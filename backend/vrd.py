"""Vintage Rotisserie Draft (VRD): draft from every Vintage-legal paper card instead of a cube.

People pick any legal card by searching Scryfall. Bots can't weigh tens of thousands of cards on every
pick, so they draft from a "virtual cube": the top-rated Vintage-legal cards by CubeCobra Elo (from the
bundled data/card_elo.csv), resolved once through Scryfall and saved in Mongo (`vrd_pool`), refreshed
monthly. Cards people pick from outside that pool still count for the bots (colours, combos).
"""
from __future__ import annotations

import asyncio
import csv
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

log = logging.getLogger(__name__)

POOL_SIZE = 1500
POOL_TTL = 30 * 24 * 3600
_ELO_CSV = Path(__file__).parent / "data" / "card_elo.csv"
_MEM: Dict[str, Any] = {}
_LOCK = asyncio.Lock()


def is_legal(raw: dict) -> bool:
    """Vintage-legal (restricted counts) and printed on paper. Basic lands are free, so not drafted."""
    if (raw.get("legalities") or {}).get("vintage") not in ("legal", "restricted"):
        return False
    if "paper" not in (raw.get("games") or []):
        return False
    return not is_basic(raw)


def is_basic(raw: dict) -> bool:
    return "basic" in (raw.get("type_line") or "").lower() and "land" in (raw.get("type_line") or "").lower()


def ranked_names(limit: int) -> List[str]:
    """Card names from the bundled CubeCobra Elo list, best first."""
    rows = []
    with open(_ELO_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                rows.append((float(r["Elo"]), r["Name"].strip()))
            except (KeyError, ValueError, TypeError):
                continue
    rows.sort(reverse=True)
    seen, out = set(), []
    for _, name in rows:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            out.append(name)
        if len(out) >= limit:
            break
    return out


async def get_pool(db, lookup: Callable, prefer_oldest: Callable, map_card: Callable,
                   fetch_combos: Callable, build_index: Callable, ensure_stats: Callable, draft_stats: Callable) -> dict:
    """The bots' VRD pool: {"cards": [...], "combos": [...], "stats": {...}}. Built once, cached in Mongo
    and memory. The heavy lifting (Scryfall, Spellbook, CubeCobra) only happens on the first VRD draft
    and then about once a month."""
    hit = _MEM.get("pool")
    if hit and time.time() - hit["built_at"] < POOL_TTL:
        return hit
    async with _LOCK:
        hit = _MEM.get("pool")
        if hit and time.time() - hit["built_at"] < POOL_TTL:
            return hit
        doc = await db.vrd_pool.find_one({"key": "v1"}, {"_id": 0})
        if doc and time.time() - doc.get("built_at", 0) < POOL_TTL and doc.get("cards"):
            _MEM["pool"] = doc
            return doc
        # Build: resolve the top-rated names, keep Vintage-legal paper cards, original printings.
        names = ranked_names(int(POOL_SIZE * 1.25))
        raw = await lookup([{"name": n} for n in names])
        legal = [c for c in raw if is_legal(c)][:POOL_SIZE]
        try:
            legal = await prefer_oldest(legal)
        except Exception as exc:   # keep Scryfall's default printings
            log.warning("VRD pool: oldest-printing lookup failed: %s", exc)
        cards = [map_card(c) for c in legal]
        combos = await fetch_combos(build_index(cards))
        stats = None
        try:
            await ensure_stats(db, [c["name"] for c in cards], budget_s=60.0)
            stats = await draft_stats(db, cards)
        except Exception as exc:
            log.warning("VRD pool: CubeCobra stats unavailable: %s", exc)
        doc = {"key": "v1", "built_at": time.time(), "cards": cards,
               "combos": [c.to_dict() for c in combos], "stats": stats}
        await db.vrd_pool.update_one({"key": "v1"}, {"$set": doc}, upsert=True)
        _MEM["pool"] = doc
        log.info("VRD pool built: %d cards, %d combos", len(cards), len(combos))
        return doc
