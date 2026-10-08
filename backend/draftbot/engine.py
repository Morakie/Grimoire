"""The pick engine: several oracles blended with phase-dependent weights.

Rotisserie drafts are fully open: every remaining card and every seat's picks are visible. Instead of
simulating hidden packs, each pick scores the whole remaining pool and models what the other seats are
likely to take before this seat's next turn ("float risk").
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

from .combos import PACKAGES, Combo
from .features import COLORS, CardInfo
from .personas import Persona

LANES: List[FrozenSet[str]] = (
    [frozenset(c) for c in COLORS]
    + [frozenset(p) for p in combinations(COLORS, 2)]
    + [frozenset(t) for t in combinations(COLORS, 3)]
)
_LANE_SIZE_PENALTY = {1: 0.9, 2: 1.0, 3: 0.86}   # three-colour decks need more fixing


@dataclass
class BotContext:
    index: Dict[str, CardInfo]
    combos: List[Combo]
    remaining: Sequence[str]               # undrafted card ids (custom cards already excluded)
    picks_by_seat: Dict[int, List[str]]    # every seat's picks so far, in order
    seat: int                              # the seat that is picking
    order: Sequence[int]                   # full pick order (seat per pick slot)
    pick_index: int                        # slot being picked now
    picks_per_seat: int
    persona: Persona = field(default_factory=lambda: Persona("steady"))


# ---------------------------------------------------------------- lanes

def _lane_fit(card: CardInfo, lane: FrozenSet[str]) -> float:
    if card.is_land:
        if not card.produces:
            return 0.6                       # utility land: playable anywhere
        overlap = len(card.produces & lane)
        return 1.0 if overlap >= 2 or (len(lane) == 1 and overlap == 1) else (0.35 if overlap == 1 else 0.0)
    return 1.0 if card.need <= lane else 0.0


def lane_distribution(pool: Iterable[CardInfo], n_picks: int, prior: Optional[Dict[FrozenSet[str], float]] = None) -> Dict[FrozenSet[str], float]:
    """Probability over colour lanes given a pool. Starts nearly flat and sharpens as picks grow."""
    pool = [c for c in pool if not c.is_land]
    scores = {}
    for lane in LANES:
        s = sum(max(c.power, 0.05) for c in pool if c.need and c.need <= lane)
        s += 0.4 * sum(max(c.power, 0.05) for c in pool if not c.need)  # colourless fits everywhere
        s *= _LANE_SIZE_PENALTY[len(lane)]
        if prior:
            s += prior.get(lane, 0.0)
        scores[lane] = s
    temp = max(0.45, 2.6 - 0.09 * n_picks)
    top = max(scores.values())
    exps = {lane: math.exp((s - top) / temp) for lane, s in scores.items()}
    total = sum(exps.values())
    return {lane: e / total for lane, e in exps.items()}


_FIT_CACHE: Dict[str, Tuple[float, ...]] = {}


def _fit_vector(card: CardInfo) -> Tuple[float, ...]:
    vec = _FIT_CACHE.get(card.id)
    if vec is None:
        vec = _FIT_CACHE[card.id] = tuple(_lane_fit(card, lane) for lane in LANES)
    return vec


def card_fit(card: CardInfo, dist: Dict[FrozenSet[str], float]) -> float:
    vec = _fit_vector(card)
    return sum(p * vec[i] for i, p in enumerate(dist.values()) if p > 0.003)


# ---------------------------------------------------------------- synergy

def combo_value(card: CardInfo, owned: set, remaining: set, combos: List[Combo], dist) -> float:
    """Value of `card` toward combos, given the pieces this seat already owns."""
    total = 0.0
    for ci in card.combos:
        combo = combos[ci]
        others = [p for p in combo.pieces if p != card.id]
        have = sum(1 for p in others if p in owned)
        missing = [p for p in others if p not in owned]
        if any(p not in remaining for p in missing):
            continue                           # a missing piece is gone: line is dead for us
        frac = have / len(others)
        progress = 0.06 if have == 0 else frac ** 1.2
        total += combo.weight * progress
    return min(total, 1.4)


def package_value(card: CardInfo, role_counts: Dict[str, int]) -> float:
    total = 0.0
    for _, enablers, payoffs in PACKAGES:
        if card.roles & set(enablers):
            have = sum(role_counts.get(r, 0) for r in payoffs)
            total += 0.12 * min(have, 3) / 3
        if card.roles & set(payoffs):
            have = sum(role_counts.get(r, 0) for r in enablers)
            total += 0.12 * min(have, 3) / 3
    return min(total, 0.3)


def _role_counts(pool: Iterable[CardInfo]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for c in pool:
        for r in c.roles:
            counts[r] = counts.get(r, 0) + 1
    return counts


# ---------------------------------------------------------------- needs (late draft)

def needs_value(card: CardInfo, pool: List[CardInfo], persona: Persona) -> float:
    spells = [c for c in pool if not c.is_land]
    interaction = sum(1 for c in spells if c.roles & {"removal", "counter", "sweeper"})
    creatures = sum(1 for c in spells if c.is_creature)
    cheap = sum(1 for c in spells if c.cmc <= 2)
    v = 0.0
    if card.roles & {"removal", "counter"} and interaction < 6:
        v += 0.14 * persona.w("interaction")
    if card.is_creature and creatures < 10:
        v += 0.08
    if not card.is_land and card.cmc <= 2 and cheap < 9:
        v += 0.07 * persona.w("curve")
    if not card.is_land and card.cmc >= 6 and sum(1 for c in spells if c.cmc >= 6) >= 3:
        v -= 0.12                               # top-heavy enough already
    return v


# ---------------------------------------------------------------- signals

def _colour_shares(pool: Iterable[CardInfo]) -> Dict[str, float]:
    counts = {c: 0.0 for c in COLORS}
    n = 0
    for card in pool:
        if card.is_land or not card.need:
            continue
        n += 1
        for col in card.need:
            counts[col] += 1.0 / len(card.need)
    return {c: (v / n if n else 0.0) for c, v in counts.items()}


def openness(ctx: BotContext, rivals: List[int]) -> Dict[str, float]:
    """Positive for colours with plenty of good cards left and few rivals in them."""
    supply = {c: 0.0 for c in COLORS}
    for cid in ctx.remaining:
        card = ctx.index[cid]
        if card.need and len(card.need) == 1 and not card.is_land:
            supply[next(iter(card.need))] += max(card.power, 0.0) ** 2
    mean_supply = sum(supply.values()) / 5 or 1.0
    contest = {c: 0.0 for c in COLORS}
    for seat in rivals:
        pool = [ctx.index[p] for p in ctx.picks_by_seat.get(seat, []) if p in ctx.index]
        for col, share in _colour_shares(pool).items():
            contest[col] += share
    mean_contest = sum(contest.values()) / 5 or 1.0
    return {c: 0.5 * (supply[c] / mean_supply - 1) - 0.5 * (contest[c] / mean_contest - 1) for c in COLORS}


# ---------------------------------------------------------------- float risk

def picks_until_next_turn(ctx: BotContext) -> Dict[int, int]:
    """How many picks each other seat makes before this seat's next turn."""
    counts: Dict[int, int] = {}
    for slot in range(ctx.pick_index + 1, len(ctx.order)):
        seat = ctx.order[slot]
        if seat == ctx.seat:
            return counts
        counts[seat] = counts.get(seat, 0) + 1
    return {"end": 1}  # no next turn: everything is "now or never"


def _desire(card: CardInfo, owned: set, remaining: set, combos, dist, role_counts) -> float:
    return (max(card.power, 0.0) * (0.3 + 0.7 * card_fit(card, dist))
            + 0.8 * combo_value(card, owned, remaining, combos, dist)
            + package_value(card, role_counts))


def float_risk(ctx: BotContext, candidates: List[str], remaining: set) -> Dict[str, float]:
    """Probability each candidate is taken by someone else before our next pick."""
    window = picks_until_next_turn(ctx)
    if "end" in window:
        return {cid: 1.0 for cid in candidates}
    risk_keep = {cid: 1.0 for cid in candidates}
    cand_set = set(candidates)
    for seat, k in window.items():
        picks = [p for p in ctx.picks_by_seat.get(seat, []) if p in ctx.index]
        pool = [ctx.index[p] for p in picks]
        owned = set(picks)
        dist = lane_distribution(pool, len(pool))
        roles = _role_counts(pool)
        desires = sorted(((_desire(ctx.index[cid], owned, remaining, ctx.combos, dist, roles), cid) for cid in remaining), reverse=True)
        spread = 1.0 + 0.35 * k
        for rank, (_, cid) in enumerate(desires):
            if cid in cand_set:
                p_take = 1.0 / (1.0 + math.exp((rank + 1 - k - 0.5) / spread))
                risk_keep[cid] *= (1.0 - p_take)
    return {cid: 1.0 - keep for cid, keep in risk_keep.items()}


# ---------------------------------------------------------------- the pick

def score_pool(ctx: BotContext) -> List[Tuple[float, str, dict]]:
    """Score every remaining card for this seat. Returns (score, card_id, breakdown), best first."""
    p = ctx.persona
    my_ids = [c for c in ctx.picks_by_seat.get(ctx.seat, []) if c in ctx.index]
    mine = [ctx.index[c] for c in my_ids]
    owned = set(my_ids)
    remaining = set(c for c in ctx.remaining if c in ctx.index)
    n = len(mine)
    t = min(1.0, n / max(ctx.picks_per_seat, 1))          # draft phase 0..1

    rivals = [s for s in ctx.picks_by_seat if s != ctx.seat]
    open_by_colour = openness(ctx, rivals)
    prior = {lane: 0.6 * (1 - t) * p.w("openness") * sum(open_by_colour[c] for c in lane) / len(lane) for lane in LANES}
    dist = lane_distribution(mine, n, prior)
    roles = _role_counts(mine)

    w_power = (1.0 - 0.45 * t) * p.w("power")
    w_combo = (0.35 + 0.45 * min(1.0, 2 * t)) * p.w("combo")
    lane_floor = min(0.95, max(0.12, 0.9 - 1.5 * t) / p.w("lane"))
    w_needs = max(0.0, (t - 0.45) * 1.8)
    w_float = (0.25 + 0.3 * min(1.0, 2 * t)) * p.w("float")

    rows = []
    for cid in remaining:
        card = ctx.index[cid]
        fit = card_fit(card, dist)
        base = (w_power * max(card.power, 0.0)
                + w_combo * combo_value(card, owned, remaining, ctx.combos, dist)
                + package_value(card, roles)
                + w_needs * needs_value(card, mine, p))
        if card.is_land and card.is_fixing:
            base += (0.08 + 0.25 * t) * fit           # duals in our colours matter more as we settle
        lane_mult = lane_floor + (1 - lane_floor) * fit
        rows.append([base * lane_mult, cid, {"fit": round(fit, 2)}])

    # Float risk only matters among plausible picks, so only compute it for the top of the list.
    rows.sort(reverse=True)
    top = rows[:30]
    risk = float_risk(ctx, [r[1] for r in top], remaining)
    for r in top:
        r[2]["risk"] = round(risk[r[1]], 2)
        r[0] *= 1.0 - min(0.6, w_float) * (1.0 - risk[r[1]])
    top.sort(reverse=True)
    return [(s, cid, info) for s, cid, info in top] + [(s, cid, info) for s, cid, info in rows[30:]]


def choose_pick(ctx: BotContext, rng: Optional[random.Random] = None) -> str:
    """Pick a card id. Usually the top score; occasionally a close runner-up (never a bad card)."""
    rng = rng or random.Random()
    scored = score_pool(ctx)
    if not scored:
        raise ValueError("No cards left to pick")
    best = scored[0][0]
    if best <= 0:
        return scored[0][1]
    close = [(s, cid) for s, cid, _ in scored[:5] if s >= 0.9 * best]
    temp = max(ctx.persona.temperature, 1e-3) * best
    weights = [math.exp((s - best) / temp) for s, _ in close]
    return rng.choices([cid for _, cid in close], weights=weights, k=1)[0]
