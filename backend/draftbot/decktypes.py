"""Deck types: what a pool is building beyond its colours (artifacts, storm, reanimator, ...).

Colours alone made every colourless card look like it fits every deck, so bots without an artifact plan
took Top, Baubles and Retrofitter Foundry early and four seats piled into one artifact drafter's lane.
Here a deck type is defined by its KEY cards (Tolarian Academy, Urza, Time Vault for artifacts; Entomb
and Reanimate for reanimator), not just good cards:

- every card gets a membership per deck type: 1 for a key card, otherwise how strongly its CubeCobra
  partners in this cube are that deck type's key cards (Mishra's Bauble -> artifacts);
- a NARROW card (a colourless non-mana spell, a key card without colours, or a one-colour utility land
  like Karakas) only pays off in some decks; engine.narrow_factor discounts it until the bot is in one;
- a pool's strength in a deck type comes from the key cards it owns (and a little from members);
- engine.deck_crowding keeps more than two seats from chasing the same deck type.
"""
from __future__ import annotations

from typing import Dict, Iterable

from .features import CardInfo

# Key cards by deck type (names as in Scryfall, matched case-insensitively). Role tags add more keys:
# see ROLE_KEYS. Cards missing from a cube are simply ignored.
KEYS: Dict[str, tuple] = {
    "artifacts": (
        "Tolarian Academy", "Urza, Lord High Artificer", "Mishra's Workshop", "Time Vault", "Mox Opal",
        "Urza's Saga", "Retrofitter Foundry", "Kappa Cannoneer", "Emry, Lurker of the Loch", "Tinker",
        "Forensic Gadgeteer", "Karn, the Great Creator", "Cranial Plating", "Sai, Master Thopterist",
        "Thopter Foundry", "Sword of the Meek", "Transmute Artifact", "Saheeli, Sublime Artificer",
    ),
    "storm": (
        "Tendrils of Agony", "Brain Freeze", "Grapeshot", "Mind's Desire", "Underworld Breach",
        "Lion's Eye Diamond", "Doomsday", "Yawgmoth's Will", "Dark Ritual", "Cabal Ritual", "Bolas's Citadel",
        "Thassa's Oracle", "Tainted Pact", "Empty the Warrens", "Past in Flames", "Ad Nauseam",
    ),
    "reanimator": (
        "Entomb", "Reanimate", "Animate Dead", "Exhume", "Buried Alive", "Necromancy", "Unburial Rites",
        "Persist", "Dread Return", "Shallow Grave", "Life // Death", "Goryo's Vengeance",
    ),
    "cheat": (
        "Sneak Attack", "Show and Tell", "Natural Order", "Flash", "Through the Breach", "Oath of Druids",
        "Eureka", "Elvish Piper", "Omniscience",
    ),
    "lands": (
        "Life from the Loam", "Crucible of Worlds", "Ramunap Excavator", "Azusa, Lost but Seeking",
        "Field of the Dead", "Titania, Protector of Argoth", "Dryad of the Ilysian Grove", "Splendid Reclamation",
    ),
}
# Role tags that make a card a key card of a deck type (from features.ROLE_PATTERNS).
ROLE_KEYS = {"artifact_payoff": "artifacts", "storm_payoff": "storm", "reanimate": "reanimator",
             "cheat": "cheat", "land_recursion": "lands"}
DECK_TYPES = tuple(KEYS)

_KEY_NAMES = {n.lower(): t for t, names in KEYS.items() for n in names}

# A card's membership in a deck type comes from the share of its CubeCobra partners (by strength) that
# are that deck type's key cards: Mishra's Bauble 15% artifact keys, Retrofitter Foundry 20% (members);
# Dismember 5% reanimator keys out of 100 partners, Skullclamp 7% artifact keys (drafted with everything).
SHARE_FROM = 0.04        # share of partners at which membership starts...
SHARE_FULL = 0.12        # ...and is full
MIN_KEY_STRENGTH = 1.5   # partner strength to key cards needed at all (cards with few known partners)


def _key_types(card: CardInfo) -> set:
    out = set()
    t = _KEY_NAMES.get(card.name.lower()) or _KEY_NAMES.get(card.name.split(" // ")[0].lower())
    if t:
        out.add(t)
    for role, t in ROLE_KEYS.items():
        if role in card.roles:
            out.add(t)
    return out


def attach_deck_types(index: Dict[str, CardInfo]) -> None:
    """Set each card's key_of (deck types it defines) and deck (membership 0..1 per deck type)."""
    for info in index.values():
        info.key_of = frozenset(_key_types(info))
    for info in index.values():
        deck = {t: 1.0 for t in info.key_of}
        sums: Dict[str, float] = {}
        total = 0.0
        for pid, strength in info.partners.items():
            p = index.get(pid)
            if p is None:
                continue
            total += strength
            for t in p.key_of:
                sums[t] = sums.get(t, 0.0) + strength
        for t, s in sums.items():
            if s < MIN_KEY_STRENGTH:
                continue
            share = s / total
            m = min(1.0, max(0.0, (share - SHARE_FROM) / (SHARE_FULL - SHARE_FROM)))
            deck[t] = max(deck.get(t, 0.0), m)
        info.deck = {t: round(v, 3) for t, v in deck.items() if v >= 0.1}


def is_universal(card: CardInfo) -> bool:
    """Cards that go in nearly every deck (Moxen, Sol Ring, Strip Mine): owning one says nothing about
    which package or deck type a pool is building. Colourless key cards (Mox Opal, Lion's Eye Diamond,
    Mishra's Workshop) are not universal: they belong to their deck type."""
    if card.need or card.key_of:
        return False
    if card.is_land:
        return not card.produces
    return "mana" in card.roles


NARROW_MEMBERSHIP = 0.5   # deck-type membership that makes a colourless spell narrow (Top, Baubles)


def is_narrow(card: CardInfo, universal: bool, take_on_sight: bool) -> bool:
    """A card that only pays off in some decks: colourless key cards (Time Vault, Mox Opal, Lion's Eye
    Diamond), colourless spells whose partners tie them to a deck type (Top, Baubles, Retrofitter
    Foundry) and one-colour utility lands (Karakas, Tolarian Academy). Coloured spells are judged by their
    colours instead, and colourless cards drafted with everything (Dismember, Mental Misstep) aren't narrow."""
    if take_on_sight:
        return False
    if card.is_land:
        return bool(card.key_of) or (len(card.produces) == 1 and not universal)
    if card.need or universal:
        return False
    return bool(card.key_of) or max(card.deck.values(), default=0.0) >= NARROW_MEMBERSHIP


def deck_strength(pool: Iterable[CardInfo]) -> Dict[str, float]:
    """0..1 per deck type: how far a pool is into it. Key cards count fully (two make it a full deck type),
    other members a quarter each."""
    raw = {t: 0.0 for t in DECK_TYPES}
    for c in pool:
        if c.staple or (is_universal(c) and not c.key_of):
            continue                        # Moxen and Sol Ring go in every deck: they don't make one
        for t in DECK_TYPES:
            if t in c.key_of:
                raw[t] += 1.0
            elif t in c.deck:
                raw[t] += 0.25 * c.deck[t]
    return {t: min(1.0, v / 2.0) for t, v in raw.items()}
