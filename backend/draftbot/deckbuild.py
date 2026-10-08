"""Suggest a deck from a drafted pool.

The same card knowledge the bots draft with (power, colour needs, fixing) picks two main colours, an
optional splash, the best castable spells, the on-colour non-basic lands and a basic land split by
colour pips. It is a starting point for the player, not a rule: Kitchen Magic has no deck size.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from .engine import TUNING, _lane_fit, best_pair, splash_colour
from .features import COLORS, CardInfo

_PIP = re.compile(r"\{([^}]+)\}")


def _pips(mana_cost: str) -> Dict[str, float]:
    """Coloured pips in a mana cost; hybrid symbols count half for each colour."""
    out: Dict[str, float] = {}
    for sym in _PIP.findall(mana_cost or ""):
        cols = [c for c in sym.upper().split("/") if c in COLORS]
        for c in cols:
            out[c] = out.get(c, 0.0) + 1.0 / len(cols)
    return out


def _land_count(spells: List[CardInfo], size: int) -> int:
    """17 for a 40-card deck, one fewer for a low curve, scaled for other sizes."""
    avg = sum(c.cmc for c in spells) / max(len(spells), 1)
    base = 16 if avg <= 2.4 else 17
    return max(1, round(base * size / 40))


def suggest_deck(pool: List[dict], index: Dict[str, CardInfo], size: int = 40) -> dict:
    """`pool` is the seat's picks (draft card dicts); `index` the draft's card index.

    Returns the ids for the main deck, basic land counts per colour, and the colours chosen."""
    infos = [index[c["id"]] for c in pool if c.get("id") in index]
    by_id = {c["id"]: c for c in pool}
    if not infos:
        return {"main": [], "basics": {}, "colors": [], "splash": None}

    pair = best_pair(infos)
    splash = splash_colour(infos, pair, lambda k: TUNING[k])
    lane = pair | ({splash} if splash else frozenset())

    spells = [c for c in infos if not c.is_land]
    lands = [c for c in infos if c.is_land]

    def spell_score(c: CardInfo) -> float:
        s = c.power
        if c.need and not c.need <= pair:      # splash card: only the strong ones are worth it
            s -= 0.25
        if c.is_creature:
            s += 0.05
        return s

    castable = sorted((c for c in spells if c.need <= lane), key=spell_score, reverse=True)
    n_lands = _land_count(castable[: size - 17] or castable, size)
    n_spells = max(0, size - n_lands)

    chosen: List[CardInfo] = []
    splash_cards = 0
    expensive = 0
    for c in castable:
        if len(chosen) >= n_spells:
            break
        if splash and splash in c.need:
            if splash_cards >= 3:
                continue
            splash_cards += 1
        if c.cmc >= 6:
            if expensive >= 3:                 # keep the curve playable
                continue
            expensive += 1
        chosen.append(c)

    # Non-basic lands that make our colours (or colourless utility lands), best fit first.
    fixing = sorted((l for l in lands if _lane_fit(l, pair) >= 0.35 or (splash and splash in l.produces) or not l.produces),
                    key=lambda l: (_lane_fit(l, pair), l.power), reverse=True)
    nonbasics = fixing[: max(0, min(len(fixing), n_lands - 6))]
    n_basics = max(0, n_lands - len(nonbasics))

    # Split basics by coloured pips in the chosen spells; a splash gets at least one source.
    pips: Dict[str, float] = {c: 0.0 for c in lane}
    for c in chosen:
        for col, n in _pips(by_id.get(c.id, {}).get("mana_cost", "")).items():
            if col in pips:
                pips[col] += n
    total = sum(pips.values())
    basics: Dict[str, int] = {}
    if n_basics and total > 0:
        raw = {col: n_basics * v / total for col, v in pips.items()}
        basics = {col: int(v) for col, v in raw.items()}
        for col in sorted(raw, key=lambda k: raw[k] - int(raw[k]), reverse=True):
            if sum(basics.values()) >= n_basics:
                break
            basics[col] += 1
        # Every colour the spells need gets at least 3 sources (2 for a splash), counting non-basic
        # lands that make it; the extra basics come from the colour with the most.
        for col, v in pips.items():
            if v <= 0:
                continue
            floor = 2 if col == splash else 3
            sources = basics.get(col, 0) + sum(1 for l in nonbasics if col in l.produces)
            while sources < floor:
                donor = max((k for k in basics if k != col), key=lambda k: basics[k], default=None)
                if donor is None or basics[donor] <= floor:
                    break
                basics[donor] -= 1
                basics[col] = basics.get(col, 0) + 1
                sources += 1
    elif n_basics:
        basics = {"C": n_basics}                # colourless pool: Wastes
    basics = {k: v for k, v in basics.items() if v > 0}

    return {
        "main": [c.id for c in chosen] + [l.id for l in nonbasics],
        "basics": basics,
        "colors": sorted(pair, key=COLORS.index),
        "splash": splash,
    }
