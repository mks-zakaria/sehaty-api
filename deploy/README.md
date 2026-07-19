# Sehaty pilot deploy (DigitalOcean droplet + Vercel)

Minimal stack for the first users. Everything runs in one `docker compose`:

| Service   | What                                   |
|-----------|----------------------------------------|
| `db`      | Postgres 16 + PostGIS (data on a volume) |
| `migrate` | one-shot `alembic upgrade head`, then exits |
| `api`     | FastAPI (uvicorn), internal port 8000  |
| `caddy`   | HTTPS reverse proxy, auto Let's Encrypt |

The **front-end and landing page deploy to Vercel** (free) and call this API over HTTPS. No SMS/email/Redis/queue needed — doctors & pharmacies use email+password, patients use phone+password.

## Repo layout on the droplet

The API image needs its sibling repos (path deps), so clone all three as siblings:

```
sehaty/
├── sehaty-api/   ← this repo (deploy/ lives here)
├── sehaty-core/
└── sehaty-db/
```

## One-time droplet setup

```bash
# On a fresh Ubuntu droplet (2 GB recommended; 1 GB works with swap)
apt-get update && apt-get install -y docker.io docker-compose-plugin git
# Firewall: allow SSH + HTTP + HTTPS
ufw allow 22 && ufw allow 80 && ufw allow 443 && ufw --force enable

# Clone the three repos as siblings
mkdir -p /opt/sehaty && cd /opt/sehaty
git clone git@github.com:mks-zakaria/sehaty-api.git
git clone git@github.com:mks-zakaria/sehaty-core.git
git clone git@github.com:mks-zakaria/sehaty-db.git
```

## Point a hostname at the droplet

Either a real domain's `A` record, or — free, until you own one — use **sslip.io**:
`api.<droplet-ip>.sslip.io` resolves to your IP automatically (e.g. `api.203.0.113.10.sslip.io`). Put it in `.env` as `SEHATY_API_HOST`.

## Configure & launch

```bash
cd /opt/sehaty/sehaty-api/deploy
cp .env.example .env
# Edit .env: strong POSTGRES_PASSWORD, matching DATABASE_URL,
# SEHATY_JWT_SECRET (openssl rand -hex 32), CORS_ORIGINS (your Vercel URL),
# SEHATY_API_HOST (your hostname).

docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

Boot order is automatic: `db` → `migrate` (runs to completion) → `api` → `caddy`.

## Verify

```bash
curl https://<SEHATY_API_HOST>/api/health          # -> {"status":"ok"}
# Register a doctor / pharmacy, or a patient (phone+password), then log in.
```

## Front-end (Vercel)

Set an env var on the Vercel project and redeploy:

```
VITE_API_URL = https://<SEHATY_API_HOST>/api
```

Make sure `CORS_ORIGINS` in `.env` includes the Vercel origin (e.g. `https://sehaty-front.vercel.app`), then `docker compose ... up -d` to apply.

> Changing the domain later = update `SEHATY_API_HOST` (+ Caddy re-issues the cert), update Vercel's `VITE_API_URL` and the API's `CORS_ORIGINS`. Nothing else moves.

## Redeploy (new code)

```bash
cd /opt/sehaty/sehaty-api && git pull      # and sehaty-core / sehaty-db as needed
cd deploy
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

`migrate` re-runs `upgrade head` every time (a no-op when already at head), so new migrations apply on deploy.

## Backups (recommended)

Nightly logical dump via cron on the droplet:

```bash
# crontab -e
0 3 * * * docker exec sehaty-db-1 pg_dump -U sehaty sehaty | gzip > /opt/sehaty/backups/sehaty-$(date +\%F).sql.gz
```

(Adjust the container name to match `docker compose ps`.) Rotate/off-site later (DO Spaces) when it matters.

## Sizing notes

- **2 GB / 1 vCPU (~$12/mo)** is comfortable. On the **$6 / 1 GB** droplet add ~2 GB swap first (`fallocate -l 2G /swapfile && mkswap /swapfile && swapon /swapfile`), or the PostGIS+Python build will OOM.
- The `db` volume (`pgdata`) is the only stateful piece — back it up, don't `docker compose down -v` it.
