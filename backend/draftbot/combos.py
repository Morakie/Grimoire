"""Combo lines and strategy packages.

Combos come from Commander Spellbook (https://commanderspellbook.com, MIT-licensed data/API): we send
the cube list and keep every combo whose pieces are all in the cube. Packages are looser enabler/payoff
relationships expressed through role tags, so they apply to any cube.
"""
from __future__ import annotations

import logging
import math
import re
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
    return with_cube_combos(index, await _spellbook_combos(index, timeout))


SPELLBOOK_MAX_LINES = 600   # Commander Spellbook rejects longer decklists (backend common/serializers.py)
SPELLBOOK_GROUP = 200       # big pools are asked about in groups of three of these (600 lines)
SPELLBOOK_PAGES = 5         # result pages (1,000 variants each) followed per request


def spellbook_batches(names: List[str], max_lines: int = SPELLBOOK_MAX_LINES, group: int = SPELLBOOK_GROUP) -> List[List[str]]:
    """Name lists to send, each within Spellbook's limit. A pool that fits goes in one request; a bigger one
    is cut into groups of up to `group` cards and every three groups are sent together, so the pieces of
    any two- or three-card combo (the only lines the bots use) all appear in at least one request."""
    if len(names) <= max_lines:
        return [list(names)]
    k = math.ceil(len(names) / group)
    size = math.ceil(len(names) / k)
    chunks = [names[i * size:(i + 1) * size] for i in range(k)]
    from itertools import combinations
    return [a + b + c for a, b, c in combinations(chunks, 3)]


async def _spellbook_combos(index: Dict[str, CardInfo], timeout: float) -> List[Combo]:
    names = sorted({info.name.split(" // ")[0] for info in index.values()})
    batches = spellbook_batches(names)
    try:
        import asyncio
        import httpx  # imported lazily so the engine itself has no network dependency
    except ImportError:
        return []
    sem = asyncio.Semaphore(3)

    async def ask(hc, batch: List[str]) -> List[dict]:
        body = "\n".join(f"1 {n}" for n in batch).encode("utf-8")
        out: List[dict] = []
        url = SPELLBOOK_URL
        async with sem:
            for _ in range(SPELLBOOK_PAGES):
                try:
                    r = await hc.post(url, content=body, headers={"Content-Type": "text/plain"})
                except Exception as exc:   # network problems shouldn't break a draft
                    log.warning("Commander Spellbook lookup failed: %s", exc)
                    break
                if r.status_code != 200:
                    log.warning("Commander Spellbook returned %s for %d cards", r.status_code, len(batch))
                    break
                data = r.json()
                out.extend((data.get("results") or {}).get("included", []))
                url = data.get("next")
                if not url:
                    break
        return out

    async with httpx.AsyncClient(timeout=timeout, headers={"Accept": "application/json", "User-Agent": "GrimoireDeckBuilder/1.0"}) as hc:
        found = await asyncio.gather(*(ask(hc, b) for b in batches))
    if len(batches) > 1:
        log.info("Commander Spellbook: %d cards asked in %d batches", len(names), len(batches))
    return _to_combos([v for vs in found for v in vs], index)


def _to_combos(variants: List[dict], index: Dict[str, CardInfo]) -> List[Combo]:
    by_name = lookup_by_name(index)
    seen = set()
    raw: List[Tuple[Tuple[str, ...], int]] = []
    for v in variants:
        if v.get("requires"):  # needs an unspecified "any X" card: too vague to draft around
            continue
        if _only_gains_life(v):  # an infinite-life loop doesn't win a game of Magic on its own
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


_LIFE = re.compile(r"\blife\b|lifegain|life gain")


def _only_gains_life(variant: dict) -> bool:
    """True when everything a Spellbook combo produces is about gaining life."""
    names = [((p.get("feature") or {}).get("name") or "").lower() for p in variant.get("produces") or []]
    return bool(names) and all(_LIFE.search(n) and "lose" not in n for n in names)


# Two-card cube staples that Commander Spellbook leaves out or lists only with extra conditions.
# Added whenever every piece is in the cube. Card names (front faces are fine).
CUBE_COMBOS: List[Tuple[str, ...]] = [
    ("Thassa's Oracle", "Tainted Pact"),
    ("Thassa's Oracle", "Demonic Consultation"),
    ("Jace, Wielder of Mysteries", "Tainted Pact"),
    ("Jace, Wielder of Mysteries", "Demonic Consultation"),
    ("Time Vault", "Voltaic Key"),
    ("Time Vault", "Manifold Key"),
    ("Isochron Scepter", "Dramatic Reversal"),
    ("Splinter Twin", "Pestermite"),
    ("Splinter Twin", "Deceiver Exarch"),
    ("Kiki-Jiki, Mirror Breaker", "Pestermite"),
    ("Kiki-Jiki, Mirror Breaker", "Deceiver Exarch"),
    ("Kiki-Jiki, Mirror Breaker", "Zealous Conscripts"),
    ("Saheeli Rai", "Felidar Guardian"),
    ("Painter's Servant", "Grindstone"),
    ("Devoted Druid", "Vizier of Remedies"),
]
CUBE_COMBO_WEIGHT = 0.9


def with_cube_combos(index: Dict[str, CardInfo], combos: List[Combo]) -> List[Combo]:
    """`combos` plus the hand-kept cube combos whose pieces are all in this cube (no duplicates)."""
    by_name = lookup_by_name(index)
    have = {tuple(sorted(c.pieces)) for c in combos}
    out = list(combos)
    for names in CUBE_COMBOS:
        ids = [by_name.get(n.lower()) for n in names]
        if all(ids):
            key = tuple(sorted(ids))
            if key not in have:
                have.add(key)
                out.append(Combo(key, CUBE_COMBO_WEIGHT))
    return out


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
    # Common vintage-cube packages
    ("artifacts", ("artifact",), ("artifact_payoff",)),
    ("storm", ("ritual", "fast_mana"), ("storm_payoff",)),
    ("blink", ("etb",), ("flicker",)),
    ("stoneforge", ("equip_fetch",), ("equipment",)),
    ("lands", ("fetchland", "landfall"), ("land_recursion",)),
]
