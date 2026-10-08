"""Combo lines and strategy packages.

Combos come from Commander Spellbook (https://commanderspellbook.com, MIT-licensed data/API): we send
the cube list and keep every combo whose pieces are all in the cube. Packages are looser enabler/payoff
relationships expressed through role tags, so they apply to any cube.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from .features import CardInfo, lookup_by_name

log = logging.getLogger(__name__)

SPELLBOOK_URL = "https://backend.commanderspellbook.com/find-my-combos"


@dataclass
class Combo:
    pieces: Tuple[str, ...]   # card ids
    weight: float             # 0.6..1.0, from Spellbook popularity

    def to_dict(self) -> dict:
        return {"pieces": list(self.pieces), "weight": round(self.weight, 3)}


def combos_from_dicts(rows: Iterable[dict]) -> List[Combo]:
    return [Combo(tuple(r["pieces"]), float(r.get("weight", 0.8))) for r in rows]


async def fetch_combos(index: Dict[str, CardInfo], timeout: float = 20.0) -> List[Combo]:
    """Ask Commander Spellbook which combos are fully contained in this cube.

    Returns [] on any failure: bots still draft well on power, lanes and packages alone.
    """
    if not index:
        return []
    names = sorted({info.name.split(" // ")[0] for info in index.values()})
    body = "\n".join(f"1 {n}" for n in names)
    try:
        import httpx  # imported lazily so the engine itself has no network dependency

        async with httpx.AsyncClient(timeout=timeout, headers={"Accept": "application/json", "User-Agent": "GrimoireDeckBuilder/1.0"}) as hc:
            r = await hc.post(SPELLBOOK_URL, content=body.encode("utf-8"), headers={"Content-Type": "text/plain"})
        if r.status_code != 200:
            log.warning("Commander Spellbook returned %s", r.status_code)
            return []
        variants = r.json().get("results", {}).get("included", [])
    except Exception as exc:  # network / JSON problems shouldn't break a draft
        log.warning("Commander Spellbook lookup failed: %s", exc)
        return []
    return _to_combos(variants, index)


def _to_combos(variants: List[dict], index: Dict[str, CardInfo]) -> List[Combo]:
    by_name = lookup_by_name(index)
    seen = set()
    raw: List[Tuple[Tuple[str, ...], int]] = []
    for v in variants:
        if v.get("requires"):  # needs an unspecified "any X" card: too vague to draft around
            continue
        ids = []
        for use in v.get("uses", []):
            name = (use.get("card") or {}).get("name", "").lower()
            cid = by_name.get(name) or by_name.get(name.split(" // ")[0])
            if not cid:
                break
            ids.append(cid)
        else:
            key = tuple(sorted(ids))
            if len(key) >= 2 and key not in seen:
                seen.add(key)
                raw.append((key, int(v.get("popularity") or 0)))
    if not raw:
        return []
    top = max(math.log1p(p) for _, p in raw) or 1.0
    return [Combo(pieces, 0.6 + 0.4 * math.log1p(pop) / top) for pieces, pop in raw]


def attach_combos(index: Dict[str, CardInfo], combos: List[Combo]) -> None:
    for info in index.values():
        info.combos = []
    for i, combo in enumerate(combos):
        for cid in combo.pieces:
            if cid in index:
                index[cid].combos.append(i)


# Packages: (name, enabler roles, payoff roles). A card that fills one side gets more valuable as the
# bot collects cards from the other side. Weights are modest; combos carry the strong signals.
PACKAGES: List[Tuple[str, Tuple[str, ...], Tuple[str, ...]]] = [
    ("reanimator", ("reanimate", "self_mill", "discard_outlet"), ("fatty",)),
    ("cheat", ("cheat",), ("fatty",)),
    ("artifact_cheat", ("artifact_cheat",), ("big_artifact",)),
    ("aristocrats", ("sac_outlet",), ("death_payoff", "token_maker")),
    ("spells", ("spells_payoff",), ("draw", "ritual", "counter")),
    ("graveyard", ("graveyard_cast",), ("self_mill", "discard_outlet")),
    ("tokens", ("anthem",), ("token_maker",)),
]
