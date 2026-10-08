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
    return Persona(archetype, weights, temperature=rng.uniform(0.035, 0.06), seed=rng.randrange(1 << 30))


def bot_names(rng: random.Random, count: int, taken: List[str] = ()) -> List[str]:
    pool = [n for n in _NAMES if n.lower() not in {t.lower() for t in taken}]
    rng.shuffle(pool)
    return [f"{n} (bot)" for n in pool[:count]]
