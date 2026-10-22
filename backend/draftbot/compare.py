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
            # A seat's lane: the deck type it holds the most KEY cards of (two or more), else "good stuff".
            # Membership alone isn't a lane: a black control deck with Dark Ritual and Oracle isn't storm.
            keys = {t: sum(1 for c in pool if t in c.key_of) for t in DECK_TYPES}
            t, v = max(keys.items(), key=lambda kv: kv[1])
            if v >= 2:
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
        per_seed.append({"over_capacity": over, "good_stuff": no_type, "distinct": len(set(main)),
                         "colours": mean(colours), "on_colour": mean(on_colour), "elo": mean(elo),
                         "interaction": mean(interaction), "main": sorted(main)})
    agg = {k: round(mean(x[k] for x in per_seed), 2) for k in ("over_capacity", "good_stuff", "distinct", "colours",
                                                               "on_colour", "elo", "interaction")}
    agg["seconds_per_draft"] = round((time.time() - started) / max(len(seeds), 1), 2)
    agg["avg_pick"] = {n: round(mean(v), 1) for n, v in when.items() if v}
    agg["undrafted"] = [n for n, v in when.items() if len(v) < len(seeds)]
    agg["main_types"] = [x["main"] for x in per_seed]
    return agg


# ---------------------------------------------------------------- deck mix: what each deck type holds
# How many creatures, enablers, counters... a seat's first 40 picks hold, by its main deck type: human draft sheets
# against all-bot drafts. Cards outside the pool are skipped (and the rest scaled up to 40).
import csv
import io
from statistics import median

from . import engine2, rules as R
from .benchmark import name_index, resolve


def card_kind(c):
    t, r = c.types, c.roles
    if c.is_land: return "land"
    if c.name in R.CHEAT_ENABLERS or r & {"reanimate", "cheat"}: return "enabler"
    if "creature" in t: return "fatty" if "fatty" in r else "creature"
    if "planeswalker" in t: return "walker"
    if "counter" in r: return "counter"
    if r & {"removal", "sweeper"}: return "removal"
    if engine2._norm(c.name) in engine2._DISCARD: return "discard"
    if "ritual" in r: return "ritual"
    if "tutor" in r: return "tutor"
    if r & {"draw", "cantrip"}: return "draw"
    if "mana" in r: return "mana"
    if "artifact" in t: return "artifact"
    return "other"

def lane(IDX, ids):
    cnt = {}
    for c in ids:
        for d in IDX[c].key_of: cnt[d] = cnt.get(d, 0) + 1
    best = max(cnt.items(), key=lambda kv: kv[1], default=(None, 0))
    return best[0] if best[1] >= 2 else "good_stuff"

def seat_rows(IDX, pools, limit=40):
    NAMES = name_index(IDX)
    rows = []
    for names in pools:
        ids = [c for c in (resolve(NAMES, n) for n in names[:limit]) if c]
        if len(ids) < 0.6 * min(limit, len(names)): continue   # too many cards outside this pool
        mix = {}
        for c in ids: k = card_kind(IDX[c]); mix[k] = mix.get(k, 0) + 1
        scale = limit / len(ids)
        rows.append((lane(IDX, ids), {k: v * scale for k, v in mix.items()}))
    return rows

def sheet_pools(text):
    rows = list(csv.reader(io.StringIO(text)))
    n = len([x for x in rows[0][2:] if x.strip()])
    pools = [[] for _ in range(n)]
    for r in rows[1:]:
        if r and r[0].strip().isdigit():
            for k in range(n):
                if k + 2 < len(r) and r[k + 2].strip(): pools[k].append(r[k + 2].strip())
    return pools

def human_rows(IDX, sheets):
    """Deck mix of every seat in draft sheets (CSV text of each sheet's draft tab)."""
    out = []
    for t in sheets: out += seat_rows(IDX, sheet_pools(t))
    return out

def bot_rows(IDX, combos, seeds, engine="engine2"):
    out = []
    for seed in seeds:
        r = simulate(IDX, combos, 8, 45, seed=seed, personas=True, engine=engine)
        pools = {}
        for p in r["picks"]: pools.setdefault(p["seat_index"], []).append(IDX[p["card_id"]].name)
        out += seat_rows(IDX, list(pools.values()))
    return out

KINDS = ["creature", "fatty", "enabler", "counter", "removal", "discard", "ritual", "tutor", "draw", "mana",
        "artifact", "walker", "land", "other"]

def mix_table(rows):
    """Median count of each kind of card per deck type (first 40 picks)."""
    by = {}
    for l, m in rows: by.setdefault(l, []).append(m)
    return {l: {"n": len(ms), **{k: round(median(m.get(k, 0) for m in ms), 1) for k in KINDS}} for l, ms in by.items()}
