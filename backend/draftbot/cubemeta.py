"""Card synergy and archetype staples from CubeCobra's public deck export (backend/data/cube_meta.json).

The file is rebuilt monthly by tools/cubecobra/build_meta.py (GitHub Actions) from decks drafted in powered
cubes. It is keyed by card name, so it works for any cube; it is loaded once, lazily, and everything here
degrades to "no data" when the file is missing.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cube_meta.json")
_META: Optional[dict] = None


def _key(name: str) -> str:
    return " ".join(str(name).replace("’", "'").split()).lower()


def load(path: str = _PATH) -> dict:
    """The whole file (cached). Empty sections when it doesn't exist or can't be read."""
    global _META
    if _META is None:
        try:
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            raw = {}
        syn = {}
        for name, rows in (raw.get("synergy") or {}).items():
            syn[_key(name)] = [(_key(other), float(lift)) for other, lift in rows]
        _META = {"source": raw.get("source") or {}, "archetypes": raw.get("archetypes") or {}, "synergy": syn}
    return _META


def synergy_strength(lift: float) -> float:
    """Map a co-occurrence lift to a partner strength like CubeCobra's (1.0 = "synergistic"). Conservative:
    only strong pairs count (x3 -> 0.25, x5 -> 0.5, x9 or more -> 1.0); weaker settings made the bots chase
    generic "played together" pairs and complete fewer combos in benchmark drafts."""
    return 0.0 if lift < 3.0 else max(0.0, min(1.0, (lift - 1.0) / 8.0))


def cube_partners(cards: List[Tuple[str, str]], meta: Optional[dict] = None) -> Dict[str, Dict[str, float]]:
    """Partners within one cube: {card_id: {card_id: strength}} for (card_id, name) pairs, symmetric.
    Double-faced cards match on their full name or their front face."""
    meta = meta if meta is not None else load()
    syn = meta.get("synergy") or {}
    if not syn:
        return {}
    by_name: Dict[str, List[str]] = {}
    for cid, name in cards:
        k = _key(name)
        by_name.setdefault(k, []).append(cid)
        front = k.split(" // ")[0]
        if front != k:
            by_name.setdefault(front, []).append(cid)
    out: Dict[str, Dict[str, float]] = {}
    for cid, name in cards:
        k = _key(name)
        rows = syn.get(k) or syn.get(k.split(" // ")[0]) or []
        for other, lift in rows:
            s = synergy_strength(lift)
            if s <= 0:
                continue
            for oid in by_name.get(other, []):
                if oid == cid:
                    continue
                for a, b in ((cid, oid), (oid, cid)):
                    row = out.setdefault(a, {})
                    row[b] = max(row.get(b, 0.0), s)
    return out
