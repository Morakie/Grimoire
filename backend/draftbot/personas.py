"""Hidden bot personalities and display names.

Personas only nudge oracle weights by roughly ±10–15%, so every bot stays a sound drafter; they add
draft-to-draft variety, not different skill levels. Names are picked independently of the persona.
"""
from __future__ import annotations

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

_NAMES = [
    "Ash", "Bram", "Cass", "Dov", "Edda", "Fen", "Gale", "Hollis", "Isa", "Jory", "Kestrel", "Lio",
    "Marlo", "Nyx", "Orrin", "Pell", "Quill", "Rook", "Sable", "Tamsin", "Ulric", "Vesper", "Wren",
    "Yara", "Zeke", "Bryn", "Corin", "Dace", "Elric", "Faye",
]


@dataclass
class Persona:
    archetype: str
    weights: Dict[str, float] = field(default_factory=dict)
    temperature: float = 0.05      # pick noise; lower = more decisive
    seed: int = 0

    def w(self, key: str) -> float:
        return self.weights.get(key, 1.0)

    def to_dict(self) -> dict:
        return {"archetype": self.archetype, "weights": self.weights, "temperature": self.temperature, "seed": self.seed}

    @staticmethod
    def from_dict(d: dict) -> "Persona":
        return Persona(d.get("archetype", "steady"), dict(d.get("weights", {})), float(d.get("temperature", 0.05)), int(d.get("seed", 0)))


def random_persona(rng: random.Random) -> Persona:
    archetype = rng.choice(list(_ARCHETYPES))
    weights = dict(_ARCHETYPES[archetype])
    # Small per-bot jitter on every weight so two bots of the same archetype still differ.
    for key in ("power", "lane", "combo", "openness", "float", "curve", "interaction"):
        weights[key] = round(weights.get(key, 1.0) * rng.uniform(0.95, 1.05), 3)
    # Drafting style (hidden): how the bot handles deck plans.
    #  - forcer:   picks a plan up front, leans into it, and is less put off when others contest it
    #  - flexible: stays open, reacts more to crowding and pivots readily (usually to a related plan)
    #  - steady:   in between
    from .archetypes import NAMES
    style = rng.choices(["steady", "forcer", "flexible"], weights=[0.5, 0.25, 0.25])[0]
    if style == "forcer":
        weights["arch_" + rng.choice(NAMES)] = round(rng.uniform(1.12, 1.2), 3)
        weights["plan_crowding"] = round(rng.uniform(0.5, 0.65), 3)
    elif style == "flexible":
        weights["plan_crowding"] = round(rng.uniform(1.2, 1.35), 3)
        weights["arch_" + rng.choice(NAMES)] = round(rng.uniform(1.02, 1.05), 3)
    else:
        weights["arch_" + rng.choice(NAMES)] = round(rng.uniform(1.03, 1.07), 3)
    weights["style_" + style] = 1.0
    return Persona(archetype, weights, temperature=rng.uniform(0.035, 0.06), seed=rng.randrange(1 << 30))


def bot_names(rng: random.Random, count: int, taken: List[str] = ()) -> List[str]:
    used = {t.lower().replace(" (bot)", "").strip() for t in taken}
    pool = [n for n in _NAMES if n.lower() not in used]
    rng.shuffle(pool)
    return [f"{n} (bot)" for n in pool[:count]]
