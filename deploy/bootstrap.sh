#!/usr/bin/env bash
#
# Sehaty droplet bootstrap — idempotent and phased. Run it on a fresh Ubuntu
# droplet as a sudo-capable user (root is fine). It advances through phases and
# stops when it needs a manual action from you; just re-run it after each one.
#
#   1. install Docker + compose plugin + git, open the firewall (22/80/443)
#   2. create an SSH key and wait for you to give the droplet GitHub read access
#   3. clone / update the three private repos under /opt/sehaty
#   4. create deploy/.env from the example (you fill in the secrets)
#   5. build the image and launch the stack (db + migrate + api + caddy)
#
# Getting this file onto a brand-new droplet (before the repos are cloned):
#   scp sehaty-api/deploy/bootstrap.sh root@<droplet-ip>:/root/bootstrap.sh
#   ssh root@<droplet-ip> 'bash /root/bootstrap.sh'
# (or just paste its contents into the droplet shell).

set -euo pipefail

ROOT=/opt/sehaty
OWNER=mks-zakaria
REPOS=(sehaty-db sehaty-core sehaty-api)
KEY="${HOME}/.ssh/id_ed25519"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\n\033[1;33m%s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31m!! %s\033[0m\n' "$*" >&2; exit 1; }

# --- Phase 1: packages + firewall ------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  say "Installing Docker, the compose plugin, and git…"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y ca-certificates curl git ufw
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  arch="$(dpkg --print-architecture)"
  codename="$(. /etc/os-release && echo "$VERSION_CODENAME")"
  echo "deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${codename} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
  systemctl enable --now docker
fi

say "Opening the firewall (22/80/443)…"
ufw allow 22 >/dev/null 2>&1 || true
ufw allow 80 >/dev/null 2>&1 || true
ufw allow 443 >/dev/null 2>&1 || true
ufw --force enable >/dev/null 2>&1 || true

# --- Phase 2: GitHub read access -------------------------------------------
mkdir -p "${HOME}/.ssh" && chmod 700 "${HOME}/.ssh"
grep -q github.com "${HOME}/.ssh/known_hosts" 2>/dev/null \
  || ssh-keyscan -t ed25519 github.com >> "${HOME}/.ssh/known_hosts" 2>/dev/null
[ -f "$KEY" ] || ssh-keygen -t ed25519 -N '' -C "sehaty-droplet" -f "$KEY"

if ! ssh -o BatchMode=yes -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
  say "The droplet needs read access to the three PRIVATE repos."
  warn "Add this key to your GitHub account (grants read access to your repos):"
  echo "    https://github.com/settings/ssh/new"
  echo
  cat "${KEY}.pub"
  echo
  warn "Prefer per-repo scoping? A GitHub deploy key can't be shared across repos,"
  warn "so you'd need three separate keys + ~/.ssh/config host aliases. The account"
  warn "key above is the low-friction pilot choice."
  die "Add the key, then re-run this script."
fi

# --- Phase 3: clone / update the repos -------------------------------------
say "Syncing the three repos under ${ROOT}…"
mkdir -p "$ROOT"
for r in "${REPOS[@]}"; do
  if [ -d "${ROOT}/${r}/.git" ]; then
    git -C "${ROOT}/${r}" fetch origin main
    git -C "${ROOT}/${r}" reset --hard origin/main
  else
    git clone "git@github.com:${OWNER}/${r}.git" "${ROOT}/${r}"
  fi
done

# --- Phase 4: environment file ---------------------------------------------
ENV_DIR="${ROOT}/sehaty-api/deploy"
if [ ! -f "${ENV_DIR}/.env" ]; then
  cp "${ENV_DIR}/.env.example" "${ENV_DIR}/.env"
  say "Created ${ENV_DIR}/.env from the example."
  warn "Edit it now (strong POSTGRES_PASSWORD + matching DATABASE_URL,"
  warn "SEHATY_JWT_SECRET via 'openssl rand -hex 32', CORS_ORIGINS = your Vercel URL,"
  warn "SEHATY_API_HOST = your hostname), then re-run this script to launch."
  exit 0
fi

# --- Phase 5: build + launch -----------------------------------------------
say "Building and launching the stack…"
cd "${ENV_DIR}"
docker compose -f docker-compose.prod.yml --env-file .env build
docker compose -f docker-compose.prod.yml --env-file .env up -d --remove-orphans
docker image prune -f

say "Done. Check health:  curl https://\$(grep '^SEHATY_API_HOST=' .env | cut -d= -f2)/api/health"
