"""Vintage Rotisserie Draft (VRD): draft from every Vintage-legal paper card instead of a cube.

People pick any legal card by searching Scryfall. Bots can't weigh tens of thousands of cards on every
pick, so they draft from a "virtual cube": the top-rated Vintage-legal cards by CubeCobra Elo (from the
bundled data/card_elo.csv). That pool is only ever built when someone hosts a VRD table, in the
background (nothing waits for it), saved in Mongo (`vrd_pool`) and kept in memory, and refreshed
monthly. Cards people pick from outside the pool still count for the bots (colours, combos).

Build cost: ~25 Scryfall collection requests (cards), then one Commander Spellbook request (combos).
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
_MEM: Dict[str, Any] = {"pool": None, "task": None}
POOL_KEY = "v2"   # bump to rebuild the saved pool after a rule change


def is_basic(raw: dict) -> bool:
    t = (raw.get("type_line") or "").lower()
    return "basic" in t and "land" in t


def is_legal(raw: dict) -> bool:
    """Vintage-legal (restricted counts). Legality is per card, not per printing, and already excludes
    digital-only cards (Alchemy etc.), so an online-only printing such as Vintage Masters Power is fine.
    Basic lands are free, so not drafted."""
    if (raw.get("legalities") or {}).get("vintage") not in ("legal", "restricted"):
        return False
    return not is_basic(raw)


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


def peek() -> Optional[dict]:
    """The pool if it's ready in memory, else None (never blocks)."""
    pool = _MEM.get("pool")
    if pool and time.time() - pool.get("built_at", 0) < POOL_TTL and pool.get("cards"):
        return pool
    return None


def warm(db, lookup: Callable, map_card: Callable, fetch_combos: Callable, build_index: Callable,
         oldest: Optional[Callable] = None) -> None:
    """Make sure the pool is loading or loaded, in the background. Cheap to call often."""
    if peek() or (_MEM.get("task") and not _MEM["task"].done()):
        return
    _MEM["task"] = asyncio.create_task(_load_or_build(db, lookup, map_card, fetch_combos, build_index, oldest))


async def _load_or_build(db, lookup, map_card, fetch_combos, build_index, oldest=None) -> None:
    try:
        doc = await db.vrd_pool.find_one({"key": POOL_KEY}, {"_id": 0})
        if doc and doc.get("cards") and time.time() - doc.get("built_at", 0) < POOL_TTL:
            _MEM["pool"] = doc
            return
        # Phase 1: the cards (enough for bots to draft).
        names = ranked_names(int(POOL_SIZE * 1.25))
        raw = await lookup([{"name": n} for n in names])
        cards = [map_card(c) for c in raw if is_legal(c)][:POOL_SIZE]
        doc = {"key": POOL_KEY, "built_at": time.time(), "cards": cards, "combos": [], "stats": None}
        _MEM["pool"] = doc
        await db.vrd_pool.update_one({"key": POOL_KEY}, {"$set": doc}, upsert=True)
        await db.vrd_pool.delete_many({"key": {"$ne": POOL_KEY}})   # drop older versions
        log.info("VRD pool: %d cards", len(cards))
        # Phase 2: combos between pool cards (bots use them once they arrive).
        try:
            combos = await fetch_combos(build_index(cards))
            doc = {**doc, "combos": [c.to_dict() for c in combos]}
            _MEM["pool"] = doc
            await db.vrd_pool.update_one({"key": POOL_KEY}, {"$set": {"combos": doc["combos"]}})
            log.info("VRD pool: %d combos", len(combos))
        except Exception as exc:
            log.warning("VRD pool: combos unavailable: %s", exc)
        # Phase 3: original paper printings for the art (like cubes). Picks match by name, so swapping
        # printings mid-draft is harmless.
        if oldest:
            try:
                swapped = await oldest([c for c in raw if is_legal(c)][:POOL_SIZE])
                cards = [map_card(c) for c in swapped]
                doc = {**doc, "cards": cards}
                _MEM["pool"] = doc
                await db.vrd_pool.update_one({"key": POOL_KEY}, {"$set": {"cards": cards}})
                log.info("VRD pool: original printings applied")
            except Exception as exc:
                log.warning("VRD pool: original printings unavailable: %s", exc)
    except Exception as exc:
        log.warning("VRD pool build failed: %s", exc)
