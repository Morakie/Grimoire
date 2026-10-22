"""LSV's conditional rules ("when X, do Y"), layered on engine 2's numbers.

A rule never forces a pick: when its condition holds it changes one number the engine already compares (a
card's colour fit, its value, its chance of being gone), so the bot can't take something that makes no sense.
Each rule has an id, a source, an on/off weight in engine2.TUNING2 (`rule_<name>`, 0 = off; the Bot Lab
shows them under "LSV rules") and a test in tests/test_principles.py named after its id. List them in
docs/project-notes/bot-principles.md.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, Iterable, NamedTuple, Set

from . import knowledge as K


class Rule(NamedTuple):
    id: str
    knob: str
    name: str
    source: str
    effect: str


RULES = [
    Rule("R1", "rule_cheat_colour", "Cheat targets ignore colour",
         "LSV's combo article (Flash wants Worldspine Wurm); owner (2026-10-21)",
         "A seat holding Flash, Sneak Attack, Show and Tell, Oath, Natural Order or a reanimation spell rates the "
         "creatures that enabler puts into play as on-colour: they are never cast. Without an enabler, nothing "
         "changes, and a target nobody else can use still floats."),
    Rule("R2", "rule_deck_mix", "Each deck type has a budget per kind of card",
         "VRD sheets and the owner's group's drafts (knowledge.DECK_MIX); owner (2026-10-22)",
         "A seat ahead of what its deck type usually holds by this point (creatures for an aggro deck, enablers and "
         "big creatures for a cheat deck, removal for Academy) values more of that kind less. A seat short of "
         "lands past its first picks values them more: people take 7-12 nonbasic lands in 40 picks."),
]


def key(name: str) -> str:
    return (name or "").split(" // ")[0].strip().lower()


# Enabler -> how it puts creatures into play. "flash": Flash's own targets (death or enter triggers: knowledge
# COMBO_PACKAGES "flash"); "hand" / "library": any big creature; "grave": reanimation (not the cards that
# shuffle themselves away); "green": Natural Order (a green creature).
CHEAT_ENABLERS: Dict[str, str] = {
    "Flash": "flash",
    "Sneak Attack": "hand", "Show and Tell": "hand", "Through the Breach": "hand", "Omniscience": "hand",
    "Elvish Piper": "hand", "Eureka": "hand", "Quicksilver Amulet": "hand",
    "Oath of Druids": "library",
    "Natural Order": "green",
    "Reanimate": "grave", "Animate Dead": "grave", "Exhume": "grave", "Necromancy": "grave",
    "Dance of the Dead": "grave", "Persist": "grave", "Unburial Rites": "grave", "Dread Return": "grave",
    "Goryo's Vengeance": "grave", "Life // Death": "grave", "Shallow Grave": "grave", "Stitch Together": "grave",
}

# Shuffle back into the library on reaching the graveyard: nothing to reanimate.
NOT_REANIMATABLE: FrozenSet[str] = frozenset(key(n) for n in (
    "Worldspine Wurm", "Emrakul, the Aeons Torn", "Ulamog, the Infinite Gyre", "Kozilek, Butcher of Truth",
    "Blightsteel Colossus", "Darksteel Colossus", "Progenitus"))

_ENABLER_KIND = {key(n): kind for n, kind in CHEAT_ENABLERS.items()}
FLASH_TARGETS: FrozenSet[str] = frozenset(
    key(card) for name, _, slots in K.COMBO_PACKAGES if name == "flash"
    for _, cards in slots[1:] for card in cards)


def cheat_kinds(names: Iterable[str]) -> Set[str]:
    """How the seat can put creatures into play, from the cards it owns."""
    return {_ENABLER_KIND[k] for k in map(key, names) if k in _ENABLER_KIND}


def is_cheat_target(card, kinds: Set[str]) -> bool:
    """Whether one of the seat's enablers puts this card into play (so its colours don't matter)."""
    if not kinds or card.is_land:
        return False
    name = key(card.name)
    if "flash" in kinds and name in FLASH_TARGETS:
        return True
    big = "fatty" in card.roles
    if not big:
        return False
    if kinds & {"hand", "library"}:
        return True
    if "grave" in kinds and name not in NOT_REANIMATABLE:
        return True
    return "green" in kinds and "G" in card.identity


# ---------------------------------------------------------------- R2: deck mix
_DISCARD = frozenset(key(n) for n in K.DISCARD)


def card_kind(c) -> str:
    """One kind per card, for deck budgets (knowledge.DECK_MIX)."""
    t, r = c.types, c.roles
    if c.is_land:
        return "land"
    if c.name in CHEAT_ENABLERS or r & {"reanimate", "cheat"}:
        return "enabler"
    if "creature" in t:
        return "fatty" if "fatty" in r else "creature"
    if "planeswalker" in t:
        return "walker"
    if "counter" in r:
        return "counter"
    if r & {"removal", "sweeper"}:
        return "removal"
    if key(c.name) in _DISCARD:
        return "discard"
    if "ritual" in r:
        return "ritual"
    if "tutor" in r:
        return "tutor"
    if r & {"draw", "cantrip"}:
        return "draw"
    if "mana" in r:
        return "mana"
    if "artifact" in t:
        return "artifact"
    return "other"


def deck_mix(deck: str) -> Dict[str, float]:
    return (K.DECK_MIX.get(deck) or K.DECK_MIX["good_stuff"])[1]


def mix_factor(kind: str, counts: Dict[str, int], picks: int, deck: str, slack: float, cut: float,
               land_boost: float) -> float:
    """Multiplier on a card's value from the seat's deck budget. Over budget: `cut` per card beyond the usual
    count (phased in between picks 10 and 25) for this point in the draft (+20%) plus `slack` (at most 60% off). Short of lands after 10 picks: `land_boost`
    per land short (at most +40%). Staples are never cut (see engine2)."""
    if kind == "other":
        return 1.0
    expected = deck_mix(deck).get(kind, 0.0) * min(1.0, picks / 40.0)
    have = counts.get(kind, 0)
    over = have - 1.2 * expected - slack          # 20% over the usual, plus `slack` cards
    ramp = min(1.0, max(0.0, (picks - 10) / 15.0))   # early picks are about value: the budget phases in by pick 25
    if over > 0 and kind != "land" and ramp > 0:
        return max(0.4, 1.0 - ramp * cut * over)
    if kind == "land" and picks >= 10:
        short = expected - have - slack
        if short > 0:
            return 1.0 + min(0.4, land_boost * short)
    return 1.0
