"""The pick engine: several oracles blended with phase-dependent weights.

Rotisserie drafts are fully open: every remaining card and every seat's picks are visible. Instead of
simulating hidden packs, each pick scores the whole remaining pool and models what the other seats are
likely to take before this seat's next turn ("float risk").

All tunable numbers live in TUNING so they can be adjusted (and tested in simulations) in one place.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

from . import archetypes as arch
from .combos import PACKAGES, Combo
from .features import COLORS, CardInfo
from .personas import Persona

TUNING: Dict[str, float] = {
    "lane_penalty_mono": 0.9,
    "lane_penalty_three": 0.74,    # a third colour has to earn its place...
    "three_colour_fixing": 0.35,   # ...and owned fixing for it is what earns it
    "lane_temp_start": 2.6, "lane_temp_slope": 0.09, "lane_temp_min": 0.45,
    "colour_crowding": 2.0,        # how strongly crowded colours are avoided
    "colour_supply": 0.5,
    "openness_weight": 1.6,        # colour signals feeding the lane prior
    "arch_crowding": 1.2,          # how strongly crowded archetypes are avoided
    "arch_weight": 0.22,           # archetype bonus per unit of relevance
    "arch_lane_support": 0.5,      # how much likely archetypes pull towards their usual colours
    "power_late_drop": 0.45,
    "combo_base": 0.35, "combo_growth": 0.45,
    "lane_floor_start": 0.9, "lane_floor_slope": 1.5, "lane_floor_min": 0.12,
    "needs_start": 0.45, "needs_slope": 1.8,
    "float_base": 0.25, "float_growth": 0.3, "float_cap": 0.6,
    "fixing_base": 0.08, "fixing_growth": 0.3,
    "package_unit": 0.12, "package_cap": 0.3, "package_urgency": 0.12, "package_urgency_cap": 0.45,
    "card_openness": 0.5,          # mid-draft: how much crowding deters moving INTO a colour
    "splash_threshold": 0.9,       # owned value in a third colour before it becomes a splash target
    "splash_fixing": 0.35,         # extra value for lands that fix the splash
    "splash_fit": 0.55,            # how "on colour" cards of the splash colour count
}

LANES: List[FrozenSet[str]] = (
    [frozenset(c) for c in COLORS]
    + [frozenset(p) for p in combinations(COLORS, 2)]
    + [frozenset(t) for t in combinations(COLORS, 3)]
)


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
    tuning: Optional[Dict[str, float]] = None

    def k(self, key: str) -> float:
        if self.tuning and key in self.tuning:
            return float(self.tuning[key])
        return TUNING[key]


# ---------------------------------------------------------------- lanes

def _lane_fit(card: CardInfo, lane: FrozenSet[str]) -> float:
    if card.is_land:
        if not card.produces:
            return 0.6                       # utility land: playable anywhere
        overlap = len(card.produces & lane)
        return 1.0 if overlap >= 2 or (len(lane) == 1 and overlap == 1) else (0.35 if overlap == 1 else 0.0)
    return 1.0 if card.need <= lane else 0.0


_FIT_CACHE: Dict[str, Tuple[float, ...]] = {}


def _fit_vector(card: CardInfo) -> Tuple[float, ...]:
    vec = _FIT_CACHE.get(card.id)
    if vec is None:
        vec = _FIT_CACHE[card.id] = tuple(_lane_fit(card, lane) for lane in LANES)
    return vec


def card_fit(card: CardInfo, dist: Dict[FrozenSet[str], float]) -> float:
    vec = _fit_vector(card)
    return sum(p * vec[i] for i, p in enumerate(dist.values()) if p > 0.003)


def lane_distribution(pool: Iterable[CardInfo], n_picks: int, prior: Optional[Dict[FrozenSet[str], float]] = None,
                      k=TUNING.get) -> Dict[FrozenSet[str], float]:
    """Probability over colour lanes given a pool. Starts nearly flat and sharpens as picks grow.

    Three-colour lanes are discounted unless the pool owns fixing for them, so a third colour is
    something a bot builds towards deliberately rather than drifts into for one card."""
    pool = list(pool)
    spells = [c for c in pool if not c.is_land]
    fixers = [c for c in pool if c.is_fixing]
    scores = {}
    for lane in LANES:
        s = sum(max(c.power, 0.05) for c in spells if c.need and c.need <= lane)
        s += 0.4 * sum(max(c.power, 0.05) for c in spells if not c.need)  # colourless fits everywhere
        if len(lane) == 1:
            s *= k("lane_penalty_mono")
        elif len(lane) == 3:
            s *= k("lane_penalty_three")
            # Only fixing that actually produces the splash colour (the lane colour with the least
            # spell support) helps a three-colour plan; an on-colour dual for the main pair doesn't.
            support = {c: sum(1 for sp in spells if c in sp.need) for c in lane}
            splash = min(lane, key=lambda c: (support[c], c))
            backing = sum(1 for f in fixers if splash in f.produces and len(f.produces & lane) >= 2)
            s += k("three_colour_fixing") * min(backing, 4)
        if prior:
            s += prior.get(lane, 0.0)
        scores[lane] = s
    temp = max(k("lane_temp_min"), k("lane_temp_start") - k("lane_temp_slope") * n_picks)
    top = max(scores.values())
    exps = {lane: math.exp((s - top) / temp) for lane, s in scores.items()}
    total = sum(exps.values())
    return {lane: e / total for lane, e in exps.items()}


def main_lane(pool: Iterable[CardInfo]) -> FrozenSet[str]:
    pool = list(pool)
    dist = lane_distribution(pool, len(pool))
    return max(dist, key=dist.get)


def splash_target(mine: List[CardInfo], lane: FrozenSet[str], owned: set, combos: List[Combo],
                  index: Dict[str, CardInfo], k=TUNING.get) -> Tuple[Optional[str], float]:
    """Is there a third colour worth splashing? Returns (colour, strength) or (None, 0).

    Value comes from owned spells that need exactly one colour beyond the main pair, plus combo
    lines that need that colour. A third colour is never ruled out: it becomes a target when enough
    of the pool depends on it, and from then on the bot looks for fixing to support it."""
    if len(lane) != 2:
        return None, 0.0
    best, best_v = None, 0.0
    for col in COLORS:
        if col in lane:
            continue
        wider = lane | {col}
        v = sum(max(c.power, 0.0) for c in mine if not c.is_land and col in c.need and c.need <= wider)
        for c in mine:
            for ci in c.combos:
                pieces = [index[p] for p in combos[ci].pieces if p in index]
                if any(col in pc.need for pc in pieces) and all(pc.need <= wider for pc in pieces):
                    v += 0.5 * combos[ci].weight
        if v > best_v:
            best, best_v = col, v
    if best_v < k("splash_threshold"):
        return None, 0.0
    return best, best_v


# ---------------------------------------------------------------- synergy

def combo_value(card: CardInfo, owned: set, remaining: set, combos: List[Combo], dist, index: Dict[str, CardInfo]) -> float:
    """Value of `card` toward combos, given the pieces this seat already owns.

    A line only counts as much as its pieces fit this seat's likely colours, so a bot that has
    settled into red-white stops chasing a blue combo piece."""
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
        fit = min(card_fit(index[p], dist) for p in combo.pieces if p in index)
        total += combo.weight * progress * (0.25 + 0.75 * fit)
    return min(total, 1.4)


def package_value(card: CardInfo, role_counts: Dict[str, int], k=TUNING.get) -> float:
    """Enabler/payoff packages. A pool that is heavy on one side makes the other side urgent:
    five reanimation spells and no big creature means the next fatty matters a lot."""
    total = 0.0
    for _, enablers, payoffs in PACKAGES:
        n_en = sum(role_counts.get(r, 0) for r in enablers)
        n_pay = sum(role_counts.get(r, 0) for r in payoffs)
        if card.roles & set(enablers):
            total += k("package_unit") * min(n_pay, 3) / 3
            total += min(k("package_urgency_cap"), k("package_urgency") * max(0, n_pay - 2 * n_en))
        if card.roles & set(payoffs):
            total += k("package_unit") * min(n_en, 3) / 3
            total += min(k("package_urgency_cap"), k("package_urgency") * max(0, n_en - 2 * n_pay))
    return min(total, k("package_cap") + k("package_urgency_cap"))


def _role_counts(pool: Iterable[CardInfo]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for c in pool:
        for r in c.roles:
            counts[r] = counts.get(r, 0) + 1
    return counts


# ---------------------------------------------------------------- needs (late draft)

def needs_value(card: CardInfo, pool: List[CardInfo], persona: Persona, lane: FrozenSet[str]) -> float:
    spells = [c for c in pool if not c.is_land]
    interaction = sum(1 for c in spells if c.roles & {"removal", "counter", "sweeper"})
    creatures = sum(1 for c in spells if c.is_creature)
    cheap = sum(1 for c in spells if c.cmc <= 2)
    fixing = sum(1 for c in pool if c.is_land and len(c.produces & lane) >= 2)
    v = 0.0
    if card.roles & {"removal", "counter"} and interaction < 6:
        v += 0.14 * persona.w("interaction")
    if card.is_creature and creatures < 10:
        v += 0.08
    if not card.is_land and card.cmc <= 2 and cheap < 9:
        v += 0.07 * persona.w("curve")
    if not card.is_land and card.cmc >= 6 and sum(1 for c in spells if c.cmc >= 6) >= 3:
        v -= 0.12                               # top-heavy enough already
    if card.is_land and len(card.produces & lane) >= 2 and fixing < 5:
        v += 0.18                               # mana for our colours
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
    """Positive for colours with plenty of good cards left and few rivals in them.

    Contest is measured in *drafters*: each rival counts towards the colours they are clearly in
    (weighted by how settled they are), so seven blue drafters read as very crowded."""
    supply = {c: 0.0 for c in COLORS}
    for cid in ctx.remaining:
        card = ctx.index[cid]
        if card.need and len(card.need) == 1 and not card.is_land:
            supply[next(iter(card.need))] += max(card.power, 0.0) ** 2
    mean_supply = sum(supply.values()) / 5 or 1.0
    contest = {c: 0.0 for c in COLORS}
    for seat in rivals:
        pool = [ctx.index[p] for p in ctx.picks_by_seat.get(seat, []) if p in ctx.index]
        coloured = sum(1 for c in pool if c.need and not c.is_land)
        settled = min(1.0, coloured / 8)
        for col, share in _colour_shares(pool).items():
            contest[col] += settled * min(1.0, share * 2.2)   # ~45%+ of their spells = "in" that colour
    expected = max(sum(contest.values()) / 5, 0.5)
    return {c: ctx.k("colour_supply") * (supply[c] / mean_supply - 1) - ctx.k("colour_crowding") * (contest[c] / expected - 1)
            for c in COLORS}


def archetype_crowding(ctx: BotContext, rivals: List[int]) -> Dict[str, float]:
    crowd = {name: 0.0 for name in arch.NAMES}
    for seat in rivals:
        pool = [ctx.index[p] for p in ctx.picks_by_seat.get(seat, []) if p in ctx.index]
        if len(pool) < 6:
            continue
        for name, p in arch.archetype_distribution(pool, len(pool)).items():
            crowd[name] += p
    expected = max(sum(crowd.values()) / len(crowd), 0.3)
    return {name: ctx.k("arch_crowding") * (v / expected - 1) for name, v in crowd.items()}


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


def _desire(card: CardInfo, owned: set, remaining: set, combos, dist, role_counts, index, adist) -> float:
    return (max(card.power, 0.0) * (0.3 + 0.7 * card_fit(card, dist))
            + 0.8 * combo_value(card, owned, remaining, combos, dist, index)
            + package_value(card, role_counts)
            + 0.15 * arch.card_archetype_bonus(card, adist))


def float_risk(ctx: BotContext, candidates: List[str], remaining: set) -> Dict[str, float]:
    """Probability each candidate is taken by someone else before our next pick."""
    window = picks_until_next_turn(ctx)
    if "end" in window:
        return {cid: 1.0 for cid in candidates}
    risk_keep = {cid: 1.0 for cid in candidates}
    cand_set = set(candidates)
    # Rivals rank only plausible cards: the strongest remaining cards plus our candidates and any
    # card that touches a combo. Far weaker cards can't push a candidate's rank down meaningfully.
    strongest = sorted(remaining, key=lambda c: -ctx.index[c].power)[:120]
    plausible = set(strongest) | cand_set | {c for c in remaining if ctx.index[c].combos}
    for seat, k in window.items():
        picks = [p for p in ctx.picks_by_seat.get(seat, []) if p in ctx.index]
        pool = [ctx.index[p] for p in picks]
        owned = set(picks)
        dist = lane_distribution(pool, len(pool))
        adist = arch.archetype_distribution(pool, len(pool))
        roles = _role_counts(pool)
        desires = sorted(((_desire(ctx.index[cid], owned, remaining, ctx.combos, dist, roles, ctx.index, adist), cid)
                          for cid in plausible), reverse=True)
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
    k = ctx.k
    my_ids = [c for c in ctx.picks_by_seat.get(ctx.seat, []) if c in ctx.index]
    mine = [ctx.index[c] for c in my_ids]
    owned = set(my_ids)
    remaining = set(c for c in ctx.remaining if c in ctx.index)
    n = len(mine)
    t = min(1.0, n / max(ctx.picks_per_seat, 1))          # draft phase 0..1

    rivals = [s for s in ctx.picks_by_seat if s != ctx.seat]
    crowd = {a: v * p.w("plan_crowding") for a, v in archetype_crowding(ctx, rivals).items()}
    # A preferred plan (forcers have a strong one) pulls hardest early and fades as the pool speaks.
    bias = {a: 4.0 * (p.w("arch_" + a) - 1) * (1.6 - t) for a in arch.NAMES}
    adist = arch.archetype_distribution(mine, n, crowd, bias)
    support = arch.lane_support(adist)
    open_by_colour = openness(ctx, rivals)
    prior = {}
    for lane in LANES:
        signal = sum(open_by_colour[c] for c in lane) / len(lane)
        prior[lane] = (k("openness_weight") * (1 - 0.6 * t) * p.w("openness") * signal
                       + k("arch_lane_support") * support.get(lane, 0.0))
    dist = lane_distribution(mine, n, prior, k)
    lane = max(dist, key=dist.get)
    roles = _role_counts(mine)
    splash, splash_strength = splash_target(mine, lane, owned, ctx.combos, ctx.index, k)

    w_power = (1.0 - k("power_late_drop") * t) * p.w("power")
    w_combo = (k("combo_base") + k("combo_growth") * min(1.0, 2 * t)) * p.w("combo")
    w_arch = k("arch_weight") * min(1.0, 0.3 + 1.4 * t)
    lane_floor = min(0.95, max(k("lane_floor_min"), k("lane_floor_start") - k("lane_floor_slope") * t) / p.w("lane"))
    w_needs = max(0.0, (t - k("needs_start")) * k("needs_slope"))
    w_float = (k("float_base") + k("float_growth") * min(1.0, 2 * t)) * p.w("float")
    entry_window = max(0.0, min(1.0, 4 * t) * (1.0 - 1.4 * t))   # strongest a quarter to half way in

    rows = []
    for cid in remaining:
        card = ctx.index[cid]
        fit = card_fit(card, dist)
        base = (w_power * max(card.power, 0.0)
                + w_combo * combo_value(card, owned, remaining, ctx.combos, dist, ctx.index)
                + package_value(card, roles, k)
                + w_arch * arch.card_archetype_bonus(card, adist)
                + w_needs * needs_value(card, mine, p, lane))
        if card.is_land and card.is_fixing:
            base += (k("fixing_base") + k("fixing_growth") * t) * fit   # duals in our colours matter more as we settle
        if splash:
            if card.is_land and splash in card.produces and card.produces & lane:
                base += k("splash_fixing") * min(1.5, splash_strength / k("splash_threshold"))
                fit = max(fit, 0.8)
            elif not card.is_land and splash in card.need and card.need <= lane | {splash}:
                fit = max(fit, k("splash_fit"))
        lane_mult = lane_floor + (1 - lane_floor) * fit
        if card.need and fit < 0.7 and entry_window > 0:
            # Moving into a new colour: crowded colours are less tempting, open ones more so.
            signal = max(-1.5, min(1.0, sum(open_by_colour[c] for c in card.need) / len(card.need)))
            lane_mult *= 1 + k("card_openness") * entry_window * (1 - fit) * signal
        rows.append([base * lane_mult, cid, {"fit": round(fit, 2)}])

    # Float risk only matters among plausible picks, so only compute it for the top of the list.
    rows.sort(reverse=True)
    top = rows[:30]
    risk = float_risk(ctx, [r[1] for r in top], remaining)
    for r in top:
        r[2]["risk"] = round(risk[r[1]], 2)
        r[0] *= 1.0 - min(k("float_cap"), w_float) * (1.0 - risk[r[1]])
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


def suggest_picks(ctx: BotContext, n: int = 3) -> List[Tuple[str, float]]:
    """Top-n cards for a seat (used later for the player pick helper)."""
    return [(cid, s) for s, cid, _ in score_pool(ctx)[:n]]
