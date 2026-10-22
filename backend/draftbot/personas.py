"""Hidden bot personalities and display names.

Personas only nudge oracle weights by roughly ±10–15%, so every bot stays a sound drafter; they add
draft-to-draft variety, not different skill levels. Names are picked independently of the persona.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List

# Oracle weight multipliers per archetype (1.0 = neutral).
_ARCHETYPES: Dict[str, Dict[str, float]] = {
    "steady":    {},
    "combo":     {"combo": 1.15, "power": 0.95},
    "tempo":     {"curve": 1.12, "power": 1.0, "combo": 0.92},
    "signals":   {"openness": 1.15, "float": 1.1, "lane": 0.95},
    "power":     {"power": 1.08, "lane": 0.94},
    "control":   {"interaction": 1.12, "curve": 0.95},
}

_NAMES = [   # planeswalkers, first names only
    "Jace", "Liliana", "Garruk", "Ajani", "Chandra", "Nissa", "Gideon", "Sorin", "Teferi", "Karn", "Ugin",
    "Nahiri", "Elspeth", "Tezzeret", "Vraska", "Kiora", "Sarkhan", "Ral", "Kaya", "Tamiyo", "Narset",
    "Saheeli", "Domri", "Tibalt", "Ashiok", "Vivien", "Oko", "Wrenn", "Davriel", "Lukka", "Basri",
    "Calix", "Niko", "Tyvar", "Kaito", "Rowan", "Will", "Dovin", "Huatli", "Samut", "Dack", "Venser",
    "Koth", "Freyalise", "Aminatou", "Lolth", "Grist", "Quintorius", "Vronos",
]


@dataclass
class Persona:
    archetype: str
    weights: Dict[str, float] = field(default_factory=dict)
    temperature: float = 0.05      # pick noise; lower = more decisive
    seed: int = 0
    lean: str = ""                 # a deck type this bot leans towards early (no two bots at a table share one)

    def w(self, key: str) -> float:
        return self.weights.get(key, 1.0)

    def to_dict(self) -> dict:
        return {"archetype": self.archetype, "weights": self.weights, "temperature": self.temperature, "seed": self.seed,
                "lean": self.lean}

    @staticmethod
    def from_dict(d: dict) -> "Persona":
        return Persona(d.get("archetype", "steady"), dict(d.get("weights", {})), float(d.get("temperature", 0.05)),
                       int(d.get("seed", 0)), str(d.get("lean") or ""))


def random_persona(rng: random.Random) -> Persona:
    archetype = rng.choice(list(_ARCHETYPES))
    weights = dict(_ARCHETYPES[archetype])
    # Small per-bot jitter on every weight so two bots of the same archetype still differ.
    for key in ("power", "lane", "combo", "openness", "float", "curve", "interaction"):
        weights[key] = round(weights.get(key, 1.0) * rng.uniform(0.95, 1.05), 3)
    return Persona(archetype, weights, temperature=rng.uniform(0.035, 0.06), seed=rng.randrange(1 << 30))


def bot_names(rng: random.Random, count: int, taken: List[str] = ()) -> List[str]:
    used = {t.lower().replace(" (bot)", "").strip() for t in taken}
    pool = [n for n in _NAMES if n.lower() not in used]
    rng.shuffle(pool)
    return pool[:count]          # pages mark bots with an icon, so no "(bot)" in the name


def lean_choices(names) -> List[str]:
    """Deck types a cube can actually support: at least three of their key cards are in it (by card name)."""
    from .decktypes import DECK_TYPES, KEYS
    have = {str(n).lower() for n in names} | {str(n).split(" // ")[0].lower() for n in names}
    return [t for t in DECK_TYPES if sum(1 for k in KEYS[t] if k.lower() in have) >= lean_keys_needed(t)]


def lean_keys_needed(deck_type: str) -> int:
    """Key cards a cube must have before a bot may lean towards that deck type: at least 4, or 40% of the
    deck type's key list for the bigger lists (white aggro needs 8 of 19). Small two- and three-card combo
    types (Painter, Nadu) need all their pieces."""
    from .decktypes import KEYS
    n = len(KEYS[deck_type])
    return min(n, max(4, math.ceil(0.4 * n)))


def lean_fade(lean: str, decks: Dict[str, float], seat_in: float) -> float:
    """How much of a bot's lean is left (1 = all, 0 = none), from how far it is into each deck type. The lean
    only steers the start: once the bot is in another deck type (at least `seat_in` deep and deeper than the
    lean), it drafts what it is building and the personality's lean is dropped. Before that it fades as
    another deck type pulls ahead of the lean."""
    if not lean:
        return 0.0
    mine = decks.get(lean, 0.0)
    elsewhere = max((v for t, v in decks.items() if t != lean), default=0.0)
    if elsewhere >= seat_in and elsewhere > mine:
        return 0.0
    return max(0.0, 1.0 - 2.0 * max(0.0, elsewhere - mine))


def assign_leans(rng: random.Random, personas: List[Persona], choices: List[str], taken: List[str] = ()) -> None:
    """Give each persona a different deck type to lean towards (and skip ones already taken). With more bots
    than deck types, the rest lean nowhere."""
    pool = [t for t in choices if t not in set(taken)]
    rng.shuffle(pool)
    for p, t in zip(personas, pool + [""] * len(personas)):
        p.lean = t
