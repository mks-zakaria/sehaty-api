"""Harvest Google autocomplete for Morocco across French, Arabic and Darija seeds.

Autocomplete is ranked by real query volume in the region, so it is the closest
thing to demand data available without an ads account.
"""

import json, urllib.parse, urllib.request, time, sys, collections

SEEDS = {
    "fr": [
        "pourquoi j'ai mal",
        "comment soigner",
        "c'est quoi",
        "symptomes",
        "traitement naturel",
        "est-ce grave",
        "combien de temps dure",
        "pourquoi je suis toujours",
        "que faire si",
        "maladie",
    ],
    "ar": [
        "علاج",
        "أعراض",
        "ما هو",
        "كيف أعالج",
        "هل يمكن",
        "سبب",
        "متى يجب",
        "أفضل علاج",
        "مرض",
        "لماذا",
    ],
}


def suggest(q, hl):
    url = (
        "https://suggestqueries.google.com/complete/search?client=firefox"
        f"&hl={hl}&gl=ma&q={urllib.parse.quote(q)}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8", "replace"))[1]
    except Exception:
        return []


out = collections.defaultdict(list)
for hl, seeds in SEEDS.items():
    for seed in seeds:
        for s in suggest(seed, hl):
            out[hl].append(s)
        time.sleep(0.4)

json.dump(out, open("/tmp/trends/raw.json", "w"), ensure_ascii=False, indent=1)
for hl in out:
    print(f"--- {hl}: {len(out[hl])} suggestions ---")
