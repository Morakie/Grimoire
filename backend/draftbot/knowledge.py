"""Drafting knowledge from people, kept as data the engine reads (engine2.py).

Everything here comes from somewhere a person can check: LSV's rotisserie videos and his TCGplayer combo article
(Feb 2025), seven VRD rotisserie sheets from the owner's playgroup, and the owner's own notes
(docs/project-notes/bots.md). docs/project-notes/bot-principles.md lists the principles these support, and
backend/tests/test_principles.py checks that the bots follow them.

To teach the bots something: change the data here, run the principle tests, and note the source next to it.
Card names are matched case-insensitively on the front face; cards missing from a cube are simply ignored.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# ---------------------------------------------------------------- lanes
# How many seats a deck type can feed at one table before it hurts everyone in it (P4, P5).
# Narrow lanes (few key enablers) hold one drafter: LSV's contested storm went 3-6 while uncontested reanimator
# went 8-1 and uncontested Academy 8-0; in the VRD sheets Academy did worst when a Time Vault seat also fought for
# artifacts. Broad lanes (lots of good cards) hold two. Unlisted deck types hold one.
LANE_CAPACITY: Dict[str, int] = {
    "tolarian": 1, "workshop": 1, "artifacts": 1, "welder": 1, "wildfire": 1, "painter": 1,
    "storm": 1, "reanimator": 1, "cheat": 1, "twin": 1, "nadu": 1, "recursion": 1, "blink": 1,
    "pox": 1, "domain": 1, "ramp": 1, "lands": 1,
    "control": 2, "tempo": 2, "white_aggro": 2, "red_aggro": 2, "gruul": 1,
}
# Artifact deck types compete for the same cheap artifacts (Moxen, Baubles, Opal): two of them at one table
# behave like one crowded lane (LSV x6HSqjTfStE: two artifact neighbours both suffered; VRD sheets).
SHARED_LANES: Tuple[Tuple[str, ...], ...] = (("tolarian", "workshop", "artifacts"),)

# Seats a colour can feed as a main colour at an eight-seat table (playtester notes 2026-10-20 and the VRD
# sheets: blue ~5 decks, red ~4, black and white ~3, green ~2). Used to judge how crowded a colour is (P16).
COLOUR_CAPACITY: Dict[str, float] = {"U": 5.0, "R": 4.0, "B": 3.0, "W": 3.0, "G": 2.0}

# ---------------------------------------------------------------- card value in this format
# Rotisserie games are fast and decks are tuned (P11). Multipliers on a card's rating, from LSV's comments:
# one- and zero-mana counters are "a league above" two-mana ones, Force of Will beats Mana Drain, Ragavan gets
# better, Bowmasters, Remand, Reprieve, Skullclamp and Hullbreacher get worse, Karakas is "underwhelming".
ROTO_ADJUST: Dict[str, float] = {
    "Force of Will": 1.05, "Force of Negation": 1.04, "Spell Pierce": 1.06, "Daze": 1.03, "Mental Misstep": 1.04,
    "Pyroblast": 1.03, "Red Elemental Blast": 1.03, "Counterspell": 1.03, "Spell Snare": 1.05,
    "Thoughtseize": 1.03, "Inquisition of Kozilek": 1.03, "Swords to Plowshares": 1.03, "Strip Mine": 1.05,
    "Ragavan, Nimble Pilferer": 1.08, "Psychic Frog": 1.04, "Tamiyo, Inquisitive Student": 1.04,
    "Balance": 1.04, "Phelia, Exuberant Shepherd": 1.03,
    "Mana Drain": 0.97, "Memory Lapse": 0.95, "Mana Leak": 0.95, "Remand": 0.88, "Reprieve": 0.88,
    "Orcish Bowmasters": 0.92, "Skullclamp": 0.85, "Hullbreacher": 0.85, "Karakas": 0.9,
    "Broadside Bombardiers": 0.95,
}
# Spells costing this much or more are slow in roto unless the deck has fast mana (LSV: four-drops are good in
# decks with Moxen and Ancient Tomb, a lot worse without).
SLOW_CMC = 4
SLOW_CUT = 0.08          # share of rating a slow spell loses in a deck with no fast mana (none for finishers in
                         # a cheat/reanimator plan, which don't get cast)

# ---------------------------------------------------------------- how early people take cards
# Typical round (an eight-seat table's pick number per seat) by which people have taken a card, from seven VRD
# rotisserie sheets and LSV's tables. Engine 2 uses it to judge whether a card will still be there when the
# next person picks (P1, P2): a card people take in round 2 won't wait for round 4.
PICK_TIERS: Dict[int, Tuple[str, ...]] = {
    1: ("Black Lotus", "Ancestral Recall", "Time Walk", "Mox Sapphire", "Mox Jet", "Mox Ruby", "Mox Pearl",
        "Mox Emerald", "Mana Crypt", "Sol Ring", "Time Vault", "Gleemox"),
    2: ("Demonic Tutor", "Force of Will", "Tolarian Academy", "White Plume Adventurer", "Mana Vault",
        "Mox Diamond", "Minsc & Boo, Timeless Heroes", "Ancient Tomb", "Ragavan, Nimble Pilferer",
        "Thoughtseize", "Urza's Saga", "The One Ring"),
    3: ("Vampiric Tutor", "Force of Negation", "Karn, the Great Creator", "Grim Monolith", "Tinker", "Strip Mine",
        "Orcish Bowmasters", "Mana Drain", "Spell Pierce", "Forth Eorlingas!", "Psychic Frog", "Mental Misstep",
        "Hullbreacher", "Oko, Thief of Crowns", "Chrome Mox", "Timetwister", "Mox Opal", "Balance"),
    5: ("Inquisition of Kozilek", "Duress", "The Fantasticar", "Lotus Petal", "Seasoned Dungeoneer",
        "Teferi, Time Raveler", "Tamiyo, Inquisitive Student", "Swords to Plowshares", "Comet, Stellar Pup",
        "Mishra's Workshop", "Snapcaster Mage", "Lion's Eye Diamond", "Gitaxian Probe", "Wasteland", "Fastbond",
        "Thassa's Oracle", "Karakas", "Sensei's Divining Top", "Broadside Bombardiers",
        "Caves of Chaos Adventurer", "Reanimate", "Entomb", "Dark Ritual", "Underworld Breach",
        "Wheel of Fortune", "Flash"),
    8: ("Polluted Delta", "Scalding Tarn", "Flooded Strand", "Misty Rainforest", "Bloodstained Mire", "Arid Mesa",
        "Marsh Flats", "Verdant Catacombs", "Wooded Foothills", "Windswept Heath", "Prismatic Vista",
        "Brainstorm", "Ponder", "Preordain", "Mystical Tutor", "Fable of the Mirror-Breaker", "Lightning Bolt",
        "Imperial Seal", "Stock Up", "Counterspell", "Daze", "Pyroblast", "Red Elemental Blast",
        "Urza, Lord High Artificer", "Manifold Key", "Basalt Monolith", "Mishra's Bauble", "Urza's Bauble",
        "Wrenn and Six", "Lorien Revealed"),
    12: ("Underground Sea", "Volcanic Island", "Tundra", "Tropical Island", "Badlands", "Plateau", "Taiga",
         "Bayou", "Savannah", "Scrubland", "Voltaic Key", "Vexing Bauble", "Otawara, Soaring City",
         "City of Traitors", "Library of Alexandria", "Animate Dead", "Brain Freeze", "Grief", "Fury",
         "Solitude", "Atraxa, Grand Unifier", "Jace, Vryn's Prodigy", "Dack Fayden", "Sink into Stupor",
         "Boseiju, Who Endures", "Retrofitter Foundry"),
}

# ---------------------------------------------------------------- combo packages (P10)
# A package is a list of slots; every slot must be filled to win. Each slot lists the cards that fill it with
# how good each one is there (1 = best), and the slot's priority (how scarce it is: take it first).
# From LSV's article: Breach > Brain Freeze > Lion's Eye Diamond (Lotus Petal can stand in for LED); Flash wants
# Worldspine Wurm far above the rest, and Griselbrand is NOT a Flash target; Tinker wants Portal / Blightsteel /
# Triplicate Titan / Citadel; Lands decks must not strand Dark Depths without Thespian's Stage.
# (name, weight, [(priority, {card: quality})...])
Package = Tuple[str, float, List[Tuple[float, Dict[str, float]]]]
COMBO_PACKAGES: List[Package] = [
    ("breach", 1.0, [
        (1.0, {"Underworld Breach": 1.0}),
        (0.85, {"Brain Freeze": 1.0}),
        (0.6, {"Lion's Eye Diamond": 1.0, "Lotus Petal": 0.8}),
    ]),
    ("flash", 0.9, [
        (1.0, {"Flash": 1.0}),
        (0.8, {"Worldspine Wurm": 1.0, "Woodfall Primus": 0.8, "Atraxa, Grand Unifier": 0.8,
               "Triplicate Titan": 0.75, "Etali, Primal Conqueror": 0.75, "Ashen Rider": 0.6,
               "Archon of Cruelty": 0.6, "Protean Hulk": 0.8}),
    ]),
    ("tinker", 0.8, [
        (1.0, {"Tinker": 1.0}),
        (0.8, {"Portal to Phyrexia": 1.0, "Blightsteel Colossus": 0.95, "Triplicate Titan": 0.9,
               "Bolas's Citadel": 0.85, "Myr Battlesphere": 0.6, "Mindslaver": 0.6, "Sundering Titan": 0.55,
               "Kaldra Compleat": 0.55, "Memory Jar": 0.5}),
    ]),
    ("vault", 0.9, [
        (1.0, {"Time Vault": 1.0}),
        (0.9, {"Voltaic Key": 1.0, "Manifold Key": 1.0}),
    ]),
    ("oracle", 0.9, [
        (1.0, {"Thassa's Oracle": 1.0, "Jace, Wielder of Mysteries": 0.8, "Laboratory Maniac": 0.6}),
        (0.9, {"Demonic Consultation": 1.0, "Tainted Pact": 1.0}),
    ]),
    ("doomsday", 0.7, [
        (1.0, {"Doomsday": 1.0}),
        (0.9, {"Thassa's Oracle": 1.0, "Laboratory Maniac": 0.7}),
    ]),
    ("depths", 0.7, [
        (1.0, {"Dark Depths": 1.0}),
        (0.9, {"Thespian's Stage": 1.0, "Vampire Hexmage": 0.8}),
    ]),
    ("orb", 0.6, [
        (0.9, {"Zuran Orb": 1.0}),
        (1.0, {"Fastbond": 1.0, "Crucible of Worlds": 0.9, "Titania, Protector of Argoth": 0.8}),
    ]),
    ("sneak", 0.8, [
        (1.0, {"Sneak Attack": 1.0, "Show and Tell": 0.9, "Through the Breach": 0.8, "Natural Order": 0.7}),
        (0.8, {"Griselbrand": 1.0, "Emrakul, the Aeons Torn": 1.0, "Atraxa, Grand Unifier": 0.9,
               "Archon of Cruelty": 0.85, "Worldspine Wurm": 0.6}),
    ]),
    ("painter", 0.8, [
        (1.0, {"Painter's Servant": 1.0}),
        (1.0, {"Grindstone": 1.0}),
    ]),
    ("twin", 0.8, [
        (1.0, {"Splinter Twin": 1.0, "Kiki-Jiki, Mirror Breaker": 1.0}),
        (0.9, {"Deceiver Exarch": 1.0, "Pestermite": 1.0, "Zealous Conscripts": 0.7}),
    ]),
    ("draw_seven", 0.45, [   # punish the opponent's seven: fits aggro, control or combo
        (1.0, {"Orcish Bowmasters": 1.0, "Sheoldred, the Apocalypse": 1.0, "Hullbreacher": 0.9,
               "Narset, Parter of Veils": 0.8, "Leovold, Emissary of Trest": 0.8}),
        (0.8, {"Timetwister": 1.0, "Wheel of Fortune": 1.0, "Echo of Eons": 0.8, "Time Spiral": 0.8,
               "Memory Jar": 0.7, "Windfall": 0.6}),
    ]),
]

# More Vintage cube combos (2026-10-21). No Vintage-specific combo database exists that we found: edh-combos.com's
# Vintage page is Commander Spellbook filtered to Vintage-legal cards, which Grimoire already queries for every
# cube, but its weights come from Commander popularity. These are the lines that show up in powered cube and
# roto drafts (LSV's videos and article, common Vintage cube knowledge), weighted for cube play.
COMBO_PACKAGES += [
    ("thopter_sword", 0.75, [(1.0, {"Thopter Foundry": 1.0}), (1.0, {"Sword of the Meek": 1.0})]),
    ("kitten_jewel", 0.6, [(1.0, {"Displacer Kitten": 1.0}), (0.9, {"Coveted Jewel": 1.0})]),
    ("scepter", 0.6, [(1.0, {"Isochron Scepter": 1.0}), (1.0, {"Dramatic Reversal": 1.0})]),
    ("saheeli", 0.6, [(1.0, {"Saheeli Rai": 1.0}), (1.0, {"Felidar Guardian": 1.0})]),
    ("power_artifact", 0.7, [(1.0, {"Power Artifact": 1.0}),
                             (0.8, {"Grim Monolith": 1.0, "Basalt Monolith": 1.0})]),
    ("gadgeteer", 0.55, [(0.9, {"Forensic Gadgeteer": 1.0}), (0.9, {"Basalt Monolith": 1.0})]),
    ("rings", 0.45, [(0.9, {"Rings of Brighthearth": 1.0}), (0.9, {"Basalt Monolith": 1.0})]),
    ("salvagers", 0.6, [(1.0, {"Auriok Salvagers": 1.0}), (0.8, {"Lion's Eye Diamond": 1.0, "Black Lotus": 0.9})]),
    ("nadu", 0.7, [(1.0, {"Nadu, Winged Wisdom": 1.0}),
                   (0.8, {"Shuko": 1.0, "Lightning Greaves": 0.9, "Nomad's En-Kor": 0.9, "Skullclamp": 0.6})]),
    ("illusionist", 0.5, [(1.0, {"Cephalid Illusionist": 1.0}), (0.9, {"Shuko": 1.0, "Nomad's En-Kor": 1.0}),
                          (0.8, {"Thassa's Oracle": 1.0, "Dread Return": 0.8, "Narcomoeba": 0.6})]),
    ("chain_smog", 0.6, [(1.0, {"Chain of Smog": 1.0}), (1.0, {"Witherbloom Apprentice": 1.0})]),
    ("devoted", 0.55, [(1.0, {"Devoted Druid": 1.0}), (1.0, {"Vizier of Remedies": 1.0})]),
    ("worldgorger", 0.45, [(1.0, {"Worldgorger Dragon": 1.0}), (0.8, {"Animate Dead": 1.0, "Necromancy": 1.0})]),
    ("helm", 0.55, [(1.0, {"Helm of Obedience": 1.0}), (0.9, {"Rest in Peace": 1.0, "Leyline of the Void": 1.0})]),
    ("sanguine", 0.5, [(1.0, {"Sanguine Bond": 1.0}), (1.0, {"Exquisite Blood": 1.0})]),
    ("oath", 0.6, [(1.0, {"Oath of Druids": 1.0}),
                   (0.8, {"Griselbrand": 1.0, "Emrakul, the Aeons Torn": 1.0, "Atraxa, Grand Unifier": 0.8,
                          "Raph & Mikey, Troublemakers": 0.7})]),
    ("academy_wheel", 0.4, [(0.8, {"Tolarian Academy": 1.0}),
                            (0.6, {"Timetwister": 1.0, "Time Spiral": 1.0, "Wheel of Fortune": 0.8})]),
]

# ---------------------------------------------------------------- deck needs (P12)
# Hand disruption isn't a role read from rules text yet; these count as interaction alongside removal and
# counterspells.
DISCARD: Tuple[str, ...] = (
    "Thoughtseize", "Duress", "Inquisition of Kozilek", "Hymn to Tourach", "Unmask", "Grief", "Dread Fugue",
    "Cabal Therapy", "Mind Twist", "Collective Brutality", "Kitesail Freebooter", "Tidehollow Sculler",
    "Opposition Agent", "Dreams of Steel and Oil",
)
INTERACTION_TARGET = 6    # interaction cards (counters, removal, discard) a finished deck wants
