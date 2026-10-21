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
from .decktypes import DECK_TYPES, deck_strength, is_narrow, is_universal
from .features import COLORS, CardInfo
from .personas import Persona

TUNING: Dict[str, float] = {
    # colours
    # Commitment counts coloured spells owned, not picks: in a powered cube the first picks are often
    # Moxen, rocks and lands, which say nothing about colours.
    "commit_start": 2,          # coloured spells owned before colour preference starts to matter
    "commit_pick": 7,           # with this many coloured spells the bot is committed to two colours
    "flex_floor": 0.9,          # off-colour cards keep this share of their value while flexible...
    "committed_floor": 0.1,     # ...and this share once committed
    "openness_weight": 2.5,     # colour signals from the table (early picks only); tuned in simulations
    "rival_committed_floor": 0.3,  # how much a committed rival still wants an off-colour card (float risk);
                                # rivals who aren't committed yet want every colour (flex_floor), like the bot
    "rival_combo_finish": 1.0,  # a rival holding all but one piece of a combo very likely takes the last piece
    # splash
    "splash_min_value": 1.2,    # owned power in the third colour before a splash is considered
    "splash_fit": 0.6,          # how on-colour splash cards count once the splash is real
    "splash_fixing_bonus": 0.2, # value of a land that fixes the splash (until the bot owns splash_fixing_target)
    "splash_fixing_target": 2,
    # fixing (basic lands come from outside the draft, so a two-colour deck needs only a few duals)
    "early_fixing_damp": 0.5,   # dual/fetch lands count at 50% power at pick 1, full by mid-draft
    "fixing_bonus": 0.15,       # late-draft value of an on-colour dual/fetch
    "fixing_target": 3,         # duals/fetches a deck would like
    # synergy
    "combo_base": 0.35, "combo_growth": 0.45,
    "combo_rest_share": 0.25,   # a card's other combo lines add only this share (its best line counts in full)
    "combo_max_pieces": 3,      # longer lines are too hard to assemble in a draft to plan around
    "combo_finish_weight": 0.8, # combo weight for the last piece of a line we hold (any time in the draft)
    "partner_weight": 0.45,     # CubeCobra package partners (value when fully "in" a package)
    # synergy over rating: once a bot is committed (colours or deck type), what fits its deck counts for more
    # than raw Elo, so a high-rated card that only goes in other decks doesn't win on rating alone
    "commit_rating_cut": 0.25,  # share of the rating weight dropped when fully committed
    "fixing_partner_share": 0.3,  # duals and Talismans are drafted with every card of their colours: their
                                  # partners say "these colours" (colour fit covers that), not synergy
    "drafted_with_share": 0.5,  # "often drafted with" partners count this share (it's partly just popularity)
    # deck types (decktypes.py): narrow cards wait until the bot is in a deck that uses them
    "narrow_floor": 0.4,        # share of a narrow card's rating it keeps for a bot not (yet) in its deck type
    "key_floor": 0.55,          # ... the same for a coloured key card (Urza, Reanimate)
    "key_open": 0.7,            # a key card of a deck type nobody at the table is in: worth starting it
    "entry_window": 0.5,        # ...early on: starting a new deck type gets less appealing until this share of
                                # the bot's picks, when it stops (decide fairly early, then build)
    "deck_seat": 0.5,           # deck-type strength at which a seat counts as being in that deck type
    "contest_weight": 0.15,     # a deck type the bot shares with a rival: its key/member cards are worth this
                                # much more (if you fight for a lane, take the contested cards, not filler)
    "crowd_seats": 2,           # seats already in a deck type before it counts as crowded...
    "crowd_cut": 0.6,           # ...then a bot behind the deepest seat values its cards up to this much less
    "deck_focus": 0.3,          # a bot fully in a deck type: cards outside it lose up to this share...
    "focus_start": 0.5,         # ...starting from this deck-type strength
    "home_weight": 0.7,         # colourless non-mana cards (Top, Skullclamp): how much their home colours matter
    "home_floor": 0.3,          # ... never fitting less than this
    "style_weight": 1.0,        # colour-pair deck style nudge (after committing)
    # late needs / floating
    "needs_start": 0.45, "needs_slope": 1.8,
    "float_base": 0.25, "float_growth": 0.3, "float_cap": 0.6,
    "power_late_drop": 0.45,
    # win condition
    "wincon_start": 0.3,        # share of picks made before the bot checks it has a way to win
    "wincon_weight": 0.35,      # value of a strong threat for a deck with no win condition at all
    "wincon_combo_weight": 0.8, # only fairly popular combos count as a way to win (Spellbook weight 0.6-1)
    # payoffs that need support (Urza without artifacts, storm without rituals...)
    # plans: what a pool is building (Flash + fatties, fetches + landfall...) and leaning into it
    "plan_weight": 0.15,        # bonus for a card that fills a plan the pool has committed to
    "plan_conflict_cut": 0.75,  # payoffs for a weaker plan lose this share x (strongest plan - their plan)
    "plan_start": 4, "plan_full": 10,   # owned cards before plans start to matter / fully matter
    # land runs: once the table starts taking duals/fetches, everyone scrambles for them
    "run_window": 1.5,          # recent table picks looked at, in rounds (x seats)
    "run_share": 0.25,          # share of those picks being fixing lands that counts as a full run
    "run_boost": 0.6,           # fixing lands' rating boost during a full run (and no early-draft discount)
    "unsupported_cut": 0.7,     # share of such a card's rating lost when the pool has none of its support
    # reanimation spells need something to reanimate: owned fatties, or ones still likely to come
    "reanimate_cut": 0.6,       # share of a reanimation spell's rating lost with no target owned or available
    "reanimate_targets": 2,     # targets that make it fully live (owned count fully, available ones partly)
    # extra mana rocks: a deck without an artifact plan only needs a few
    "rock_limit": 3,            # mana artifacts owned before more of them lose value
    "rock_cut": 0.35,           # share of a 2+ mana rock's rating lost past the limit (no artifact plan)
    # sideboard / counter picks: answers to a deck someone at the table is building, late in the draft only
    "hate_start": 19,           # cards the bot owns before it looks at hate cards (its own 20th pick)
    "hate_full": 33,            # ... growing slowly to full by its 34th pick
    "hate_weight": 0.3,         # value of a hate card against a fully built target deck
    "hate_max": 4,              # hate cards a bot wants in all (sideboard space)
    "support_after": 6,         # picks before that cut fully applies (early picks keep options open)
}

# Payoff role -> (roles that support it, how many supporting cards make it fully live).
DEPENDENT_PAYOFFS: Dict[str, Tuple[Tuple[str, ...], int]] = {
    "artifact_payoff": (("artifact",), 4),
    "storm_payoff": (("ritual", "fast_mana"), 5),
    "flicker": (("etb",), 3),
    "equip_fetch": (("equipment",), 2),
    "land_recursion": (("fetchland", "landfall"), 3),
}
_DEPENDENT_ROLES = frozenset(DEPENDENT_PAYOFFS)

# Plans: (roles on one side, how many make that side complete, roles on the other side, how many).
# A pool's strength in a plan is half from each side, so a pool with Flash and no fatty is a half-built
# "cheat" plan that badly wants a fatty.
PLANS: Dict[str, Tuple[Tuple[str, ...], int, Tuple[str, ...], int]] = {
    "reanimator": (("reanimate",), 2, ("fatty",), 2),
    "cheat": (("cheat",), 1, ("fatty",), 2),
    "artifact_cheat": (("artifact_cheat",), 1, ("big_artifact",), 1),
    "artifacts": (("artifact",), 6, ("artifact_payoff",), 2),
    "storm": (("ritual", "fast_mana"), 4, ("storm_payoff",), 1),
    "blink": (("etb",), 4, ("flicker",), 2),
    "stoneforge": (("equip_fetch",), 1, ("equipment",), 2),
    "lands": (("fetchland", "land_sac", "extra_land"), 5, ("land_recursion", "landfall"), 2),
    "aristocrats": (("sac_outlet",), 1, ("death_payoff", "token_maker"), 3),
    "tokens": (("anthem",), 1, ("token_maker",), 4),
}
# The plan each "needs support" payoff belongs to (for the off-plan cut).
_PAYOFF_PLAN = {"artifact_payoff": "artifacts", "storm_payoff": "storm", "flicker": "blink",
                "equip_fetch": "stoneforge", "land_recursion": "lands"}


def land_run(ctx: "BotContext") -> float:
    """0..1: how hard the table is taking fixing lands right now (share of recent picks that were)."""
    seats = len(ctx.picks_by_seat) or 1
    window = int(round(ctx.k("run_window") * seats))
    start = max(0, ctx.pick_index - window)
    recent_slots = ctx.order[start:ctx.pick_index]
    if len(recent_slots) < seats:
        return 0.0
    # The window's picks are each seat's most recent ones. Only people's picks start a run: bots that
    # follow each other's fetch picks would set one off by themselves.
    per_seat: Dict[int, int] = {}
    for s in recent_slots:
        if ctx.people is None or s in ctx.people:
            per_seat[s] = per_seat.get(s, 0) + 1
    fixing = total = 0
    for s, m in per_seat.items():
        for cid in ctx.picks_by_seat.get(s, [])[-m:]:
            total += 1
            card = ctx.index.get(cid)
            if card and card.is_land and card.is_fixing:
                fixing += 1
    if fixing < 2:
        return 0.0                  # one fetch isn't a run
    return min(1.0, (fixing / max(total, 4)) / ctx.k("run_share"))


def plan_fill(role_counts: Dict[str, int]) -> Dict[str, Tuple[float, float]]:
    """Per plan: how complete each side is in this pool (0..1, 0..1)."""
    out = {}
    for name, (a_roles, a_need, b_roles, b_need) in PLANS.items():
        a = sum(role_counts.get(r, 0) for r in a_roles)
        b = sum(role_counts.get(r, 0) for r in b_roles)
        out[name] = (min(1.0, a / a_need), min(1.0, b / b_need))
    return out


def plan_strengths(fill: Dict[str, Tuple[float, float]]) -> Dict[str, float]:
    return {name: 0.5 * (fa + fb) for name, (fa, fb) in fill.items()}


def plan_value(card: CardInfo, fill: Dict[str, Tuple[float, float]], strengths: Dict[str, float]) -> float:
    """0..1: how much this card fills a plan the pool has started (more for the side that's missing)."""
    best = 0.0
    for name, (a_roles, _, b_roles, _) in PLANS.items():
        s = strengths[name]
        if s < 0.3:
            continue
        fa, fb = fill[name]
        if card.roles & set(a_roles):
            best = max(best, s * (0.4 + 0.6 * (1 - fa)))
        if card.roles & set(b_roles):
            best = max(best, s * (0.4 + 0.6 * (1 - fb)))
    return best


def plan_conflict(card: CardInfo, strengths: Dict[str, float]) -> float:
    """How far a payoff's own plan trails the pool's strongest other plan (0 = on plan)."""
    own_plans = {_PAYOFF_PLAN[r] for r in card.roles & _DEPENDENT_ROLES if r in _PAYOFF_PLAN}
    if not own_plans:
        return 0.0
    own = max(strengths[p] for p in own_plans)
    other = max((s for p, s in strengths.items() if p not in own_plans), default=0.0)
    return max(0.0, other - own)


def support_factor(card: CardInfo, role_counts: Dict[str, int], ramp: float, cut: float) -> float:
    """How much of a payoff's rating counts for this pool: full with enough support, down to (1 - cut)
    with none. A card with several payoff roles takes its best-supported one."""
    best = 0.0
    for role in card.roles & _DEPENDENT_ROLES:
        support, needed = DEPENDENT_PAYOFFS[role]
        have = sum(role_counts.get(r, 0) for r in support)
        best = max(best, min(1.0, have / needed))
    return 1.0 - cut * ramp * (1.0 - best)

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
    explain: bool = False                  # attach each card's score parts (for the bot report)
    people: Optional[FrozenSet[int]] = None  # seats drafted by people (None: treat every seat as a person)

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
        if len(card.produces) == 1:          # one-colour utility land (Karakas): fits decks of that colour
            return 1.0 if overlap else 0.0
        return 1.0 if overlap >= 2 or (len(lane) == 1 and overlap == 1) else (0.35 if overlap == 1 else 0.0)
    if not card.need and card.home:
        # Colourless card with a home: fits a lane holding a fair share of its partners' colours.
        inside = sum(card.home.get(c, 0.0) for c in lane)
        share = min(1.0, inside / (0.25 * len(lane)))
        return max(TUNING["home_floor"], 1.0 - TUNING["home_weight"] * card.home_evidence * (1.0 - share))
    return 1.0 if card.need <= lane else 0.0


_FIT_CACHE: Dict[tuple, Tuple[float, ...]] = {}


def _fit_vector(card: CardInfo) -> Tuple[float, ...]:
    # A card's home depends on the cube (its partners there), so it is part of the key.
    key = (card.id, tuple(sorted(card.home.items())), card.home_evidence) if card.home else (card.id,)
    vec = _FIT_CACHE.get(key)
    if vec is None:
        if len(_FIT_CACHE) > 50000:
            _FIT_CACHE.clear()
        vec = _FIT_CACHE[key] = tuple(_lane_fit(card, lane) for lane in LANES)
    return vec


def _dist_terms(dist: Dict[FrozenSet[str], float]) -> List[Tuple[int, float]]:
    """The lanes that matter in a distribution (index into LANES, probability), in LANES order."""
    return [(i, p) for i, p in enumerate(dist.values()) if p > 0.003]


def card_fit(card: CardInfo, dist: Dict[FrozenSet[str], float], terms: Optional[List[Tuple[int, float]]] = None) -> float:
    vec = _fit_vector(card)
    return sum(p * vec[i] for i, p in (terms if terms is not None else _dist_terms(dist)))


def fitter(index: Dict[str, CardInfo], dist: Dict[FrozenSet[str], float]):
    """card id -> fit for one lane distribution, worked out once per card (the scoring loops ask for
    the same cards many times over)."""
    terms = _dist_terms(dist)
    cache: Dict[str, float] = {}

    def fit_of(cid: str) -> float:
        v = cache.get(cid)
        if v is None:
            v = cache[cid] = card_fit(index[cid], dist, terms) if cid in index else 0.0
        return v
    return fit_of


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
    """A third colour is a real splash only if strong owned cards need it (and nothing beyond it).
    Lands don't count: a fetch or dual taken for its other colour says nothing about wanting this one."""
    best, best_v = None, 0.0
    for col in COLORS:
        if col in pair:
            continue
        v = sum(max(c.power, 0.0) for c in pool if not c.is_land and col in c.need and c.need <= pair | {col})
        if v > best_v:
            best, best_v = col, v
    return best if best_v >= k("splash_min_value") else None


# ---------------------------------------------------------------- synergy

_COLOURLESS_IDS: set = set()


def _colourless_piece(cid: str) -> bool:
    return cid in _COLOURLESS_IDS


def register_colourless(index: Dict[str, CardInfo]) -> None:
    """Remember which card ids are colourless spells (combo pieces that fit any deck)."""
    _COLOURLESS_IDS.update(cid for cid, c in index.items() if not c.need and not c.is_land)


def combo_value(card: CardInfo, owned: set, remaining: set, combos: List[Combo], fit_of,
                rest_share: float = TUNING["combo_rest_share"], max_pieces: float = TUNING["combo_max_pieces"]) -> float:
    """Value toward combos given owned pieces; a line counts only as much as its pieces fit our colours."""
    lines = []
    for ci in card.combos:
        combo = combos[ci]
        if len(combo.pieces) > max_pieces:
            continue
        others = [p for p in combo.pieces if p != card.id]
        have = sum(1 for p in others if p in owned)
        missing = [p for p in others if p not in owned]
        if any(p not in remaining for p in missing):
            continue
        progress = 0.06 if have == 0 else (have / len(others)) ** 1.2
        # Colourless pieces (Time Vault, a Key) go in any deck that runs the combo: only coloured ones limit it.
        fit = min((fit_of(p) for p in combo.pieces if not _colourless_piece(p)), default=1.0)
        lines.append(combo.weight * progress * (0.25 + 0.75 * fit))
    if not lines:
        return 0.0
    # The best line counts in full; the rest only add a little, so a card in many half-relevant
    # lines (Displacer Kitten in 20 Commander combos) doesn't outscore real cards.
    lines.sort(reverse=True)
    return min(lines[0] + rest_share * sum(lines[1:]), 1.4)


_PACKAGE_SETS = [(frozenset(enablers), frozenset(payoffs)) for _, enablers, payoffs in PACKAGES]


def package_strengths(role_counts: Dict[str, int]) -> List[Tuple[FrozenSet[str], float, FrozenSet[str], float]]:
    """Per package: (enabler roles, value of an enabler, payoff roles, value of a payoff) for a pool.
    Depends only on the pool, so it is worked out once per pick instead of once per card."""
    out = []
    for enablers, payoffs in _PACKAGE_SETS:
        out.append((enablers, 0.12 * min(sum(role_counts.get(r, 0) for r in payoffs), 3) / 3,
                    payoffs, 0.12 * min(sum(role_counts.get(r, 0) for r in enablers), 3) / 3))
    return out


def package_value(card: CardInfo, role_counts: Dict[str, int], strengths=None) -> float:
    total = 0.0
    for enablers, as_enabler, payoffs, as_payoff in (strengths if strengths is not None else package_strengths(role_counts)):
        if card.roles & enablers:
            total += as_enabler
        if card.roles & payoffs:
            total += as_payoff
    return min(total, 0.3)


def partner_sources(index: Dict[str, CardInfo], owned: Iterable[str]) -> set:
    """Owned cards whose CubeCobra partners count (everything but the universal staples)."""
    return {o for o in owned if o in index and not is_universal(index[o])}


def partner_value(card: CardInfo, owned: Iterable[str], fit_of, drafted_share: float = 1.0) -> float:
    """CubeCobra packages: how strongly this card goes with the (on-colour) cards we already own,
    based on what real drafters put together ("synergistic" partners have strength 1, "often drafted
    with" ones 0.5, scaled by drafted_share because that list is partly just popular cards).
    `owned` should be partner_sources(): universal staples like Sol Ring are drafted with everything."""
    if not card.partners:
        return 0.0
    total = sum((strength if strength >= 1.0 else strength * drafted_share) * fit_of(o)
                for o, strength in card.partners.items() if o in owned)
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

def pool_counts(pool: List[CardInfo]) -> Tuple[int, int, int, int]:
    """(interaction, creatures, cheap spells, 6+ drops) among a pool's spells."""
    spells = [c for c in pool if not c.is_land]
    return (sum(1 for c in spells if c.roles & {"removal", "counter", "sweeper"}),
            sum(1 for c in spells if c.is_creature),
            sum(1 for c in spells if c.cmc <= 2),
            sum(1 for c in spells if c.cmc >= 6))


def needs_value(card: CardInfo, pool: List[CardInfo], persona: Persona, counts=None) -> float:
    interaction, creatures, cheap, big = counts if counts is not None else pool_counts(pool)
    v = 0.0
    if card.roles & {"removal", "counter"} and interaction < 6:
        v += 0.14 * persona.w("interaction")
    if card.is_creature and creatures < 10:
        v += 0.08
    if not card.is_land and card.cmc <= 2 and cheap < 9:
        v += 0.07 * persona.w("curve")
    if not card.is_land and card.cmc >= 6 and big >= 3:
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


def deck_table(ctx: BotContext, rivals: List[int]) -> List[Dict[str, float]]:
    """Every rival's deck-type strengths."""
    return [deck_strength(ctx.index[c] for c in ctx.picks_by_seat.get(s, []) if c in ctx.index) for s in rivals]


def deck_outlook(ctx: BotContext, mine: Dict[str, float], others: List[Dict[str, float]]) -> Tuple[Dict[str, float], Dict[str, float]]:
    """(effective strength per deck type, how open each one is for starting it: 1 nobody in it, 0.5 one seat,
    0 two or more). A deck type with crowd_seats seats already in it is worth less to a bot that isn't
    leading it, so four seats don't chase one artifact drafter's cards."""
    k = ctx.k
    eff, open_ = {}, {}
    for t in DECK_TYPES:
        theirs = [o[t] for o in others]
        seats_in = sum(1 for v in theirs if v >= k("deck_seat"))
        leader = max(theirs, default=0.0)
        if seats_in >= k("crowd_seats") and leader > 0:
            # Fight or pivot: a bot about as deep as the deepest rival keeps fighting for the deck type's
            # cards; a shallow one backs off (and so moves to something more open).
            behind = max(0.0, 1.0 - mine[t] / leader)
            eff[t] = mine[t] * (1.0 - k("crowd_cut") * behind)
        else:
            eff[t] = mine[t]
        # One seat in it: less open the deeper that seat already is (0.5 at the threshold, 0.25 when full).
        open_[t] = 1.0 if seats_in == 0 else (0.5 * (1.5 - leader) if seats_in < k("crowd_seats") else 0.0)
    return eff, open_


def shared_types(ctx: BotContext, mine: Dict[str, float], others: List[Dict[str, float]]) -> Dict[str, float]:
    """Deck types this bot is in that a rival is in too: how far in the bot is (0 if not shared)."""
    k = ctx.k
    return {t: mine[t] for t in DECK_TYPES
            if mine[t] >= k("deck_seat") and any(o[t] >= k("deck_seat") for o in others)}


def deck_factor(ctx: BotContext, card: CardInfo, eff: Dict[str, float], open_: Dict[str, float],
                colour_q: float, entry: float = 1.0) -> float:
    """Share of its rating a card is worth to a seat, given what that seat's deck is (1 for most cards).
    Narrow cards (Top, Baubles, Karakas, Mox Opal) count fully only for a deck that uses them: one in their
    deck type, or (for cards that go by colour) a deck committed to their colour (`colour_q`). Coloured key
    cards (Urza, Reanimate, Ajani) lose some value outside their deck type. A key card of an open deck type
    is worth taking to start it, early in the draft (`entry` falls from 1 to 0 over entry_window)."""
    universal = is_universal(card)
    narrow = is_narrow(card, universal, card.staple)
    if not narrow and not card.key_of:
        return 1.0
    # Cards tied to a deck type (Baubles -> artifacts) wait for that deck type; others that go by colour
    # (Karakas, Top-like cards with no deck type) count once the bot is committed to their colour.
    tied = card.key_of or max(card.deck.values(), default=0.0) >= 0.5
    q = colour_q if narrow and (card.is_land or not tied) else 0.0
    for t, m in card.deck.items():
        q = max(q, eff[t] * m)
    for t in card.key_of:
        q = max(q, ctx.k("key_open") * open_[t] * entry)
    floor = ctx.k("narrow_floor") if narrow else ctx.k("key_floor")
    return floor + (1.0 - floor) * min(1.0, q)


def focus_factor(ctx: BotContext, card: CardInfo, mine: Dict[str, float]) -> float:
    """The deeper a bot is in a deck type, the more it takes what that deck needs instead of generically
    good cards: cards with no part in its strongest deck type lose value step by step (from deck-type
    strength focus_start, up to deck_focus when fully in). Interaction (removal, counterspells), staples
    and cards that go in every deck are always needed."""
    if not mine:
        return 1.0
    t, s = max(mine.items(), key=lambda kv: kv[1])
    ramp = min(1.0, max(0.0, (s - ctx.k("focus_start")) / (1.0 - ctx.k("focus_start"))))
    if not ramp or card.staple or is_universal(card) or card.roles & {"removal", "counter"}:
        return 1.0
    member = card.deck.get(t, 0.0)
    return 1.0 - ctx.k("deck_focus") * ramp * (1.0 - min(1.0, member / 0.5))


def commit_progress(ctx: BotContext, pool: List[CardInfo]) -> float:
    """0..1: how committed to colours a pool is (coloured spells owned, commit_start to commit_pick)."""
    k = ctx.k
    span = max(1.0, k("commit_pick") - k("commit_start"))
    return min(1.0, max(0.0, (coloured_spells(pool) - k("commit_start")) / span))


def rival_floor(ctx: BotContext, pool: List[CardInfo]) -> float:
    """How much a rival with this pool still wants an off-colour card: like the bot's own off-colour
    floor, generous until the rival owns a few coloured spells, then down to rival_committed_floor."""
    k = ctx.k
    return k("flex_floor") + (k("rival_committed_floor") - k("flex_floor")) * commit_progress(ctx, pool)


def completes_combo(card: CardInfo, owned: set, combos: List[Combo], max_pieces: float) -> bool:
    """True if taking this card finishes a combo line whose other pieces we already own."""
    for ci in card.combos:
        pieces = combos[ci].pieces
        if len(pieces) <= max_pieces and all(p in owned for p in pieces if p != card.id):
            return True
    return False


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
        strengths = package_strengths(_role_counts(pool))
        fit_of = fitter(ctx.index, dist)
        # A rival who isn't committed yet still wants every colour (as the bot itself does early on):
        # treating three blue picks as a blue drafter made Ragavan look like it would come back.
        floor = rival_floor(ctx, pool)
        partners_from = partner_sources(ctx.index, owned)
        r_deck = deck_strength(pool)
        r_eff, r_open = deck_outlook(ctx, r_deck, [deck_strength(ctx.index[c] for c in ctx.picks_by_seat.get(o, []) if c in ctx.index)
                                                     for o in ctx.picks_by_seat if o != seat])
        r_prog = commit_progress(ctx, pool)
        desires = sorted(((max(ctx.index[cid].power, 0.0) * (floor + (1 - floor) * fit_of(cid))
                           * deck_factor(ctx, ctx.index[cid], r_eff, r_open, r_prog * fit_of(cid))
                           + 0.8 * combo_value(ctx.index[cid], owned, remaining, ctx.combos, fit_of)
                           + package_value(ctx.index[cid], None, strengths)
                           + 0.3 * partner_value(ctx.index[cid], partners_from, fit_of, ctx.k("drafted_with_share"))
                           + (ctx.k("rival_combo_finish") if completes_combo(ctx.index[cid], owned, ctx.combos, ctx.k("combo_max_pieces")) else 0.0), cid)
                          for cid in plausible), reverse=True)
        spread = 1.0 + 0.35 * n_picks
        for rank, (_, cid) in enumerate(desires):
            if cid in cand_set:
                risk_keep[cid] *= 1.0 - 1.0 / (1.0 + math.exp((rank + 1 - n_picks - 0.5) / spread))
    return {cid: 1.0 - keep for cid, keep in risk_keep.items()}


# ---------------------------------------------------------------- the pick

def _is_rock(card: CardInfo) -> bool:
    return "mana" in card.roles and "artifact" in card.roles and not card.is_creature and not card.is_land


# ---------------------------------------------------------------- sideboard / counter picks

HATE_TARGETS = ("artifact", "graveyard", "counters", "creatures", "spells")


def deck_targets(pool: Iterable[CardInfo]) -> Dict[str, float]:
    """0..1 per kind of deck a sideboard card can answer: how far this pool is building it."""
    pool = list(pool)
    rc = _role_counts(pool)
    artifacts = sum(1 for c in pool if "artifact" in c.roles and not c.is_land)
    grave = rc.get("reanimate", 0) + 0.5 * rc.get("graveyard_cast", 0) + 0.3 * rc.get("self_mill", 0)
    storm = rc.get("ritual", 0) + 0.5 * rc.get("fast_mana", 0) + 2 * rc.get("storm_payoff", 0)
    clamp = lambda x: min(1.0, max(0.0, x))
    return {
        "artifact": clamp((artifacts - 4) / 5),        # every powered deck has a Mox or two; 9+ artifacts is a plan
        "graveyard": clamp((grave - 1) / 2),           # three reanimation spells is a reanimator deck
        "counters": clamp((rc.get("counter", 0) - 2) / 4),
        "creatures": clamp((rc.get("aggro_creature", 0) - 4) / 6),
        "spells": clamp((storm - 3) / 4),
    }


def table_targets(ctx: "BotContext", rivals: List[int]) -> Dict[str, float]:
    """How much the table offers each kind of sideboard card a target: the strongest rival deck of that
    kind counts in full, others add a little."""
    per = [deck_targets(ctx.index[c] for c in ctx.picks_by_seat.get(s, []) if c in ctx.index) for s in rivals]
    out = {}
    for t in HATE_TARGETS:
        vals = sorted((p[t] for p in per), reverse=True)
        out[t] = min(1.0, (vals[0] if vals else 0.0) + 0.25 * sum(vals[1:]))
    return out


def hate_value(card: CardInfo, table: Dict[str, float], own: Dict[str, float], owned_hate: Dict[str, int]) -> float:
    """0..1: how useful this card is as a sideboard answer at this table (never against our own plan)."""
    best = 0.0
    for t in HATE_TARGETS:
        if f"hate_{t}" in card.roles and own[t] < 0.5:     # no Null Rod for our own artifact deck
            best = max(best, table[t] / (1 + owned_hate.get(t, 0)))
    return best


def coloured_spells(pool: Iterable[CardInfo]) -> int:
    """How many owned cards say something about colours (non-land spells with coloured costs)."""
    return sum(1 for c in pool if c.need and not c.is_land)


def colour_state(ctx: BotContext, mine: List[CardInfo], n: int, rivals: List[int]):
    """Where the bot stands on colours: (lane distribution, committed pair or None, splash colour).
    Commitment follows coloured spells owned, not the pick number."""
    k = ctx.k
    col = coloured_spells(mine)
    t_open = 1 - min(1.0, n / max(ctx.picks_per_seat, 1)) * 1.6
    open_by_colour = openness(ctx, rivals)
    prior = {lane: k("openness_weight") * max(t_open, 0.0) * ctx.persona.w("openness")
             * sum(open_by_colour[c] for c in lane) / len(lane) for lane in LANES}
    dist = lane_distribution(mine, col, prior)
    pair = best_pair(mine, prior) if col >= k("commit_start") else None
    # A splash only once the two main colours are fairly settled (half way to committed).
    splash_from = k("commit_start") + 0.5 * (k("commit_pick") - k("commit_start"))
    splash = splash_colour(mine, pair, k) if pair and col >= splash_from else None
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
    progress = min(1.0, max(0.0, (coloured_spells(mine) - k("commit_start")) / span))
    floor = k("flex_floor") + (k("committed_floor") - k("flex_floor")) * progress
    fixing_owned = sum(1 for c in mine if c.is_land and pair and len(c.produces & pair) >= 2)

    terms = _dist_terms(dist)

    def fit_of_card(card: CardInfo) -> float:
        flexible = card_fit(card, dist, terms) if (pair is None or progress < 1.0) else 0.0
        if pair is None:
            return flexible
        committed = _lane_fit(card, pair)
        if splash and committed < 1.0:
            if card.is_land and splash in card.produces and card.produces & pair:
                committed = 1.0
            elif not card.is_land and card.need <= pair | {splash} and splash not in card.heavy:
                committed = k("splash_fit")      # single-pip splash cards only: no {B}{B} cards on a splash
        return committed if progress >= 1.0 else (1 - progress) * flexible + progress * committed

    fit_cache: Dict[str, float] = {}

    def fit_of(cid: str) -> float:
        if cid not in fit_cache:
            fit_cache[cid] = fit_of_card(ctx.index[cid]) if cid in ctx.index else 0.0
        return fit_cache[cid]

    role_counts = _role_counts(mine)
    partners_from = partner_sources(ctx.index, my_ids)
    strengths = package_strengths(role_counts)
    support_ramp = min(1.0, n / k("support_after"))
    fill = plan_fill(role_counts)
    plans = plan_strengths(fill)
    plan_ramp = min(1.0, max(0.0, (n - k("plan_start")) / max(1.0, k("plan_full") - k("plan_start"))))
    run = land_run(ctx)
    counts = pool_counts(mine)
    # Sideboard picks: from the bot's own ~20th pick, answers to decks being built at the table.
    hate_ramp = min(1.0, max(0.0, (n - k("hate_start") + 1) / max(1.0, k("hate_full") - k("hate_start") + 1)))
    owned_hate = {t: sum(1 for c in mine if f"hate_{t}" in c.roles) for t in HATE_TARGETS}
    if hate_ramp and sum(owned_hate.values()) < k("hate_max"):
        table, own_decks = table_targets(ctx, rivals), deck_targets(mine)
    else:
        hate_ramp = 0.0
    # Extra mana rocks: past a few, a deck with no artifact plan gets little from another one.
    rocks_owned = sum(1 for c in mine if _is_rock(c))
    rock_glut = rocks_owned >= k("rock_limit") and plans["artifacts"] < 0.5
    # A cheat/reanimator plan doesn't need to cast its fatties, and its deck types (worked out here because
    # the rating weight below depends on how committed the bot is).
    cheat_plan = max(plans["cheat"], plans["reanimator"])
    deck_mine = deck_strength(mine)
    others = deck_table(ctx, rivals)
    deck_eff, deck_open = deck_outlook(ctx, deck_mine, others)
    shared = shared_types(ctx, deck_mine, others)
    entry = max(0.0, 1.0 - t / k("entry_window"))
    commitment = max(progress, max(deck_mine.values(), default=0.0))
    w_power = (1.0 - k("power_late_drop") * t) * (1.0 - k("commit_rating_cut") * commitment) * p.w("power")
    # Reanimation spells: targets owned count fully, strong fatties still in the pool count a little each.
    owned_targets = sum(1 for c in mine if "fatty" in c.roles)
    open_targets = sum(1 for c in remaining if "fatty" in ctx.index[c].roles and ctx.index[c].power >= 0.5)
    target_fill = min(1.0, (owned_targets + 0.25 * open_targets) / k("reanimate_targets"))
    splash_fixing = sum(1 for c in mine if c.is_land and splash and splash in c.produces and pair and c.produces & pair) \
        if splash else 0
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
        if cheat_plan >= 0.3 and plan_ramp and ("fatty" in card.roles or ("big_artifact" in card.roles and plans["artifact_cheat"] >= 0.3)):
            fit = max(fit, 0.5 + 0.5 * cheat_plan)
        power = max(card.power, 0.0)
        if card.roles & _DEPENDENT_ROLES and support_ramp:
            power *= support_factor(card, role_counts, support_ramp, k("unsupported_cut"))
            if plan_ramp:
                power *= 1.0 - k("plan_conflict_cut") * plan_ramp * plan_conflict(card, plans)
        if rock_glut and _is_rock(card) and card.cmc >= 2:
            power *= 1.0 - k("rock_cut")
        if "reanimate" in card.roles and "fatty" not in card.roles and support_ramp:
            power *= 1.0 - k("reanimate_cut") * support_ramp * (1.0 - target_fill)
        d_mult = deck_factor(ctx, card, deck_eff, deck_open, progress * (_lane_fit(card, pair) if pair else 0.0),
                             entry) * focus_factor(ctx, card, deck_mine)
        power *= d_mult
        if card.is_land and card.is_fixing:
            damp = k("early_fixing_damp")
            # Spells first, fixing later... unless the table is in a land run: then they won't come back.
            power *= (damp + (1 - damp) * max(min(1.0, 2 * t), run)) * (1 + k("run_boost") * run)
        t_rating = w_power * power
        finishes = bool(card.combos) and completes_combo(card, owned, ctx.combos, k("combo_max_pieces"))
        t_combo = (max(w_combo, k("combo_finish_weight")) if finishes else w_combo) * combo_value(
            card, owned, remaining, ctx.combos, fit_of, k("combo_rest_share"), k("combo_max_pieces"))
        t_plan = package_value(card, None, strengths) + k("plan_weight") * plan_ramp * plan_value(card, fill, plans)
        if shared:
            # Fighting a rival for a deck type: its key and member cards come first.
            t_plan += k("contest_weight") * max(
                (s * (1.0 if dt in card.key_of else min(1.0, card.deck.get(dt, 0.0) / 0.5))
                 for dt, s in shared.items()), default=0.0)
        t_partner = k("partner_weight") * p.w("combo") * partner_value(card, partners_from, fit_of, k("drafted_with_share"))
        if card.is_fixing:
            t_partner *= k("fixing_partner_share")
        t_needs = w_needs * needs_value(card, mine, p, counts)
        t_hate = k("hate_weight") * hate_ramp * hate_value(card, table, own_decks, owned_hate) if hate_ramp else 0.0
        t_other = 0.0
        if wincon_gap:
            t_other += wincon_gap * threat_level(card) * min(1.0, 0.4 + max(card.power, 0.0))
        if pair:
            t_other += w_style * style_value(card, pair)
            if card.is_land and len(card.produces & pair) >= 2 and fixing_owned < k("fixing_target"):
                t_other += k("fixing_bonus") * t * (1.5 if fixing_owned == 0 and t > 0.5 else 1.0)
            if splash and card.is_land and splash in card.produces and card.produces & pair \
                    and splash_fixing < k("splash_fixing_target"):
                t_other += k("splash_fixing_bonus")
        base = t_rating + t_combo + t_plan + t_partner + t_needs + t_other + t_hate
        lane_mult = floor + (1 - floor) * fit
        info = {"fit": round(fit, 2)}
        if d_mult < 1.0:
            info["deck"] = round(d_mult, 2)
        if ctx.explain:
            info.update(rating=round(t_rating, 3), combo=round(t_combo, 3), plan=round(t_plan, 3),
                        partners=round(t_partner, 3), needs=round(t_needs, 3), other=round(t_other, 3), hate=round(t_hate, 3),
                        colour=round(lane_mult, 2))
        rows.append([base * lane_mult, cid, info])

    rows.sort(reverse=True)
    top = rows[:30]
    risk = float_risk(ctx, [r[1] for r in top], remaining)
    for r in top:
        # Never gamble on the last piece of our own combo coming back: a person can take it to stop us.
        if ctx.index[r[1]].combos and completes_combo(ctx.index[r[1]], owned, ctx.combos, k("combo_max_pieces")):
            risk[r[1]] = 1.0
        r[2]["risk"] = round(risk[r[1]], 2)
        mult = 1.0 - min(k("float_cap"), w_float) * (1.0 - risk[r[1]])
        r[0] *= mult
        if ctx.explain:
            r[2]["contested"] = round(mult, 2)          # < 1: likely to come back, so worth less now
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
