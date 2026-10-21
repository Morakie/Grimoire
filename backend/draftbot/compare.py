"""Compare pick engines on one pool: all-bot drafts with the same seeds, and the numbers that say whether the
bots draft the way the principles ask (docs/project-notes/bot-principles.md). Used from Bot Brain's browser
worker and from a shell; returns plain dicts.
"""
from __future__ import annotations

import time
from statistics import mean
from typing import Dict, List

from .decktypes import DECK_TYPES, deck_strength
from .engine import best_pair, coloured_spells
from .engine2 import is_interaction
from .features import castable
from .knowledge import LANE_CAPACITY
from .lab import simulate

WATCH = ("Black Lotus", "Ancestral Recall", "Time Walk", "Timetwister", "Mox Sapphire", "Sol Ring", "Mana Crypt",
         "Tolarian Academy", "Ragavan, Nimble Pilferer", "Force of Will", "Demonic Tutor", "Balance",
         "Orcish Bowmasters", "The One Ring", "Sensei's Divining Top", "Karakas", "Skullclamp", "Urza's Bauble",
         "Underworld Breach", "Brain Freeze", "Lion's Eye Diamond", "Flash", "Worldspine Wurm", "Tinker",
         "Thassa's Oracle", "Demonic Consultation", "Null Rod", "Remand", "Counterspell", "Mana Drain",
         "Spell Pierce", "Underground Sea", "Polluted Delta", "Reanimate", "Griselbrand")


def run_metrics(index, combos, engine: str, seeds: List[int], seats: int = 8, picks: int = 45,
                personas: bool = True) -> dict:
    by_name = {c.name: cid for cid, c in index.items()}
    per_seed = []
    when: Dict[str, List[int]] = {n: [] for n in WATCH if n in by_name}
    started = time.time()
    for seed in seeds:
        r = simulate(index, combos, seats, picks, seed=seed, personas=personas, engine=engine)
        pools: Dict[int, List[str]] = {s: [] for s in range(seats)}
        for p in r["picks"]:
            pools[p["seat_index"]].append(p["card_id"])
            name = index[p["card_id"]].name
            if name in when:
                when[name].append(p["order"] + 1)
        main = []
        over = 0
        no_type = 0
        colours = []
        on_colour = []
        elo = []
        interaction = []
        for s, ids in pools.items():
            pool = [index[c] for c in ids]
            d = deck_strength(pool)
            t, v = max(d.items(), key=lambda kv: kv[1])
            if v >= 0.5:
                main.append(t)
            else:
                no_type += 1
            pair = best_pair(pool) if coloured_spells(pool) >= 2 else frozenset()
            spells = [c for c in pool if not c.is_land]
            on = [c for c in spells if not pair or castable(c, pair)]
            on_colour.append(len(on) / max(len(spells), 1))
            used = {col for c in on for col in c.need}
            colours.append(len(used))
            top = sorted(on, key=lambda c: -c.elo)[:23]
            elo.append(mean(c.elo for c in top) if top else 0)
            interaction.append(sum(1 for c in top if is_interaction(c)))
        for t in set(main):
            if main.count(t) > LANE_CAPACITY.get(t, 1):
                over += main.count(t) - LANE_CAPACITY.get(t, 1)
        per_seed.append({"over_capacity": over, "no_type": no_type, "distinct": len(set(main)),
                         "colours": mean(colours), "on_colour": mean(on_colour), "elo": mean(elo),
                         "interaction": mean(interaction), "main": sorted(main)})
    agg = {k: round(mean(x[k] for x in per_seed), 2) for k in ("over_capacity", "no_type", "distinct", "colours",
                                                               "on_colour", "elo", "interaction")}
    agg["seconds_per_draft"] = round((time.time() - started) / max(len(seeds), 1), 2)
    agg["avg_pick"] = {n: round(mean(v), 1) for n, v in when.items() if v}
    agg["undrafted"] = [n for n, v in when.items() if len(v) < len(seeds)]
    agg["main_types"] = [x["main"] for x in per_seed]
    return agg
