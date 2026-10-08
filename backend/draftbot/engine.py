"""The pick engine.

A rotisserie draft is one big face-up pack passed back and forth. Each pick, a bot scores every
remaining card from a few simple ingredients:

1. Power: CubeCobra Elo, normalised to the cube.
2. Colours: flexible for the first few picks, committed to two colours by about pick 10. After that,
   off-colour cards are mostly ignored. A third colour is allowed only as a deliberate splash: the bot
   already owns strong cards in it AND has (or takes) fixing for it.
3. Combos and packages: Commander Spellbook combos, CubeCobra "synergistic / often drafted with"
   partners (what real drafters put together), plus simple enabler/payoff pairs.
4. Fixing timing: spells first; dual/fetch lands for the bot's colours from mid-draft, urgently if short.
5. Deck style by colour pair: once committed, a light nudge towards what that pair usually does
   (e.g. white-red values cheap creatures and burn).
6. Float risk: cards nobody else will take before the bot's next turn can wait.
7. Win condition: from about a third of the way in, a deck with no combo line, too few threats and
   no aggro base gets a gentle push towards on-colour threats (creatures, planeswalkers, finishers).

Every number lives in TUNING so it can be explained and adjusted in one place.
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

TUNING: Dict[str, float] = {
    # colours
    "commit_start": 4,          # picks before colour preference starts to matter
    "commit_pick": 10,          # by this pick the bot is committed to two colours
    "flex_floor": 0.9,          # off-colour cards keep this share of their value while flexible...
    "committed_floor": 0.1,     # ...and this share once committed
    "openness_weight": 2.5,     # colour signals from the table (early picks only); tuned in simulations
    # splash
    "splash_min_value": 1.2,    # owned power in the third colour before a splash is considered
    "splash_fit": 0.6,          # how on-colour splash cards count once the splash is real
    "splash_fixing_bonus": 0.3, # value of a land that fixes the splash
    # fixing
    "early_fixing_damp": 0.5,   # dual/fetch lands count at 50% power at pick 1, full by mid-draft
    "fixing_bonus": 0.25,       # late-draft value of an on-colour dual/fetch
    "fixing_target": 5,         # duals/fetches a deck would like
    # synergy
    "combo_base": 0.35, "combo_growth": 0.45,
    "partner_weight": 0.3,      # CubeCobra package partners (value when fully "in" a package)
    "style_weight": 1.0,        # colour-pair deck style nudge (after committing)
    # late needs / floating
    "needs_start": 0.45, "needs_slope": 1.8,
    "float_base": 0.25, "float_growth": 0.3, "float_cap": 0.6,
    "power_late_drop": 0.45,
    # win condition
    "wincon_start": 0.3,        # share of picks made before the bot checks it has a way to win
    "wincon_weight": 0.35,      # value of a strong threat for a deck with no win condition at all
    "wincon_combo_weight": 0.8, # only fairly popular combos count as a way to win (Spellbook weight 0.6-1)
}

LANES: List[FrozenSet[str]] = (
    [frozenset(c) for c in COLORS]
    + [frozenset(p) for p in combinations(COLORS, 2)]
    + [frozenset(t) for t in combinations(COLORS, 3)]
)
PAIRS: List[FrozenSet[str]] = [frozenset(p) for p in combinations(COLORS, 2)]

# What each colour pair usually wants (role -> small bonus). A nudge, not a rulebook.
PAIR_STYLE: Dict[FrozenSet[str], Dict[str, float]] = {
    frozenset("WR"): {"aggro_creature": 0.15, "burn": 0.12, "equipment": 0.06, "cheap_threat": 0.05},
    frozenset("WU"): {"counter": 0.08, "sweeper": 0.1, "removal": 0.06, "planeswalker": 0.08, "draw": 0.05},
    frozenset("UB"): {"counter": 0.07, "reanimate": 0.1, "fatty": 0.08, "removal": 0.06, "draw": 0.05},
    frozenset("UR"): {"cantrip": 0.08, "spells_payoff": 0.12, "artifact_payoff": 0.08, "burn": 0.06, "counter": 0.05},
    frozenset("BR"): {"cheat": 0.12, "fatty": 0.08, "removal": 0.07, "aggro_creature": 0.06, "reanimate": 0.06},
    frozenset("RG"): {"ramp": 0.1, "finisher": 0.08, "aggro_creature": 0.08, "fatty": 0.05},
    frozenset("UG"): {"ramp": 0.1, "value_creature": 0.08, "draw": 0.06, "finisher": 0.05},
    frozenset("WB"): {"token_maker": 0.08, "sac_outlet": 0.1, "death_payoff": 0.1, "removal": 0.06, "aggro_creature": 0.06},
    frozenset("WG"): {"aggro_creature": 0.1, "token_maker": 0.07, "ramp": 0.06, "anthem": 0.06},
    frozenset("BG"): {"reanimate": 0.07, "self_mill": 0.06, "value_creature": 0.07, "removal": 0.07},
}


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


# ---------------------------------------------------------------- colours

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


def lane_distribution(pool: Iterable[CardInfo], n_picks: int, prior: Optional[Dict[FrozenSet[str], float]] = None) -> Dict[FrozenSet[str], float]:
    """Probability over colour lanes given a pool (used to judge flexibility and rivals' colours)."""
    pool = [c for c in pool if not c.is_land]
    scores = {}
    for lane in LANES:
        s = sum(max(c.power, 0.05) for c in pool if c.need and c.need <= lane)
        s += 0.4 * sum(max(c.power, 0.05) for c in pool if not c.need)
        s *= {1: 0.9, 2: 1.0, 3: 0.74}[len(lane)]
        if prior:
            s += prior.get(lane, 0.0)
        scores[lane] = s
    temp = max(0.45, 2.6 - 0.09 * n_picks)
    top = max(scores.values())
    exps = {lane: math.exp((s - top) / temp) for lane, s in scores.items()}
    total = sum(exps.values())
    return {lane: e / total for lane, e in exps.items()}


def best_pair(pool: Iterable[CardInfo], prior: Optional[Dict[FrozenSet[str], float]] = None) -> FrozenSet[str]:
    """The two colours this pool is best at (the commitment)."""
    pool = [c for c in pool if not c.is_land]

    def value(pair):
        v = sum(max(c.power, 0.05) for c in pool if c.need and c.need <= pair)
        v += 0.3 * sum(max(c.power, 0.05) for c in pool if not c.need)
        return v + (prior or {}).get(pair, 0.0)
    return max(PAIRS, key=value)


def splash_colour(pool: List[CardInfo], pair: FrozenSet[str], k) -> Optional[str]:
    """A third colour is a real splash only if strong owned cards need it (and nothing beyond it)."""
    best, best_v = None, 0.0
    for col in COLORS:
        if col in pair:
            continue
        v = sum(max(c.power, 0.0) for c in pool if not c.is_land and col in c.need and c.need <= pair | {col})
        if v > best_v:
            best, best_v = col, v
    return best if best_v >= k("splash_min_value") else None


# ---------------------------------------------------------------- synergy

def combo_value(card: CardInfo, owned: set, remaining: set, combos: List[Combo], fit_of) -> float:
    """Value toward combos given owned pieces; a line counts only as much as its pieces fit our colours."""
    total = 0.0
    for ci in card.combos:
        combo = combos[ci]
        others = [p for p in combo.pieces if p != card.id]
        have = sum(1 for p in others if p in owned)
        missing = [p for p in others if p not in owned]
        if any(p not in remaining for p in missing):
            continue
        progress = 0.06 if have == 0 else (have / len(others)) ** 1.2
        fit = min(fit_of(p) for p in combo.pieces)
        total += combo.weight * progress * (0.25 + 0.75 * fit)
    return min(total, 1.4)


def package_value(card: CardInfo, role_counts: Dict[str, int]) -> float:
    total = 0.0
    for _, enablers, payoffs in PACKAGES:
        if card.roles & set(enablers):
            total += 0.12 * min(sum(role_counts.get(r, 0) for r in payoffs), 3) / 3
        if card.roles & set(payoffs):
            total += 0.12 * min(sum(role_counts.get(r, 0) for r in enablers), 3) / 3
    return min(total, 0.3)


def partner_value(card: CardInfo, owned: Iterable[str], fit_of) -> float:
    """CubeCobra packages: how strongly this card goes with the (on-colour) cards we already own,
    based on what real drafters put together ("synergistic" counts double "often drafted with")."""
    if not card.partners:
        return 0.0
    total = sum(strength * fit_of(o) for o, strength in card.partners.items() if o in owned)
    return min(1.0, total / 3.0)


def _role_counts(pool: Iterable[CardInfo]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for c in pool:
        for r in c.roles:
            counts[r] = counts.get(r, 0) + 1
    return counts


def style_value(card: CardInfo, pair: FrozenSet[str]) -> float:
    style = PAIR_STYLE.get(pair, {})
    return min(0.25, sum(v for role, v in style.items() if role in card.roles))


# ---------------------------------------------------------------- late needs

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
        v -= 0.12
    return v


# ---------------------------------------------------------------- win condition

def threat_level(card: CardInfo) -> float:
    """How much a card can win a game on its own (0..1), from its type and text only."""
    if card.is_land:
        return 0.0
    if "planeswalker" in card.roles or "finisher" in card.roles:
        return 1.0
    if card.is_creature:
        if card.roles & {"aggro_creature", "value_creature"} or card.cmc >= 3:
            return 0.8
        return 0.5
    if "token_maker" in card.roles and card.cmc >= 2:
        return 0.5
    return 0.0


def win_plan(pool: List[CardInfo], fits, owned: set, remaining: set, combos: List[Combo],
             min_weight: float = TUNING["wincon_combo_weight"]) -> Tuple[float, str]:
    """How well this pool can actually win (0..1) and by which plan.

    Three ways to win, judged on cards the bot can cast:
      - combo: a combo line that is complete, or half done with the rest still available;
      - threats: about six creatures/planeswalkers that can take over a game (midrange, control);
      - aggro: about ten cheap attackers.
    The best of the three counts; a deck only needs one."""
    on = [c for c in pool if not c.is_land and fits(c) >= 0.6]
    threats = sum(threat_level(c) for c in on)
    cheap_attackers = sum(1 for c in on if c.is_creature and c.cmc <= 2)
    combo = 0.0
    for combo_line in combos:
        if combo_line.weight < min_weight:
            continue
        have = sum(1 for p in combo_line.pieces if p in owned)
        if not have:
            continue
        missing = [p for p in combo_line.pieces if p not in owned]
        if any(p not in remaining for p in missing):
            continue
        combo = max(combo, have / len(combo_line.pieces) if missing else 1.0)
    plans = {"combo": 1.0 if combo >= 1.0 else 0.6 * combo, "threats": min(1.0, threats / 6), "aggro": min(1.0, cheap_attackers / 10)}
    best = max(plans, key=plans.get)
    return plans[best], best


# ---------------------------------------------------------------- table signals

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
    """Positive for colours with good cards left and few rivals in them (rivals counted as drafters)."""
    supply = {c: 0.0 for c in COLORS}
    for cid in ctx.remaining:
        card = ctx.index[cid]
        if card.need and len(card.need) == 1 and not card.is_land:
            supply[next(iter(card.need))] += max(card.power, 0.0) ** 2
    mean_supply = sum(supply.values()) / 5 or 1.0
    contest = {c: 0.0 for c in COLORS}
    for seat in rivals:
        pool = [ctx.index[p] for p in ctx.picks_by_seat.get(seat, []) if p in ctx.index]
        settled = min(1.0, sum(1 for c in pool if c.need and not c.is_land) / 8)
        for col, share in _colour_shares(pool).items():
            contest[col] += settled * min(1.0, share * 2.2)
    expected = max(sum(contest.values()) / 5, 0.5)
    return {c: 0.5 * (supply[c] / mean_supply - 1) - (contest[c] / expected - 1) for c in COLORS}


# ---------------------------------------------------------------- float risk

def picks_until_next_turn(ctx: BotContext) -> Dict[int, int]:
    counts: Dict[int, int] = {}
    for slot in range(ctx.pick_index + 1, len(ctx.order)):
        seat = ctx.order[slot]
        if seat == ctx.seat:
            return counts
        counts[seat] = counts.get(seat, 0) + 1
    return {"end": 1}


def float_risk(ctx: BotContext, candidates: List[str], remaining: set) -> Dict[str, float]:
    """Probability each candidate is taken by someone else before our next pick."""
    window = picks_until_next_turn(ctx)
    if "end" in window:
        return {cid: 1.0 for cid in candidates}
    risk_keep = {cid: 1.0 for cid in candidates}
    cand_set = set(candidates)
    strongest = sorted(remaining, key=lambda c: -ctx.index[c].power)[:120]
    plausible = set(strongest) | cand_set | {c for c in remaining if ctx.index[c].combos}
    for seat, n_picks in window.items():
        picks = [p for p in ctx.picks_by_seat.get(seat, []) if p in ctx.index]
        pool = [ctx.index[p] for p in picks]
        owned = set(picks)
        dist = lane_distribution(pool, len(pool))
        roles = _role_counts(pool)

        def fit_of(cid, d=dist):
            return card_fit(ctx.index[cid], d) if cid in ctx.index else 0.0
        desires = sorted(((max(ctx.index[cid].power, 0.0) * (0.3 + 0.7 * card_fit(ctx.index[cid], dist))
                           + 0.8 * combo_value(ctx.index[cid], owned, remaining, ctx.combos, fit_of)
                           + package_value(ctx.index[cid], roles)
                           + 0.3 * partner_value(ctx.index[cid], owned, fit_of), cid) for cid in plausible), reverse=True)
        spread = 1.0 + 0.35 * n_picks
        for rank, (_, cid) in enumerate(desires):
            if cid in cand_set:
                risk_keep[cid] *= 1.0 - 1.0 / (1.0 + math.exp((rank + 1 - n_picks - 0.5) / spread))
    return {cid: 1.0 - keep for cid, keep in risk_keep.items()}


# ---------------------------------------------------------------- the pick

def colour_state(ctx: BotContext, mine: List[CardInfo], n: int, rivals: List[int]):
    """Where the bot stands on colours: (lane distribution, committed pair or None, splash colour)."""
    k = ctx.k
    t_open = 1 - min(1.0, n / max(ctx.picks_per_seat, 1)) * 1.6
    open_by_colour = openness(ctx, rivals)
    prior = {lane: k("openness_weight") * max(t_open, 0.0) * ctx.persona.w("openness")
             * sum(open_by_colour[c] for c in lane) / len(lane) for lane in LANES}
    dist = lane_distribution(mine, n, prior)
    pair = best_pair(mine, prior) if n >= k("commit_start") else None
    splash = splash_colour(mine, pair, k) if pair else None
    return dist, pair, splash


def score_pool(ctx: BotContext) -> List[Tuple[float, str, dict]]:
    """Score every remaining card for this seat. Returns (score, card_id, breakdown), best first."""
    p = ctx.persona
    k = ctx.k
    my_ids = [c for c in ctx.picks_by_seat.get(ctx.seat, []) if c in ctx.index]
    mine = [ctx.index[c] for c in my_ids]
    owned = set(my_ids)
    remaining = set(c for c in ctx.remaining if c in ctx.index)
    n = len(mine)
    t = min(1.0, n / max(ctx.picks_per_seat, 1))

    rivals = [s for s in ctx.picks_by_seat if s != ctx.seat]
    dist, pair, splash = colour_state(ctx, mine, n, rivals)

    # How much off-colour cards are discounted: generous early, strict once committed.
    span = max(1.0, k("commit_pick") - k("commit_start"))
    progress = min(1.0, max(0.0, (n - k("commit_start")) / span))
    floor = k("flex_floor") + (k("committed_floor") - k("flex_floor")) * progress
    fixing_owned = sum(1 for c in mine if c.is_land and pair and len(c.produces & pair) >= 2)

    def fit_of_card(card: CardInfo) -> float:
        flexible = card_fit(card, dist) if (pair is None or progress < 1.0) else 0.0
        if pair is None:
            return flexible
        committed = _lane_fit(card, pair)
        if splash and committed < 1.0:
            if card.is_land and splash in card.produces and card.produces & pair:
                committed = 1.0
            elif not card.is_land and card.need <= pair | {splash}:
                committed = k("splash_fit")
        return committed if progress >= 1.0 else (1 - progress) * flexible + progress * committed

    fit_cache: Dict[str, float] = {}

    def fit_of(cid: str) -> float:
        if cid not in fit_cache:
            fit_cache[cid] = fit_of_card(ctx.index[cid]) if cid in ctx.index else 0.0
        return fit_cache[cid]

    roles = _role_counts(mine)
    w_power = (1.0 - k("power_late_drop") * t) * p.w("power")
    w_combo = (k("combo_base") + k("combo_growth") * min(1.0, 2 * t)) * p.w("combo")
    w_needs = max(0.0, (t - k("needs_start")) * k("needs_slope"))
    w_float = (k("float_base") + k("float_growth") * min(1.0, 2 * t)) * p.w("float")
    w_style = k("style_weight") * progress

    # Win condition: once committed and past the early picks, a deck with no way to win
    # (no combo line, too few threats, no aggro base) leans towards on-colour threats.
    wincon_gap, plan = 0.0, None
    if pair and t >= k("wincon_start"):
        plan_score, plan = win_plan(mine, lambda c: fit_of(c.id), owned, remaining, ctx.combos,
                                    k("wincon_combo_weight"))
        ramp = min(1.0, (t - k("wincon_start")) / 0.25)
        wincon_gap = max(0.0, 1.0 - plan_score) * ramp * k("wincon_weight")

    rows = []
    for cid in remaining:
        card = ctx.index[cid]
        fit = fit_of(cid)
        power = max(card.power, 0.0)
        if card.is_land and card.is_fixing:
            damp = k("early_fixing_damp")
            power *= damp + (1 - damp) * min(1.0, 2 * t)    # spells first, fixing later
        base = (w_power * power
                + w_combo * combo_value(card, owned, remaining, ctx.combos, fit_of)
                + package_value(card, roles)
                + k("partner_weight") * p.w("combo") * partner_value(card, owned, fit_of)
                + w_needs * needs_value(card, mine, p))
        if wincon_gap:
            base += wincon_gap * threat_level(card) * min(1.0, 0.4 + max(card.power, 0.0))
        if pair:
            base += w_style * style_value(card, pair)
            if card.is_land and len(card.produces & pair) >= 2 and fixing_owned < k("fixing_target"):
                base += k("fixing_bonus") * t * (1.5 if fixing_owned < 2 and t > 0.5 else 1.0)
            if splash and card.is_land and splash in card.produces and card.produces & pair:
                base += k("splash_fixing_bonus")
        lane_mult = floor + (1 - floor) * fit
        rows.append([base * lane_mult, cid, {"fit": round(fit, 2)}])

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
    """Top-n cards for a seat (for a future player pick helper)."""
    return [(cid, s) for s, cid, _ in score_pool(ctx)[:n]]
