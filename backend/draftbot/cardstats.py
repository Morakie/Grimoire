"""Card statistics from CubeCobra, for any cube.

For each card, CubeCobra's card page (https://cubecobra.com/tool/card/<name>) carries data built from
thousands of real cubes and drafts:

- ``elo``: its current draft rating (fresher and more complete than our static CSV);
- ``draftedWithIDs``: cards most often drafted alongside it;
- ``synergisticIDs``: cards it appears with far more often than chance (its real package partners).

We read only those fields, cache them in Mongo (collection ``card_stats``, refreshed monthly) and turn
them into per-draft data: a rating per card and, per card, its partners *within this cube*.
Everything degrades gracefully: a card with no stats just uses the CSV Elo and no partners.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

log = logging.getLogger(__name__)

CARD_URL = "https://cubecobra.com/tool/card/{}"
MAX_AGE = timedelta(days=30)
_PROPS = re.compile(r"window\.reactProps\s*=\s*(\{.*?\});\s*</script>", re.S)

SYNERGY_STRENGTH = 1.0   # "synergistic" partner
DRAFTED_STRENGTH = 0.5   # "often drafted with" partner (also includes generically popular cards)


def parse_card_page(html: str) -> Optional[dict]:
    m = _PROPS.search(html or "")
    if not m:
        return None
    try:
        props = json.loads(m.group(1))
    except ValueError:
        return None
    card = props.get("card") or {}
    if not card.get("name"):
        return None

    def top(key):
        return [i for i in ((props.get(key) or {}).get("top") or []) if isinstance(i, str)][:40]
    return {
        "name": card["name"],
        "cc_id": card.get("scryfall_id") or "",
        "elo": card.get("elo"),
        "drafted_with": top("draftedWithIDs"),
        "synergistic": top("synergisticIDs"),
    }


async def _fetch_one(hc, name: str) -> Optional[dict]:
    from urllib.parse import quote
    try:
        r = await hc.get(CARD_URL.format(quote(name, safe="")))
        if r.status_code != 200 or r.url.path.endswith("/404"):
            return None
        return parse_card_page(r.text)
    except Exception as exc:  # network trouble: just skip this card
        log.info("CubeCobra stats for %s failed: %s", name, exc)
        return None


_IN_FLIGHT: set = set()


async def ensure_stats(db, names: Iterable[str], budget_s: float = 10.0, concurrency: int = 4) -> None:
    """Fetch and cache stats for any of `names` that are missing or stale, for up to `budget_s` seconds.
    Safe to call repeatedly (and in the background): cards already being fetched are skipped."""
    import httpx

    names = list(dict.fromkeys(n for n in names if n))
    now = datetime.now(timezone.utc)
    fresh = set()
    async for doc in db.card_stats.find({"key": {"$in": [n.lower() for n in names]}}, {"key": 1, "fetched_at": 1}):
        try:
            if now - datetime.fromisoformat(doc["fetched_at"]) < MAX_AGE:
                fresh.add(doc["key"])
        except (KeyError, ValueError):
            pass
    todo = [n for n in names if n.lower() not in fresh and n.lower() not in _IN_FLIGHT]
    if not todo:
        return
    _IN_FLIGHT.update(n.lower() for n in todo)
    deadline = asyncio.get_event_loop().time() + budget_s
    sem = asyncio.Semaphore(concurrency)
    headers = {"User-Agent": "GrimoireDeckBuilder/1.0 (rotisserie draft bots)"}

    async def work(hc, name):
        try:
            async with sem:
                if asyncio.get_event_loop().time() > deadline:
                    return
                stats = await _fetch_one(hc, name)
                await asyncio.sleep(0.1)   # be polite
            doc = {"key": name.lower(), "fetched_at": datetime.now(timezone.utc).isoformat()}
            doc.update(stats or {"name": name, "missing": True})
            await db.card_stats.update_one({"key": doc["key"]}, {"$set": doc}, upsert=True)
        finally:
            _IN_FLIGHT.discard(name.lower())

    try:
        async with httpx.AsyncClient(timeout=15.0, headers=headers, follow_redirects=True) as hc:
            await asyncio.gather(*(work(hc, n) for n in todo))
    finally:
        for n in todo:
            _IN_FLIGHT.discard(n.lower())


async def draft_stats(db, cube: List[dict]) -> dict:
    """Per-draft stats from the cache: {"elo": {card_id: elo}, "partners": {card_id: {card_id: strength}}}.
    Partners are limited to cards in this cube and made symmetric."""
    cards = [c for c in cube if not c.get("is_custom")]
    by_key = {c.get("name", "").lower(): c["id"] for c in cards}
    docs = {}
    async for doc in db.card_stats.find({"key": {"$in": list(by_key)}, "missing": {"$ne": True}}):
        docs[doc["key"]] = doc
    cc_to_card = {doc.get("cc_id"): by_key[key] for key, doc in docs.items() if doc.get("cc_id")}
    elo: Dict[str, float] = {}
    partners: Dict[str, Dict[str, float]] = {}

    def link(a, b, s):
        if a == b:
            return
        for x, y in ((a, b), (b, a)):
            row = partners.setdefault(x, {})
            row[y] = max(row.get(y, 0.0), s)

    for key, doc in docs.items():
        cid = by_key[key]
        if doc.get("elo"):
            elo[cid] = float(doc["elo"])
        for other in doc.get("drafted_with", []):
            if other in cc_to_card:
                link(cid, cc_to_card[other], DRAFTED_STRENGTH)
        for other in doc.get("synergistic", []):
            if other in cc_to_card:
                link(cid, cc_to_card[other], SYNERGY_STRENGTH)
    return {"elo": elo, "partners": partners}
