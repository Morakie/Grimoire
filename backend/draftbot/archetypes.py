"""Deck plans ("archetypes") the bots can draft toward.

An archetype is a set of card *roles* (from features.py) plus the colour pairs it usually lives in. The
colours are a soft guide, not a rule, and nothing here names specific cards, so it works for any cube.
A bot keeps a probability over archetypes based on its pool; cards that advance its likely plans get a
bonus, and plans other drafters are already pursuing look less attractive (the same idea as colours).
"""
from __future__ import annotations

import math
from typing import Dict, FrozenSet, Iterable, List

from .features import CardInfo

# name -> (typical colour pairs, role weights)
ARCHETYPES: Dict[str, tuple] = {
    "artifacts":   (("U", "UR", "UW", "UB"), {"artifact": 0.6, "artifact_payoff": 1.6, "artifact_cheat": 1.6, "big_artifact": 1.0}),
    "cheat":       (("R", "BR", "UR", "RG"), {"cheat": 2.0, "fatty": 1.4}),
    "reanimator":  (("B", "UB", "BR", "WB"), {"reanimate": 2.0, "fatty": 1.4, "self_mill": 0.9, "discard_outlet": 0.7}),
    "aggro":       (("R", "W", "WR", "BR", "RG"), {"aggro_creature": 1.4, "burn": 1.1, "equipment": 0.8, "anthem": 0.8, "cheap_threat": 0.6}),
    "control":     (("UW", "UB", "U", "UR"), {"counter": 1.2, "sweeper": 1.4, "removal": 0.8, "draw": 0.8, "planeswalker": 1.0, "finisher": 0.5}),
    "aristocrats": (("W", "WB", "B", "BR"), {"sac_outlet": 1.6, "death_payoff": 1.6, "token_maker": 1.1}),
    "spells":      (("UR", "U", "R"), {"spells_payoff": 1.8, "cantrip": 1.0, "burn": 0.7, "ritual": 0.6, "draw": 0.5}),
    "midrange":    (("UG", "BG", "RG", "G"), {"ramp": 1.2, "value_creature": 1.1, "finisher": 0.9, "planeswalker": 0.8}),
    "stompy":      (("RG", "G", "R"), {"ramp": 1.2, "aggro_creature": 0.9, "finisher": 0.8, "fatty": 0.4}),
}
NAMES: List[str] = list(ARCHETYPES)
_LANES = {name: [frozenset(l) for l in spec[0]] for name, spec in ARCHETYPES.items()}


def relevance(card: CardInfo, archetype: str) -> float:
    """How much a card does for an archetype (0 = nothing). Capped so one card never defines a plan."""
    weights = ARCHETYPES[archetype][1]
    return min(2.0, sum(w for role, w in weights.items() if role in card.roles))


_REL_CACHE: Dict[str, tuple] = {}


def relevance_vector(card: CardInfo) -> tuple:
    vec = _REL_CACHE.get(card.id)
    if vec is None:
        vec = _REL_CACHE[card.id] = tuple(relevance(card, a) for a in NAMES)
    return vec


def archetype_distribution(pool: Iterable[CardInfo], n_picks: int, crowding: Dict[str, float] = None,
                           bias: Dict[str, float] = None) -> Dict[str, float]:
    """Probability over archetypes. Flat early, sharpening as the pool takes shape."""
    totals = [0.0] * len(NAMES)
    for card in pool:
        weight = 0.5 + max(card.power, 0.0)          # better cards say more about the plan
        for i, r in enumerate(relevance_vector(card)):
            totals[i] += r * weight
    scores = {}
    for i, name in enumerate(NAMES):
        s = totals[i]
        if crowding:
            s -= crowding.get(name, 0.0)
        if bias:
            s += bias.get(name, 0.0)
        scores[name] = s
    temp = max(1.2, 6.0 - 0.18 * n_picks)
    top = max(scores.values())
    exps = {k: math.exp((v - top) / temp) for k, v in scores.items()}
    total = sum(exps.values())
    return {k: v / total for k, v in exps.items()}


def card_archetype_bonus(card: CardInfo, dist: Dict[str, float]) -> float:
    vec = relevance_vector(card)
    return sum(dist[name] * vec[i] for i, name in enumerate(NAMES))


def lane_support(dist: Dict[str, float]) -> Dict[FrozenSet[str], float]:
    """Soft colour prior implied by the likely archetypes."""
    support: Dict[FrozenSet[str], float] = {}
    for name, p in dist.items():
        for lane in _LANES[name]:
            support[lane] = support.get(lane, 0.0) + p
    return support
