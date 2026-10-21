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

Aggro decks are deck types too (white weenie, red aggro, RG beats): Ajani or Ocelot Pride only belong in a
creature-aggro deck, so a seat that isn't building one shouldn't take them just for their rating, least of all
once another seat is deep in it.
"""
from __future__ import annotations

from typing import Dict, Iterable

from .features import CardInfo

# Key cards by deck type (names as in Scryfall, matched case-insensitively). A key card is a SIGNATURE card:
# it only belongs in that kind of deck, so owning it puts a bot into the deck type, and a bot outside the deck
# type values it less (engine.deck_factor). Generically strong cards (Lightning Bolt, Force of Will, Swords,
# fetches and duals) must never be keys, or every other bot would stop valuing them: those go in CORE.
# Similar decks are separate deck types: a Tolarian Academy deck, a Workshop deck and an artifact-synergy deck
# share some cards (Moxen, Baubles) and compete for those, but not for each other's key cards. A card can key
# more than one deck type (Ragavan: red aggro and UR tempo; a Boros deck is in both aggro types). Role tags add
# more keys (ROLE_KEYS) for cards not named here. Cards missing from a cube are simply ignored, and every other
# card's membership comes from its CubeCobra partners (attach_deck_types), so these lists stay short.
KEYS: Dict[str, tuple] = {
    # ---------------------------------------------------------------- artifacts
    "tolarian": (    # blue artifact engines: Academy, Urza, Time Vault + Keys, Tinker
        "Tolarian Academy", "Urza, Lord High Artificer", "Time Vault", "Tinker", "Transmute Artifact",
        "Voltaic Key", "Manifold Key", "Power Artifact", "Paradox Engine", "Mystic Forge",
    ),
    "workshop": (    # colourless stax and big artifacts off Mishra's Workshop
        "Mishra's Workshop", "Karn, the Great Creator", "Kappa Cannoneer", "Trinisphere", "Lodestone Golem",
        "Sphere of Resistance", "Precursor Golem", "Phyrexian Revoker", "Foundry Inspector", "Smokestack",
        "Tangle Wire", "Winter Orb", "Static Orb", "Chalice of the Void", "Golos, Tireless Pilgrim",
    ),
    "artifacts": (   # artifact synergy: Saga, Opal, Plating, Thopter-Sword, Retrofitter
        "Urza's Saga", "Mox Opal", "Retrofitter Foundry", "Cranial Plating", "Sai, Master Thopterist",
        "Thopter Foundry", "Sword of the Meek", "Emry, Lurker of the Loch", "Forensic Gadgeteer",
        "Saheeli, Sublime Artificer", "Steel Overseer", "Arcbound Ravager", "Cori-Steel Cutter",
    ),
    "welder": (      # red artifacts: Goblin Welder / Engineer swapping junk for big artifacts, Kuldotha aggro
        "Goblin Welder", "Goblin Engineer", "Daretti, Scrap Savant", "Kuldotha Forgemaster", "Bomat Courier",
        "Kuldotha Rebirth", "Daretti, Ingenious Iconoclast", "Scrap Trawler",
    ),
    "wildfire": (    # artifact-mana ramp into land-destroying sweepers
        "Wildfire", "Burning of Xinye", "Destructive Force", "Tezzeret the Seeker", "Upheaval",
    ),
    "painter": (     # Painter's Servant + Grindstone / colour hate
        "Painter's Servant", "Grindstone",
    ),
    # ---------------------------------------------------------------- combo and cheating things into play
    "storm": (       # storm finishers and engines only: rituals and Yawgmoth's Will are core (any black deck plays them)
        "Tendrils of Agony", "Brain Freeze", "Grapeshot", "Mind's Desire", "Underworld Breach",
        "Lion's Eye Diamond", "Doomsday", "Empty the Warrens", "Past in Flames", "Ad Nauseam", "High Tide",
        "Peer into the Abyss", "Aetherflux Reservoir",
    ),
    "reanimator": (
        "Entomb", "Reanimate", "Animate Dead", "Exhume", "Buried Alive", "Necromancy", "Unburial Rites",
        "Persist", "Dread Return", "Shallow Grave", "Life // Death", "Goryo's Vengeance",
    ),
    "cheat": (       # Sneak & Show, Breach, Flash, Channel, Oath
        "Sneak Attack", "Show and Tell", "Natural Order", "Flash", "Through the Breach", "Oath of Druids",
        "Eureka", "Elvish Piper", "Omniscience", "Channel", "Worldspine Wurm", "Woodfall Primus",
    ),
    "twin": (        # Splinter Twin / Kiki-Jiki with Exarch, Pestermite, Conscripts
        "Splinter Twin", "Kiki-Jiki, Mirror Breaker", "Deceiver Exarch", "Pestermite", "Zealous Conscripts",
    ),
    "nadu": (        # Nadu, Winged Wisdom creature value
        "Nadu, Winged Wisdom", "Shuko", "Thousand-Faced Shadow",
    ),
    # ---------------------------------------------------------------- value engines and control
    "recursion": (   # Recurring Nightmare, Pod, Survival: loop creatures for value
        "Recurring Nightmare", "Birthing Pod", "Survival of the Fittest", "Yawgmoth, Thran Physician",
        "Fiend Artisan", "Fleshbag Marauder", "Carrion Feeder", "Pattern of Rebirth",
    ),
    "blink": (       # flicker / enters-the-battlefield value
        "Ephemerate", "Soulherder", "Yorion, Sky Nomad", "Flickerwisp", "Restoration Angel", "Felidar Guardian",
        "Thassa, Deep-Dwelling", "Brago, King Eternal", "Charming Prince",
    ),
    "control": (     # sweepers and walls: what only a control deck plays
        "Wrath of God", "Supreme Verdict", "Day of Judgment", "Moat", "Fractured Identity", "Terminus",
        "Teferi, Hero of Dominaria", "Hullbreaker Horror", "Shark Typhoon", "Opposition",
    ),
    "tempo": (       # UR spells / tempo
        "Dragon's Rage Channeler", "Murktide Regent", "Delver of Secrets", "Expressive Iteration",
        "Young Pyromancer", "Third Path Iconoclast", "Ragavan, Nimble Pilferer", "Stormchaser Mage",
        "Sprite Dragon",
    ),
    # ---------------------------------------------------------------- aggro
    "white_aggro": (  # white weenie / Death & Taxes (Boros decks are in both aggro types)
        "Ocelot Pride", "Ajani, Nacatl Pariah", "Thalia, Guardian of Thraben", "Mother of Runes",
        "Giver of Runes", "Kytheon, Hero of Akros", "Guide of Souls", "Adeline, Resplendent Cathar",
        "Luminarch Aspirant", "Champion of the Parish", "Student of Warfare", "Isamaru, Hound of Konda",
        "Phelia, Exuberant Shepherd", "Thalia's Lieutenant", "Armageddon", "Ravages of War",
        "Esper Sentinel", "Inti, Seneschal of the Sun", "Sanguine Evangelist",
    ),
    "red_aggro": (    # mono-red aggro / burn
        "Monastery Swiftspear", "Goblin Guide", "Eidolon of the Great Revel", "Sulfuric Vortex", "Fireblast",
        "Zurgo Bellstriker", "Inti, Seneschal of the Sun", "Figure of Destiny", "Ragavan, Nimble Pilferer",
        "Goblin Rabblemaster", "Laelia, the Blade Reforged", "Sanguine Evangelist", "Rampaging Ferocidon",
    ),
    "gruul": (        # RG beats (strong gold cards like Minsc & Boo are core: their colours already limit them)
        "Burning-Tree Emissary", "Halana and Alena, Partners", "Escape to the Wilds", "Questing Beast",
    ),
    "pox": (          # mono-black disruption: symmetrical discard and land loss with recursive creatures
        "Pox", "Smallpox", "Sinkhole", "Braids, Cabal Minion", "Gravecrawler", "Phyrexian Obliterator",
        "The Rack",
    ),
    "domain": (       # five-colour zoo
        "Wild Nacatl", "Territorial Kavu", "Tribal Flames", "Leyline Binding", "Scion of Draco",
        "Nishoba Brawler",
    ),
    # ---------------------------------------------------------------- ramp and lands
    "ramp": (         # green ramp into big threats
        "Rofellos, Llanowar Emissary", "Gaea's Cradle", "Craterhoof Behemoth", "Utopia Sprawl",
        "Titan of Industry", "Primeval Titan", "Priest of Titania", "Elvish Archdruid", "Nyxbloom Ancient",
        "Natural Order",
    ),
    "lands": (
        "Life from the Loam", "Crucible of Worlds", "Ramunap Excavator", "Azusa, Lost but Seeking",
        "Field of the Dead", "Titania, Protector of Argoth", "Dryad of the Ilysian Grove", "Splendid Reclamation",
        "Fastbond", "Crop Rotation", "Dark Depths", "Thespian's Stage", "Manabond", "Exploration",
    ),
}
# Core cards: strong cards that belong in a deck type without defining it (Lightning Bolt in red aggro, Force of
# Will in control). They count as members (CORE_MEMBERSHIP) so a bot in that deck type wants them more, but they
# are not keys: bots outside the deck type value them as usual.
CORE: Dict[str, tuple] = {
    "storm": ("Dark Ritual", "Cabal Ritual", "Rite of Flame", "Yawgmoth's Will", "Bolas's Citadel", "Time Spiral",
              "Thassa's Oracle", "Tainted Pact", "Necropotence", "Demonic Consultation"),
    "red_aggro": ("Lightning Bolt", "Chain Lightning", "Lava Dart", "Price of Progress"),
    "tempo": ("Lightning Bolt", "Force of Will", "Counterspell", "Brainstorm", "Ponder", "Preordain", "Daze",
              "Force of Negation", "Fire // Ice"),
    "control": ("Force of Will", "Counterspell", "Mana Drain", "Swords to Plowshares", "Solitude",
                "Jace, the Mind Sculptor", "Toxic Deluge", "Memory Lapse", "Cryptic Command"),
    "white_aggro": ("Swords to Plowshares", "Stoneforge Mystic", "Recruiter of the Guard", "Solitude"),
    "blink": ("Solitude", "Recruiter of the Guard", "Eternal Witness", "Venser, Shaper Savant", "Grief",
              "Fury", "Endurance", "Spellbook Seller"),
    "recursion": ("Eternal Witness", "Grief", "Fury", "Endurance", "Siege Rhino", "Bloodghast"),
    "pox": ("Dark Confidant", "Bloodghast", "Hymn to Tourach", "Thoughtseize", "Duress"),
    "ramp": ("Llanowar Elves", "Elvish Mystic", "Fyndhorn Elves", "Birds of Paradise", "Noble Hierarch",
             "Sylvan Caryatid"),
    "wildfire": ("Grim Monolith", "Mana Vault", "Basalt Monolith"),
    "welder": ("Triplicate Titan", "Blightsteel Colossus", "Myr Battlesphere"),
    "gruul": ("Lightning Bolt", "Minsc & Boo, Timeless Heroes", "Bloodbraid Elf"),
}
# Only coloured cards and mana rocks belong here: a colourless spell with this membership would count as narrow.
CORE_MEMBERSHIP = 0.6
# Role tags that make a card a key card of a deck type (from features.ROLE_PATTERNS), for cards not named above.
ROLE_KEYS = {"artifact_payoff": "artifacts", "storm_payoff": "storm", "reanimate": "reanimator",
             "cheat": "cheat", "land_recursion": "lands"}
DECK_TYPES = tuple(KEYS)
# Deck types that are built on artifacts (an artifact plan: extra rocks and utility artifacts are fine).
ARTIFACT_TYPES = ("tolarian", "workshop", "artifacts", "welder", "wildfire", "painter")

_KEY_NAMES: Dict[str, set] = {}
for _t, _names in KEYS.items():
    for _n in _names:
        _KEY_NAMES.setdefault(_n.lower(), set()).add(_t)
_CORE_NAMES: Dict[str, set] = {}
for _t, _names in CORE.items():
    for _n in _names:
        _CORE_NAMES.setdefault(_n.lower(), set()).add(_t)

# A card's membership in a deck type comes from the share of its CubeCobra partners (by strength) that
# are that deck type's key cards: Mishra's Bauble 15% artifact keys, Retrofitter Foundry 20% (members);
# Dismember 5% reanimator keys out of 100 partners, Skullclamp 7% artifact keys (drafted with everything).
SHARE_FROM = 0.04        # share of partners at which membership starts...
SHARE_FULL = 0.12        # ...and is full
MIN_KEY_STRENGTH = 1.5   # partner strength to key cards needed at all (cards with few known partners)


def _key_types(card: CardInfo) -> set:
    named = _KEY_NAMES.get(card.name.lower()) or _KEY_NAMES.get(card.name.split(" // ")[0].lower())
    if named:
        return set(named)
    return {t for role, t in ROLE_KEYS.items() if role in card.roles}


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
        core = _CORE_NAMES.get(info.name.lower()) or _CORE_NAMES.get(info.name.split(" // ")[0].lower()) or ()
        for t in core:
            if t not in info.key_of:
                deck[t] = max(deck.get(t, 0.0), CORE_MEMBERSHIP)
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


NARROW_MEMBERSHIP = 0.4   # deck-type membership that makes a colourless spell narrow (Top, Baubles)


def is_narrow(card: CardInfo, universal: bool, take_on_sight: bool) -> bool:
    """A card that only pays off in some decks: colourless key cards (Time Vault, Mox Opal, Lion's Eye
    Diamond), colourless spells whose partners tie them to a deck type (Top, Baubles, Retrofitter
    Foundry) and one-colour utility lands (Karakas, Tolarian Academy). Coloured spells are judged by their
    colours instead, and colourless cards drafted with everything (Dismember, Mental Misstep) aren't narrow."""
    if take_on_sight:
        return False
    if card.is_land:
        return bool(card.key_of) or (len(card.produces) == 1 and not universal)
    if card.need or card.hybrid or universal:
        return False
    if card.bomb and not card.key_of:
        return False
    return bool(card.key_of) or max(card.deck.values(), default=0.0) >= NARROW_MEMBERSHIP


KEY_WEIGHT = 1.0      # a key card: two make a full deck type
MEMBER_WEIGHT = 0.3   # a member card (Bauble for artifacts), scaled by membership
LEAN_WEIGHT = 0.5     # an open pick that still leans (Mana Vault -> Tolarian), scaled by membership:
                      # Mana Vault is half a key, a Mox a small nudge, Sol Ring and Lotus mostly open
LEAN_CAP = 0.6        # most that open picks add up to (a little more than one Mana Vault)


def deck_strength(pool: Iterable[CardInfo]) -> Dict[str, float]:
    """0..1 per deck type: how far a pool is into it. Key cards count fully (two make a full deck type),
    member cards and open picks that lean towards a deck type (Mana Vault) count partly."""
    raw = {t: 0.0 for t in DECK_TYPES}
    lean = {t: 0.0 for t in DECK_TYPES}
    for c in pool:
        open_pick = c.staple or c.bomb or (is_universal(c) and not c.key_of)
        for t in DECK_TYPES:
            if t in c.key_of:
                raw[t] += KEY_WEIGHT
            elif t in c.deck:
                if open_pick:
                    lean[t] += LEAN_WEIGHT * c.deck[t]
                else:
                    raw[t] += MEMBER_WEIGHT * c.deck[t]
    # Open picks lean, but a pile of mana rocks doesn't make a deck type: only key cards and members do.
    return {t: min(1.0, (raw[t] + min(lean[t], LEAN_CAP)) / 2.0) for t in DECK_TYPES}
