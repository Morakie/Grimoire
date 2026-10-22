"""Engine 2: pick the card you'd most regret not taking now.

Design and reasons: docs/project-notes/engine2.md. Principles it must keep: docs/project-notes/bot-principles.md,
checked by backend/tests/test_principles.py. Drafting knowledge (lane capacity, combo packages, roto card
adjustments, how early people take cards) lives in knowledge.py as data.

For the seat picking, every available card gets

    score = value x (keep + (1 - keep) x gone)

- value: how much the card improves this seat's likely final deck: quality (rating, adjusted for the format) x
  colour fit x plan fit, minus what a substitute still to come would give (replaceability), plus combo
  packages, CubeCobra links, deck needs (interaction, a win condition) and late sideboard answers;
- gone: the chance someone else takes it before this seat picks again, from each rival's own value of it
  (the bots model rivals the way they model themselves) and, for people, how early people usually take it;
- keep: how much a card that will still be there is worth taking now (1 near the end of the draft).

The interface matches engine.py (BotContext in, score_pool / choose_pick / suggest_picks out), so the Lab, the
bot report and the draft room can run either. Colour handling reuses engine.py's model.
"""
from __future__ import annotations

import dataclasses
import math
import random
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

from . import knowledge as K
from .lsv_drafts import DRAFTS as LSV_DRAFTS
from .pick_order import combined_order
from . import rules as R
from .decktypes import ARTIFACT_TYPES, DECK_TYPES, deck_strength, is_narrow, is_universal
from .engine import (BotContext, _is_rock, _is_utility_artifact, _lane_fit, best_pair, colour_state, coloured_spells,
                     combo_value, commit_progress, completes_combo, deck_targets, fitter, hate_value, lane_distribution,
                     partner_sources, partner_value, picks_until_next_turn, rival_floor, saturation_factor, table_targets,
                     threat_level, win_plan, HATE_TARGETS, _role_counts)
from .features import CardInfo, lookup_by_name

ENGINE = "engine2"

TUNING2: Dict[str, float] = {
    # the pick rule
    "keep": 0.5,                # share of its value a card that will come back is still worth taking now
    "rival_spread": 0.35,       # how sure the bots are about rivals' picks (lower = sharper)
    "people_prior": 1.0,       # weight of "people usually take this by round N" (knowledge.PICK_TIERS)
    "plausible": 150,           # strongest cards (by rating) each rival is assumed to consider, plus combo pieces
    # plans
    "deck_seat": 0.5,           # deck-type strength at which a seat is "in" that deck type
    "crowd_cut": 0.8,           # plan weight lost for a seat that would be over a lane's capacity
    "start_weight": 1.0,        # how much a key card of an open deck type counts as a plan to start...
    "entry_window": 0.5,        # ...fading to nothing by this share of the seat's picks
    "good_floor": 0.75,         # weight of the "good stuff" plan for a seat fully in a deck type
    "narrow_floor": 0.35,       # value a narrow card (Top, Baubles, Karakas) keeps outside a deck that uses it
    "key_floor": 0.45,          # ... a coloured key card (Reanimate, Ajani) outside its deck type
    "plan_bonus": 0.5,          # extra value for cards of the deck types a seat is in (synergy over raw rating)
    "plan_colour": 0.75,        # off-colour card (one new colour, single pip) fitting the seat's plan
    "lean_weight": 0.15,        # personality: a little extra for one deck type early on
    # value parts
    "partner_weight": 0.5,     # CubeCobra "drafted together" links to the seat's cards
    "combo_weight": 0.45,        # combo packages and Spellbook lines
    "replace_weight": 0.05,     # (0.35 by LSV's Balance-over-Drain remark; replaying his drafts says almost none)     # share of a substitute's value that a card loses (Balance has none, Drain has Counterspell)
    "fixing_damp": 0.8,         # dual/fetch lands' value at pick 1 (full once the seat is committed)
    "interaction_weight": 0.25, # deck short of interaction by mid-draft
    "wincon_start": 0.3, "wincon_weight": 0.3,
    "reanimate_cut": 0.6, "reanimate_targets": 2, "fatty_cut": 0.6, "fatty_enablers": 2, "fatty_cmc": 7,
    "open_support_share": 0.2,
    "saturation_cut": 0.5, "utility_limit": 2, "utility_cut": 0.4, "rock_limit": 3, "rock_cut": 0.35,
    # sideboard answers (P14): late, low weight, a few
    "hate_start": 19, "hate_full": 33, "hate_weight": 0.3, "hate_max": 4,
    "conspiracy_value": 0.0,
    "candidates": 60,           # cards per pick that get the full treatment (replaceability, gone)
    "generic_power": 0.9,       # cards rated this high (about the cube's top 5%) go in any deck of their colours:
                                # never discounted as a deck type's key card, never "replaceable" (P9: Ragavan,
                                # Demonic Tutor)
    # People's value of a card (pick_order.py: how early real rotisserie tables take it) against its CubeCobra
    # rating: experienced roto drafters take fetches, tutors, cheap discard and blasts much earlier than ratings
    # suggest, and Timetwister or Chrome Mox later.
    "mox_lean": 0.9,            # a one-colour Mox counts as this much of a card of its colour when choosing colours
    "fetch_fit": 0.75,          # colour fit a fetchland always has
    # Whose pick order counts most (owner, 2026-10-21): LSV's tables, then the VRD sheets, then the owner's group.
    # Weight per draft that took the card (pick_order.combined_order).
    "lsv_source": 24.0, "vrd_source": 1.0, "group_source": 0.2,   # held-out benchmark sweep 2026-10-21
    # LSV's conditional rules (rules.py): 1 = on, 0 = off.
    "rule_cheat_colour": 1.0,
    "rule_deck_mix": 1.0, "mix_slack": 1.0, "mix_cut": 0.15, "mix_land_boost": 0.06,
    "human_weight": 0.7,        # share of a card's quality that comes from how early people take it
    "human_top": 1.45, "human_floor": 0.2, "human_scale": 12.0,   # round 1 -> 1.45, round 10 -> ~0.8, never -> 0.2
}

_REANIMATE_ROLES = frozenset({"reanimate", "cheat"})

# The weights the Bot Lab offers for engine 2: (group, key, label, help, min, max, step).
KNOBS2: List[tuple] = [
    ("Pick rule", "keep", "Worth of a card that comes back", "How much of its value a card that will still be there next turn is worth taking now. Lower = more willing to float uncontested cards.", 0, 1, 0.05),
    ("Pick rule", "people_prior", "Trust people's pick order", "How much 'people usually take this by round N' counts toward a card being gone.", 0, 1, 0.05),
    ("Card value", "human_weight", "People's value vs rating", "Share of a card's value from how early real roto tables take it (rest: CubeCobra Elo).", 0, 1, 0.05),
    ("Card value", "replace_weight", "Substitutes lower value", "How much a card loses to a substitute still likely to be there (Counterspell for Mana Drain).", 0, 0.8, 0.05),
    ("Deck plans", "plan_bonus", "Synergy with the bot's deck", "Extra value for cards of the deck types the bot is in.", 0, 1.5, 0.05),
    ("LSV rules", "rule_cheat_colour", "Cheat targets ignore colour", "R1: a seat with Flash, Sneak Attack, Show and Tell, Oath or reanimation rates the creatures it puts into play as on-colour (Worldspine Wurm for a blue-black Flash deck). 0 = off.", 0, 1, 1),
    ("LSV rules", "rule_deck_mix", "Deck-type budgets", "R2: a seat ahead of what its deck type usually holds (creatures, enablers, removal...) values more of that kind less; short of lands, it values them more. 0 = off.", 0, 1, 0.25),
    ("Deck plans", "narrow_floor", "Narrow cards outside their deck", "Value Top, Baubles, Karakas keep for a committed bot not in a deck that uses them.", 0, 1, 0.05),
    ("Deck plans", "key_floor", "Key cards outside their deck", "Value Reanimate, Ajani keep for a committed bot outside their deck type.", 0, 1, 0.05),
    ("Deck plans", "crowd_cut", "Back off full lanes", "Plan value lost for a bot that would be one seat too many in a lane.", 0, 1, 0.05),
    ("Synergy", "partner_weight", "Drafted-together weight", "Value for cards CubeCobra drafters put with the bot's cards.", 0, 1.5, 0.05),
    ("Synergy", "combo_weight", "Combo weight", "Value of combo packages and combo lines.", 0, 1.5, 0.05),
    ("Colours", "mox_lean", "Moxen lean colours", "How much a one-colour Mox counts toward choosing that colour.", 0, 1, 0.05),
    ("Colours", "fetch_fit", "Fetchlands fit any deck", "Colour fit a fetchland always has.", 0, 1, 0.05),
    ("Other", "interaction_weight", "Find interaction", "Push towards removal, counters and discard for a deck short of them by mid-draft.", 0, 1, 0.05),
    ("Other", "hate_weight", "Sideboard answers", "Value of hate cards against a deck another seat is building (late only).", 0, 1, 0.05),
]


def k2(ctx: BotContext, key: str) -> float:
    if ctx.tuning and key in ctx.tuning:
        return float(ctx.tuning[key])
    return TUNING2[key]


# ---------------------------------------------------------------- what never changes for a cube

def _norm(name: str) -> str:
    return (name or "").split(" // ")[0].strip().lower()


_ADJUST = {_norm(n): v for n, v in K.ROTO_ADJUST.items()}
_TIER = {}
for _round, _names in sorted(K.PICK_TIERS.items(), reverse=True):
    for _n in _names:
        _TIER[_norm(_n)] = _round          # a card listed twice keeps its earliest round
_ORDER: Dict[str, Tuple[float, int]] = {}


def use_order(exclude: Optional[str] = None) -> None:
    """(Re)build people's pick order from all sources; `exclude` leaves one LSV draft out (the benchmark scores
    each draft with an order built without it)."""
    _ORDER.clear()
    _ORDER.update(combined_order(LSV_DRAFTS, TUNING2["lsv_source"], TUNING2["vrd_source"],
                                 TUNING2["group_source"], exclude))
    _STATIC.clear()


def human_quality(avg_round: float) -> float:
    """People's value of a card from the round it's usually taken in, on the same scale as CardInfo.power."""
    return TUNING2["human_floor"] + (TUNING2["human_top"] - TUNING2["human_floor"]) * math.exp(
        -(avg_round - 1.0) / TUNING2["human_scale"])
_DISCARD = {_norm(n) for n in K.DISCARD}


def job_of(card: CardInfo) -> str:
    """The job a card does in a deck, for replaceability: cards with the same job can stand in for each other.
    Power, bombs and the cube's very best cards have no stand-in."""
    if card.staple or card.bomb or card.power >= TUNING2["generic_power"]:
        return ""
    r = card.roles
    if card.is_land:
        return "fixing" if card.is_fixing else ""
    if "counter" in r:
        return "counter_cheap" if card.cmc <= 1 else "counter"
    if _norm(card.name) in _DISCARD:
        return "discard"
    if "sweeper" in r:
        return "sweeper"
    if "removal" in r:
        return "removal"
    if "cantrip" in r:
        return "cantrip"
    if "fast_mana" in r:
        return "fast_mana"
    if _is_rock(card):
        return "rock"
    if "tutor" in r:
        return "tutor"
    return ""


def is_interaction(card: CardInfo) -> bool:
    return bool(card.roles & {"removal", "counter", "sweeper"}) or _norm(card.name) in _DISCARD


class Static:
    """Per-card facts for one card index (one cube), worked out once."""

    def __init__(self, index: Dict[str, CardInfo]):
        self.index = index
        self.quality: Dict[str, float] = {}
        self.tier: Dict[str, int] = {}
        self.job: Dict[str, str] = {}
        self.narrow: Dict[str, bool] = {}
        self.universal: Dict[str, bool] = {}
        self.interaction: Dict[str, bool] = {}
        w = TUNING2["human_weight"]
        for cid, c in index.items():
            name = _norm(c.name)
            # Rating-only values live on the people's scale too: no card outranks Black Lotus on Elo alone.
            q = min(max(c.power, 0.0), TUNING2["human_top"])
            seen = _ORDER.get(name)
            if seen is None and name in _TIER:
                seen = (float(_TIER[name]), 0)          # hand-kept tiers (knowledge.PICK_TIERS) for cards with no data
            if seen is not None:
                # How early people take it (the people's value), blended with the rating.
                q = w * human_quality(seen[0]) + (1 - w) * q
                self.tier[cid] = seen[0]
            if c.staple and seen is None:
                q = max(q, human_quality(1.5))       # Power with no pick data: rate it like Power
            self.quality[cid] = q * _ADJUST.get(name, 1.0)
            self.job[cid] = job_of(c)
            uni = is_universal(c)
            self.universal[cid] = uni
            # Big fatties (Griselbrand, Emrakul) are only good in a deck that cheats them in: narrow like Top.
            big = "fatty" in c.roles and c.cmc >= TUNING2["fatty_cmc"] and not (c.staple or c.bomb)
            self.narrow[cid] = is_narrow(c, uni, c.staple) or big
            self.interaction[cid] = is_interaction(c)
        # Combo packages resolved to card ids: [(name, weight, [(priority, {cid: quality})])], and per card the
        # (package, slot) pairs it fills.
        by_name = lookup_by_name(index)
        self.pkgs: List[tuple] = []
        self.card_pkgs: Dict[str, List[Tuple[int, int]]] = {}
        for name, weight, slots in K.COMBO_PACKAGES:
            resolved = []
            for prio, alts in slots:
                ids = {}
                for n, q in alts.items():
                    cid = by_name.get(n.lower()) or by_name.get(_norm(n))
                    if cid:
                        ids[cid] = q
                resolved.append((prio, ids))
            if all(ids for _, ids in resolved):
                pi = len(self.pkgs)
                self.pkgs.append((name, weight, resolved))
                for si, (_, ids) in enumerate(resolved):
                    for cid in ids:
                        self.card_pkgs.setdefault(cid, []).append((pi, si))
        self.by_quality = sorted(index, key=lambda c: -self.quality[c])


_STATIC: List[Static] = []
use_order()


def static_for(index: Dict[str, CardInfo]) -> Static:
    for s in _STATIC:
        if s.index is index:
            return s
    s = Static(index)
    _STATIC[:] = [s]          # one cube at a time
    return s


def package_value(st: Static, cid: str, owned: set, remaining: set) -> Tuple[float, bool]:
    """(value 0..1 toward a combo package, whether this card completes one). The scarcest slot (highest
    priority) comes first; a second card for a slot already filled is a small backup; a package that can no
    longer be finished is worth nothing."""
    best, completes = 0.0, False
    for pi, si in st.card_pkgs.get(cid, ()):
        _, weight, slots = st.pkgs[pi]
        prio, alts = slots[si]
        q = alts[cid]
        filled = [any(a in owned for a in ids) for _, ids in slots]
        if filled[si]:
            best = max(best, 0.1 * weight * prio * q)
            continue
        others = [j for j in range(len(slots)) if j != si]
        if any(not filled[j] and not any(a in remaining for a in slots[j][1]) for j in others):
            continue
        have = sum(1 for j in others if filled[j])
        if have == len(others):
            completes = True
            v = weight * prio * q
        elif have == 0:
            v = 0.25 * weight * prio * q
        else:
            v = weight * prio * q * ((have + 1) / len(slots)) ** 1.2
        best = max(best, v)
    return best, completes


# ---------------------------------------------------------------- a seat's view of the draft

class SeatModel:
    """What one seat's pool says: its colours, its deck plans (with lane capacity), and how much it wants each
    card. Bots use the same model for themselves and for their rivals."""

    def __init__(self, ctx: BotContext, st: Static, seat: int, picks: Sequence[str],
                 others: List[Dict[str, float]], table: dict, me: bool):
        idx = ctx.index
        self.ctx, self.st, self.seat, self.me = ctx, st, seat, me
        self.pool = [idx[c] for c in picks if c in idx]
        self.owned = set(c for c in picks if c in idx)
        n = len(self.pool)
        self.t = min(1.0, n / max(ctx.picks_per_seat, 1))
        rivals = [s for s in ctx.picks_by_seat if s != seat]
        # A Mox says something about colours: drafters take "the Moxen of the colours I want" (LSV took Sapphire
        # and Jet, then drafted UB). For choosing colours (not for how committed the seat is), a one-colour Mox
        # counts as a weaker card of its colour.
        lean = [dataclasses.replace(c, need=frozenset(c.produces), power=c.power * k2(ctx, "mox_lean"))
                for c in self.pool if "fast_mana" in c.roles and not c.is_land and len(c.produces) == 1]
        colour_pool = self.pool + lean
        if me:
            self.dist, self.pair, self.splash = colour_state(ctx, colour_pool, n, rivals)
        else:
            col = coloured_spells(colour_pool)
            self.dist = lane_distribution(colour_pool, col)
            self.pair = best_pair(colour_pool) if col >= ctx.k("commit_start") else None
            self.splash = None
        self.progress = commit_progress(ctx, self.pool)
        # A pool with spells in only one colour hasn't chosen its second colour yet: best_pair still names one
        # (the first it tries), so cards of that colour must not count as committed (a mono-blue start would
        # otherwise "be" blue-white and want every white card).
        self.weak = ""
        if self.pair:
            counts = {c: sum(1 for x in colour_pool if not x.is_land and c in x.need) for c in self.pair}
            empty = [c for c, v in counts.items() if v == 0]
            if len(empty) == 1:
                self.weak = empty[0]
        k = ctx.k
        self.floor = (k("flex_floor") + (k("committed_floor") - k("flex_floor")) * self.progress) if me \
            else rival_floor(ctx, self.pool)
        self._flex = fitter(idx, self.dist)
        self._fit: Dict[str, float] = {}
        self.decks = deck_strength(self.pool)
        self.role_counts = _role_counts(self.pool)
        self.partners_from = partner_sources(idx, self.owned)
        self.fast_mana = any("fast_mana" in c.roles or c.staple for c in self.pool)
        self._plans(ctx, others)
        # Support counts for reanimation / big fatties (owned; the table's open ones come in `table`).
        self.owned_targets = sum(1 for c in self.pool if "fatty" in c.roles)
        self.owned_enablers = sum(1 for c in self.pool if c.roles & _REANIMATE_ROLES)
        # Enablers that don't go through the graveyard (Worldspine Wurm, Emrakul can't be reanimated).
        self.owned_cheaters = sum(1 for c in self.pool if "cheat" in c.roles
                                  or R.CHEAT_ENABLERS.get(c.name, "grave") != "grave")
        self.table = table
        art_plan = max(self.decks.get(t, 0.0) for t in ARTIFACT_TYPES)
        self.utility_glut = art_plan < 0.5 and sum(1 for c in self.pool if _is_utility_artifact(c)) >= k2(ctx, "utility_limit")
        self.rock_glut = art_plan < 0.5 and sum(1 for c in self.pool if _is_rock(c)) >= k2(ctx, "rock_limit")
        self.cheat_kinds = R.cheat_kinds(c.name for c in self.pool) if k2(ctx, "rule_cheat_colour") else set()
        self.kind_counts: Dict[str, int] = {}
        for c in self.pool:
            k = R.card_kind(c)
            self.kind_counts[k] = self.kind_counts.get(k, 0) + 1
        best = max(self.decks.items(), key=lambda kv: kv[1], default=("good_stuff", 0.0))
        self.main_deck = best[0] if best[1] >= 0.5 else "good_stuff"
        self.cheat_plan = max(self.decks.get("reanimator", 0.0), self.decks.get("cheat", 0.0))
        self._desire: Dict[str, tuple] = {}

    # ------------------------------------------------------------ plans and lanes
    def _plans(self, ctx: BotContext, others: List[Dict[str, float]]) -> None:
        """Plan weights: how far the seat is into each deck type, cut when it would be one seat too many for the
        lane (P4, P5), and how open each deck type is for starting it now (P15)."""
        seat_in = k2(ctx, "deck_seat")
        cut = k2(ctx, "crowd_cut")
        entry = max(0.0, 1.0 - self.t / max(k2(ctx, "entry_window"), 1e-6))
        group_of = {t: g for g in K.SHARED_LANES for t in g}
        self.weight: Dict[str, float] = {}
        self.open: Dict[str, float] = {}
        self.over: Dict[str, bool] = {}
        for t in DECK_TYPES:
            group = group_of.get(t, (t,))
            mine = max(self.decks.get(x, 0.0) for x in group) if len(group) > 1 else self.decks.get(t, 0.0)
            theirs = sorted((max(o.get(x, 0.0) for x in group) for o in others), reverse=True)
            cap = K.LANE_CAPACITY.get(t, 1)
            seats_in = [v for v in theirs if v >= seat_in]
            over = len(seats_in) >= cap and mine <= seats_in[cap - 1]
            self.over[t] = over
            s = self.decks.get(t, 0.0)
            self.weight[t] = s * (1.0 - cut) if over else s
            self.open[t] = (1.0 if not seats_in else (0.5 if len(seats_in) < cap else 0.0)) * entry
        lean = self.ctx.persona.lean if self.me else ""      # rivals' personalities are unknown
        self.lean = lean if lean in self.weight and not self.over.get(lean) else ""
        self.lean_w = k2(ctx, "lean_weight") * entry if self.lean else 0.0
        deepest = max(self.weight.values(), default=0.0)
        self.deepest = deepest
        self.good = 1.0 - (1.0 - k2(ctx, "good_floor")) * min(1.0, deepest)

    def plan_fit(self, cid: str, card: CardInfo) -> Tuple[float, str, float]:
        """(fit 0..~1.5 of the card to this seat's plans, the plan it fits best, how much it belongs to a deck
        type the seat is in). Strong generic cards always fit the "good stuff" plan (P7, P9); narrow cards and
        coloured key cards wait for a deck that uses them (P8)."""
        ctx, st = self.ctx, self.st
        seat_in = k2(ctx, "deck_seat")
        # Power, bombs, cards every deck plays and interaction always fit; but a narrow deck's key card that
        # happens to deal damage (Grapeshot) is still that deck's card.
        exempt = card.staple or card.bomb or st.universal[cid] or (st.interaction[cid] and not card.key_of)
        # Early on, a strong build-around is just a strong card (LSV's tables take Academy, Saga, Opal, LED, Flash
        # in the first rounds to plant a flag); the "only in some decks" discount grows as the seat commits to
        # something else (colours or a deck type).
        commit = min(1.0, max(self.progress, self.deepest / k2(ctx, "deck_seat")))
        if exempt:
            base = 1.0
        elif st.narrow[cid]:
            floor = k2(ctx, "narrow_floor") * self.good
            base = 1.0 - (1.0 - floor) * commit
        elif card.key_of and card.power < k2(ctx, "generic_power"):
            floor = k2(ctx, "key_floor")
            base = 1.0 - (1.0 - floor) * commit
        else:
            base = self.good
        use, best, syn = 0.0, "good stuff", 0.0
        for t, m in card.deck.items():
            w = self.weight.get(t, 0.0)
            u = min(1.0, w / seat_in) * min(1.0, m / 0.5)
            syn += w * m
            if u > use:
                use, best = u, t
        in_plan = use
        for t in card.key_of:
            u = k2(ctx, "start_weight") * self.open.get(t, 0.0)
            if self.lean == t:
                u += self.lean_w
            if u > use:
                use, best = u, t
        if self.lean and self.lean in card.deck and self.lean not in card.key_of:
            use = max(use, min(1.0, self.lean_w * card.deck[self.lean] / 0.5))
        fit = base + (1.0 - base) * min(1.0, use)
        fit *= 1.0 + k2(ctx, "plan_bonus") * min(1.0, syn)
        return fit, best, in_plan

    # ------------------------------------------------------------ colours
    def colour_fit(self, cid: str) -> float:
        v = self._fit.get(cid)
        if v is not None:
            return v
        card = self.ctx.index[cid]
        flexible = self._flex(cid) if (self.pair is None or self.progress < 1.0 or self.weak) else 0.0
        if self.pair is None:
            v = flexible
        else:
            committed = _lane_fit(card, self.pair)
            if self.weak and self.weak in card.need:
                committed = self._flex(cid)
            if self.splash and committed < 1.0:
                if card.is_land and self.splash in card.produces and card.produces & self.pair:
                    committed = 1.0
                elif not card.is_land and card.need <= self.pair | {self.splash} and self.splash not in card.heavy:
                    committed = self.ctx.k("splash_fit")
            v = committed if self.progress >= 1.0 else (1 - self.progress) * flexible + self.progress * committed
        if "fetchland" in card.roles:
            v = max(v, k2(self.ctx, "fetch_fit"))   # a fetch finds basics of either type: fits most decks
        self._fit[cid] = v
        return v

    # ------------------------------------------------------------ what a card is worth to this seat
    def desire(self, cid: str, remaining: set) -> tuple:
        """(value, parts) of a card for this seat, before replaceability and the pick rule."""
        hit = self._desire.get(cid)
        if hit is not None:
            return hit
        ctx, st = self.ctx, self.st
        card = ctx.index[cid]
        q = st.quality[cid]
        if card.conspiracy:
            q *= k2(ctx, "conspiracy_value")
        fit = self.colour_fit(cid)
        pf, plan, in_plan = self.plan_fit(cid, card)
        # Off-colour card on plan: one new colour, single pip, belongs to the deck the seat is in (P7).
        if self.pair and fit < 1.0 and not card.is_land and card.need and len(card.need - self.pair) == 1 \
                and not (card.need - self.pair) & card.heavy and in_plan > 0:
            fit = max(fit, k2(ctx, "plan_colour") * in_plan)
        if self.cheat_kinds and R.is_cheat_target(card, self.cheat_kinds):
            fit = 1.0                                   # R1: put into play, never cast
        lane = self.floor + (1 - self.floor) * fit
        # Format and deck: slow spells without fast mana, lands before commitment, too many of one job.
        if not card.is_land and card.cmc >= K.SLOW_CMC and not self.fast_mana and not card.staple \
                and not ("fatty" in card.roles and self.cheat_plan >= 0.3):
            q *= 1.0 - K.SLOW_CUT
        if card.is_land and card.is_fixing:
            d = k2(ctx, "fixing_damp")
            q *= d + (1 - d) * max(self.progress, min(1.0, 2 * self.t))
        q *= saturation_factor(card, self.role_counts, k2(ctx, "saturation_cut"))
        if k2(ctx, "rule_deck_mix") and not (card.staple or card.bomb):
            q *= R.mix_factor(R.card_kind(card), self.kind_counts, len(self.pool), self.main_deck,
                              k2(ctx, "mix_slack"), k2(ctx, "mix_cut") * k2(ctx, "rule_deck_mix"),
                              k2(ctx, "mix_land_boost") * k2(ctx, "rule_deck_mix"))
        if self.utility_glut and _is_utility_artifact(card):
            q *= 1.0 - k2(ctx, "utility_cut")
        if self.rock_glut and _is_rock(card) and card.cmc >= 2:
            q *= 1.0 - k2(ctx, "rock_cut")
        ramp = min(1.0, len(self.pool) / 6.0)
        if card.roles & _REANIMATE_ROLES and "fatty" not in card.roles and ramp:
            fill = min(1.0, (self.owned_targets + 0.25 * self.table["open_targets"]) / k2(ctx, "reanimate_targets"))
            q *= 1.0 - k2(ctx, "reanimate_cut") * ramp * (1.0 - fill)
        if "fatty" in card.roles and card.cmc >= k2(ctx, "fatty_cmc") and ramp:
            owned = self.owned_cheaters if R.key(card.name) in R.NOT_REANIMATABLE else self.owned_enablers
            fill = min(1.0, (owned + k2(ctx, "open_support_share") * self.table["open_enablers"])
                       / k2(ctx, "fatty_enablers"))
            q *= 1.0 - k2(ctx, "fatty_cut") * ramp * (1.0 - fill)
        base = q * lane * pf
        partners = k2(ctx, "partner_weight") * lane * partner_value(card, self.partners_from, self.colour_fit,
                                                                   ctx.k("drafted_with_share"), ctx.k("partner_full"))
        pv, completes = package_value(st, cid, self.owned, remaining)
        cv = combo_value(card, self.owned, remaining, ctx.combos, self.colour_fit) if card.combos else 0.0
        if card.combos and not completes:
            completes = completes_combo(card, self.owned, ctx.combos, ctx.k("combo_max_pieces"))
        combo = k2(ctx, "combo_weight") * max(pv, min(cv, 1.0)) * (0.25 + 0.75 * lane)
        value = base + partners + combo
        parts = {"quality": q, "colour": lane, "plan_fit": pf, "plan": plan, "base": base, "partners": partners,
                 "combo": combo, "completes": completes}
        out = (value, parts)
        self._desire[cid] = out
        return out


# ---------------------------------------------------------------- the pick

def _table(ctx: BotContext, remaining: set) -> dict:
    idx = ctx.index
    return {
        "open_targets": sum(1 for c in remaining if "fatty" in idx[c].roles and idx[c].power >= 0.5),
        "open_enablers": sum(1 for c in remaining if idx[c].roles & _REANIMATE_ROLES and idx[c].power >= 0.3),
    }


def _rival_model(ctx: BotContext, st: Static, seat: int, table: dict) -> SeatModel:
    picks = tuple(p for p in ctx.picks_by_seat.get(seat, []) if p in ctx.index)
    others = [deck_strength(ctx.index[c] for c in ctx.picks_by_seat.get(o, []) if c in ctx.index)
              for o in ctx.picks_by_seat if o != seat] if ctx.memo is None else None
    if ctx.memo is None:
        return SeatModel(ctx, st, seat, picks, others, table, me=False)
    store = ctx.memo.setdefault("e2_rivals", {})
    key = (picks, tuple(sorted(ctx.tuning.items())) if ctx.tuning else ())
    hit = store.get(seat)
    if hit is None or hit[0] != key:
        others = [_seat_decks(ctx, o) for o in ctx.picks_by_seat if o != seat]
        hit = store[seat] = (key, SeatModel(ctx, st, seat, picks, others, table, me=False))
    return hit[1]


def _seat_decks(ctx: BotContext, seat: int) -> Dict[str, float]:
    picks = tuple(ctx.picks_by_seat.get(seat, []))
    store = ctx.memo.setdefault("e2_decks", {}) if ctx.memo is not None else None
    if store is not None:
        hit = store.get(seat)
        if hit is not None and hit[0] == picks:
            return hit[1]
    d = deck_strength(ctx.index[c] for c in picks if c in ctx.index)
    if store is not None:
        store[seat] = (picks, d)
    return d


def gone_chances(ctx: BotContext, st: Static, candidates: Sequence[str], remaining: set, table: dict,
                 my_round: int) -> Dict[str, float]:
    """Chance each candidate is taken before this seat picks again (P2). Each rival picking in between ranks
    the cards it would consider by its own value; a card near the top of a rival's list is likely gone. For
    people, add how early people usually take the card (knowledge.PICK_TIERS)."""
    window = picks_until_next_turn(ctx)
    if "end" in window:
        return {c: 1.0 for c in candidates}
    keep = {c: 1.0 for c in candidates}
    cand = set(candidates)
    n_plaus = int(k2(ctx, "plausible"))
    plausible = [c for c in st.by_quality if c in remaining][:n_plaus]
    plausible = set(plausible) | cand | {c for c in remaining if c in st.card_pkgs or ctx.index[c].combos}
    spread_k = k2(ctx, "rival_spread")
    people_picks, all_picks = 0, 0
    for seat, n in window.items():
        all_picks += n
        if ctx.people is None or seat in ctx.people:
            people_picks += n
        model = _rival_model(ctx, st, seat, table)
        ranked = sorted(((model.desire(c, remaining)[0], c) for c in plausible), reverse=True)
        spread = 1.0 + spread_k * n
        for rank, (_, c) in enumerate(ranked):
            if c in cand:
                keep[c] *= 1.0 - 1.0 / (1.0 + math.exp((rank + 1 - n - 0.5) / spread))
    share = people_picks / max(all_picks, 1)
    if share > 0:
        w = k2(ctx, "people_prior") * share
        for c in candidates:
            tier = st.tier.get(c)
            if tier is not None:
                keep[c] *= 1.0 - w / (1.0 + math.exp(1.5 * (tier - my_round)))
    return {c: 1.0 - v for c, v in keep.items()}


def score_pool(ctx: BotContext) -> List[Tuple[float, str, dict]]:
    """Score every remaining card for this seat. Returns (score, card_id, parts), best first."""
    st = static_for(ctx.index)
    remaining = set(c for c in ctx.remaining if c in ctx.index)
    if not remaining:
        return []
    table = _table(ctx, remaining)
    others = [_seat_decks(ctx, o) if ctx.memo is not None
              else deck_strength(ctx.index[c] for c in ctx.picks_by_seat.get(o, []) if c in ctx.index)
              for o in ctx.picks_by_seat if o != ctx.seat]
    me = SeatModel(ctx, st, ctx.seat, ctx.picks_by_seat.get(ctx.seat, []), others, table, me=True)
    rivals = [s for s in ctx.picks_by_seat if s != ctx.seat]
    n = len(me.pool)

    # Deck needs: interaction by mid-draft (P12) and a way to win.
    interaction = sum(1 for c in me.pool if st.interaction[c.id])
    gap = max(0.0, K.INTERACTION_TARGET * min(1.0, me.t / 0.8) - interaction) / K.INTERACTION_TARGET \
        if me.t >= 0.3 else 0.0
    wincon_gap = 0.0
    if me.pair and me.t >= k2(ctx, "wincon_start"):
        score, _ = win_plan(me.pool, lambda c: me.colour_fit(c.id), me.owned, remaining, ctx.combos,
                            ctx.k("wincon_combo_weight"))
        wincon_gap = max(0.0, 1.0 - score) * min(1.0, (me.t - k2(ctx, "wincon_start")) / 0.25) * k2(ctx, "wincon_weight")
    # Sideboard answers (P14).
    hs, hf = k2(ctx, "hate_start"), k2(ctx, "hate_full")
    hate_ramp = min(1.0, max(0.0, (n - hs + 1) / max(1.0, hf - hs + 1)))
    owned_hate = {t: sum(1 for c in me.pool if f"hate_{t}" in c.roles) for t in HATE_TARGETS}
    if hate_ramp and sum(owned_hate.values()) < k2(ctx, "hate_max"):
        tt, own_t = table_targets(ctx, rivals), deck_targets(me.pool)
    else:
        hate_ramp = 0.0

    rows = []
    for cid in remaining:
        value, parts = me.desire(cid, remaining)
        card = ctx.index[cid]
        need = 0.0
        if gap and st.interaction[cid]:
            need += k2(ctx, "interaction_weight") * gap * parts["colour"]
        if wincon_gap:
            need += wincon_gap * threat_level(card) * min(1.0, 0.4 + max(card.power, 0.0)) * parts["colour"]
        hate = k2(ctx, "hate_weight") * hate_ramp * hate_value(card, tt, own_t, owned_hate) if hate_ramp else 0.0
        rows.append([value + need + hate, cid, parts, need, hate])
    rows.sort(key=lambda r: -r[0])

    # The full treatment for the strongest candidates: replaceability (P6), then the pick rule (P2, P3).
    top = rows[:int(k2(ctx, "candidates"))]
    top_ids = [r[1] for r in top]
    peers: Dict[str, List[tuple]] = {}
    for r in rows:
        job = st.job[r[1]]
        if job:
            peers.setdefault(job, []).append((r[0], r[1]))
    peer_ids = set()
    for r in top:
        job = st.job[r[1]]
        if job:
            peer_ids.update(c for _, c in peers[job][:4])
    my_round = n + 1
    gone = gone_chances(ctx, st, list(dict.fromkeys(top_ids + sorted(peer_ids))), remaining, table, my_round)
    picks_left = sum(1 for s in ctx.order[ctx.pick_index:] if s == ctx.seat)
    keep = 1.0 if picks_left <= 1 else k2(ctx, "keep")
    rw = k2(ctx, "replace_weight")
    out = []
    for value, cid, parts, need, hate in top:
        job = st.job[cid]
        sub = 0.0
        if job:
            # The substitute: the best other card with the same job that is likely still there next time.
            p_left = 1.0
            for v_other, other in peers[job]:
                if other == cid:
                    continue
                g = gone.get(other, 0.5)
                sub += p_left * (1.0 - g) * v_other
                p_left *= g
                if p_left < 0.05:
                    break
        own = value - rw * min(value, sub)
        g = 1.0 if parts["completes"] else gone.get(cid, 0.0)
        score = own * (keep + (1.0 - keep) * g)
        info = {"fit": round(parts["colour"], 2), "plan": parts["plan"], "value": round(value, 3),
                "gone": round(g, 2)}
        if ctx.explain:
            info.update(quality=round(parts["quality"], 3), plan_fit=round(parts["plan_fit"], 2),
                        base=round(parts["base"], 3), partners_raw=round(parts["partners"], 3),
                        combo_raw=round(parts["combo"], 3), need=round(need, 3), hate_raw=round(hate, 3),
                        substitute=round(sub, 3), keep=keep, **_lab_parts(parts, need, hate, score, g))
        out.append((score, cid, info))
    out.sort(key=lambda r: -r[0])
    tail = []
    for value, cid, parts, need, hate in rows[len(top):]:
        info = {"fit": round(parts["colour"], 2), "plan": parts["plan"], "value": round(value, 3)}
        if ctx.explain:
            info.update(quality=round(parts["quality"], 3), plan_fit=round(parts["plan_fit"], 2),
                        base=round(parts["base"], 3), partners_raw=round(parts["partners"], 3),
                        combo_raw=round(parts["combo"], 3), need=round(need, 3), hate_raw=round(hate, 3),
                        **_lab_parts(parts, need, hate, value * keep, None))
        tail.append((value * keep, cid, info))
    return out + tail


def _lab_parts(parts: dict, need: float, hate: float, score: float, gone: Optional[float]) -> dict:
    """The score in the Bot Lab's terms (rating, drafted together, combo, needs, sideboard; x colour fit x
    contention), so its bars and breakdown add up for engine 2 too: "contention" here is everything the pick
    rule does after the value (substitutes, the chance it's gone, how much a card that comes back is worth)."""
    lane = max(parts["colour"], 1e-6)
    out = {"rating": round(parts["quality"] * parts["plan_fit"], 3), "partners": round(parts["partners"] / lane, 3),
           "plan": 0.0, "combo": round(parts["combo"] / lane, 3), "needs": round(need / lane, 3), "other": 0.0,
           "hate": round(hate / lane, 3), "colour": round(lane, 2)}
    total = (out["rating"] + out["partners"] + out["combo"] + out["needs"] + out["hate"]) * lane
    out["contested"] = round(score / total, 2) if total > 1e-9 else 1.0
    if gone is not None:
        out["risk"] = round(gone, 2)
    return out


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
    return [(cid, s) for s, cid, _ in score_pool(ctx)[:n]]
