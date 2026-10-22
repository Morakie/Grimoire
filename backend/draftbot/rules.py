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
