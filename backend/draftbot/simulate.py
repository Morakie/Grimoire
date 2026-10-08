"""Bot-only draft simulation, for tuning and sanity checks."""
from __future__ import annotations

import random
import time
from typing import Callable, Dict, List, Optional, Sequence

from .combos import Combo, attach_combos
from . import archetypes as arch
from .engine import BotContext, choose_pick, lane_distribution
from .features import CardInfo, build_card_index, castable
from .personas import Persona, bot_names, random_persona


def _final_lane(pool: List[CardInfo]):
    dist = lane_distribution(pool, len(pool))
    return max(dist, key=dist.get)


def run_draft(cube: List[dict], combos: List[Combo], order: Sequence[int], num_seats: int, picks_per_seat: int,
              seed: int = 0, greedy_seats: Sequence[int] = (),
              index: Optional[Dict[str, CardInfo]] = None, tuning: Optional[dict] = None) -> dict:
    """Run a full draft. Seats in `greedy_seats` just take the highest-Elo card (a baseline)."""
    rng = random.Random(seed)
    index = index or build_card_index(cube)
    attach_combos(index, combos)
    remaining = [cid for cid in index]
    picks: Dict[int, List[str]] = {s: [] for s in range(num_seats)}
    personas = {s: random_persona(rng) for s in range(num_seats)}
    names = bot_names(rng, num_seats)
    started = time.time()
    for slot, seat in enumerate(order):
        if not remaining:
            break
        if seat in greedy_seats:
            cid = max(remaining, key=lambda c: index[c].elo)
        else:
            ctx = BotContext(index, combos, remaining, picks, seat, order, slot, picks_per_seat, personas[seat], tuning)
            cid = choose_pick(ctx, rng)
        picks[seat].append(cid)
        remaining.remove(cid)
    elapsed = time.time() - started
    return {"picks": picks, "personas": personas, "names": names, "index": index, "seconds": elapsed}


def summarise(result: dict, combos: List[Combo]) -> List[dict]:
    index = result["index"]
    out = []
    for seat, ids in result["picks"].items():
        pool = [index[c] for c in ids]
        lane = _final_lane(pool)
        spells = [c for c in pool if not c.is_land]
        on_lane = [c for c in spells if castable(c, lane)]
        owned = set(ids)
        done = [[index[p].name for p in combo.pieces] for combo in combos if set(combo.pieces) <= owned]
        playables = sorted(on_lane, key=lambda c: -c.elo)[:23]
        out.append({
            "seat": seat,
            "name": result["names"][seat],
            "persona": result["personas"][seat].archetype,
            "plan": max((d := arch.archetype_distribution(pool, len(pool))), key=d.get),
            "lane": "".join(sorted(lane, key="WUBRG".index)),
            "on_lane_pct": round(100 * len(on_lane) / max(len(spells), 1)),
            "avg_elo_top23": round(sum(c.elo for c in playables) / max(len(playables), 1)),
            "lands_fixing": sum(1 for c in pool if c.is_land and c.is_fixing and len(c.produces & lane) >= 2),
            "deck_creatures": sum(1 for c in playables if c.is_creature),
            "deck_interaction": sum(1 for c in playables if c.roles & {"removal", "counter", "sweeper"}),
            "deck_avg_mv": round(sum(c.cmc for c in playables) / max(len(playables), 1), 2),
            "combos": done,
            "picks": [index[c].name for c in ids],
        })
    return out
