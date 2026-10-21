"""Bot Lab: look inside one pick of a rotisserie draft and try other weights.

Rebuilds the table as it was just before a pick slot, scores every card still available with the engine
(with each score's parts) and, when `tuning` overrides some TUNING values, scores it again with those so
the page can show how the ranking moves. The overrides only apply to this view, never to the live bots.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

from .combos import Combo
from .decktypes import deck_strength
from .engine import TUNING, BotContext, coloured_spells, colour_state, commit_progress, score_pool
from .features import CardInfo
from .personas import Persona

# The weights the Lab offers, grouped for the page: (group, key, label, help, min, max, step).
# Labels describe what a person sees the bot do, not the code.
KNOBS: List[tuple] = [
    ("Rating and colours", "commit_rating_cut", "Rating drop once committed", "How much less raw Elo counts once the bot has a deck (colours or deck type).", 0, 1, 0.05),
    ("Rating and colours", "power_late_drop", "Rating drop late in the draft", "How much less raw Elo counts by the last pick.", 0, 1, 0.05),
    ("Rating and colours", "flex_floor", "Off-colour value while open", "Share of its value an off-colour card keeps before the bot commits.", 0, 1, 0.05),
    ("Rating and colours", "committed_floor", "Off-colour value once committed", "Share of its value an off-colour card keeps after the bot commits.", 0, 1, 0.05),
    ("Rating and colours", "commit_pick", "Coloured spells to commit", "Coloured spells owned before the bot is fully in two colours.", 3, 15, 1),
    ("Synergy", "partner_weight", "Drafted-together weight", "Value for cards CubeCobra drafters put with the bot's cards.", 0, 1.5, 0.05),
    ("Synergy", "drafted_with_share", "'Often drafted with' share", "How much the weaker 'often drafted with' links count next to 'synergistic' ones.", 0, 1, 0.05),
    ("Synergy", "combo_base", "Combo weight early", "Value of combo pieces at the start of the draft.", 0, 1.5, 0.05),
    ("Synergy", "combo_growth", "Combo weight growth", "Extra combo value by mid-draft.", 0, 1.5, 0.05),
    ("Synergy", "contest_weight", "Fight for a shared lane", "Bonus for a deck type's cards when a rival is in it too.", 0, 0.6, 0.05),
    ("Deck types", "narrow_floor", "Narrow cards outside their deck", "Share of value Top, Baubles, Karakas keep for a bot not in a deck that uses them.", 0, 1, 0.05),
    ("Deck types", "key_floor", "Key cards outside their deck", "Share of value Urza, Reanimate, Ajani keep for a bot not in their deck type.", 0, 1, 0.05),
    ("Deck types", "deck_focus", "Focus on own deck type", "How much cards outside the bot's deck type lose once it's fully in one.", 0, 1, 0.05),
    ("Deck types", "crowd_cut", "Back off crowded lanes", "How much a crowded deck type's cards lose for a bot behind the leader.", 0, 1, 0.05),
    ("Support and saturation", "unsupported_cut", "Payoffs with no support", "Rating lost by payoffs (artifact, storm, blink) with nothing to support them.", 0, 1, 0.05),
    ("Support and saturation", "reanimate_cut", "Reanimate / cheat with no targets", "Rating lost by Reanimate or Sneak Attack with no fatty around.", 0, 1, 0.05),
    ("Support and saturation", "fatty_cut", "Fatties with no way in", "Rating lost by 7+ mana fatties with no reanimation or cheat spell around.", 0, 1, 0.05),
    ("Support and saturation", "saturation_cut", "Too many of one job", "Rating lost once a role (fatties, sweepers, tutors...) is past its limit.", 0, 1, 0.05),
    ("Support and saturation", "utility_cut", "Extra utility artifacts", "Rating lost by a third Top/Bauble-type card with no artifact plan.", 0, 1, 0.05),
    ("Support and saturation", "rock_cut", "Extra mana rocks", "Rating lost by a fourth mana rock with no artifact plan.", 0, 1, 0.05),
    ("Other", "fixing_bonus", "Dual lands bonus", "Late-draft value of an on-colour dual or fetch.", 0, 0.6, 0.05),
    ("Other", "wincon_weight", "Find a win condition", "Push towards threats for a deck with no way to win.", 0, 1, 0.05),
    ("Other", "hate_weight", "Sideboard answers", "Value of hate cards against a deck another seat is building (late only).", 0, 1, 0.05),
    ("Other", "float_base", "Let cards come back", "How much a card likely to come back is worth less now.", 0, 1, 0.05),
]
KNOB_KEYS = {k[1] for k in KNOBS}


def knob_list() -> List[dict]:
    return [{"group": g, "key": key, "label": label, "help": help_, "min": lo, "max": hi, "step": step,
             "default": TUNING[key]} for g, key, label, help_, lo, hi, step in KNOBS]


def clean_tuning(raw: Optional[dict]) -> Dict[str, float]:
    """Only known weights, as numbers within each knob's range."""
    out: Dict[str, float] = {}
    limits = {k[1]: (k[4], k[5]) for k in KNOBS}
    for key, val in (raw or {}).items():
        if key not in KNOB_KEYS:
            continue
        try:
            v = float(val)
        except (TypeError, ValueError):
            continue
        lo, hi = limits[key]
        v = min(hi, max(lo, v))
        if abs(v - TUNING[key]) > 1e-9:
            out[key] = v
    return out


def seat_slots(order: Sequence[int], made: int, seat: int) -> List[int]:
    """A seat's pick slots that have happened, plus its next one if the draft is still on it."""
    return [i for i, s in enumerate(order) if s == seat and i <= made]


def pick_slot(order: Sequence[int], made: int, seat: Optional[int], pick_no: Optional[int], slot: Optional[int]) -> int:
    """The slot to show: a seat's Nth pick (its latest if no number), or a slot given directly."""
    if seat is not None:
        slots = seat_slots(order, made, seat)
        if slots:
            return slots[-1] if not pick_no else slots[min(max(pick_no, 1), len(slots)) - 1]
    return max(0, min(slot or 0, made, len(order) - 1))


def lab_view(index: Dict[str, CardInfo], combos: List[Combo], order: Sequence[int], picks: Sequence[dict],
             picks_per_seat: int, slot: int, tuning: Optional[Dict[str, float]] = None,
             people: Optional[Iterable[int]] = None, skip_names: Iterable[str] = (), singleton_names: bool = False,
             n: int = 15) -> dict:
    """The engine's view of pick `slot` (0-based, up to the next pick still to be made)."""
    slot = max(0, min(int(slot), len(order) - 1, len(picks)))
    seat = order[slot]
    skip = {s.lower() for s in skip_names}
    by_seat: Dict[int, List[str]] = {s: [] for s in set(order)}
    taken, taken_names = set(), set()
    ordered = sorted(picks, key=lambda p: p["order"])
    for p in ordered:
        if p["order"] >= slot:
            break
        by_seat.setdefault(p["seat_index"], []).append(p["card_id"])
        taken.add(p["card_id"])
        if singleton_names and p["card_id"] in index:
            taken_names.add(index[p["card_id"]].name.lower())
    actual = next((p["card_id"] for p in ordered if p["order"] == slot), None)
    remaining = [c for c in index if c not in taken and index[c].name.lower() not in skip
                 and index[c].name.lower() not in taken_names]
    if actual in index and actual not in remaining:
        remaining.append(actual)
    people = frozenset(people) if people is not None else None

    def run(t):
        ctx = BotContext(index, combos, remaining, by_seat, seat, order, slot, picks_per_seat, Persona("steady"),
                         t or None, explain=True, people=people)
        return ctx, score_pool(ctx)

    ctx, base = run(None)
    tuned = run(tuning)[1] if tuning else base
    base_rank = {cid: (i + 1, s) for i, (s, cid, _) in enumerate(base)}

    def row(i, s, cid, info):
        br, bs = base_rank.get(cid, (None, None))
        return {"card": cid, "name": index[cid].name, "rank": i + 1, "score": round(s, 3), "parts": info,
                "base_rank": br, "base_score": round(bs, 3) if bs is not None else None}

    rows = [row(i, s, cid, info) for i, (s, cid, info) in enumerate(tuned[:n])]
    took = None
    if actual in index:
        i = next(i for i, (_, cid, _) in enumerate(tuned) if cid == actual)
        took = row(i, tuned[i][0], actual, tuned[i][2])

    mine = [index[c] for c in by_seat.get(seat, []) if c in index]
    rivals = [s for s in by_seat if s != seat]
    _, pair, splash = colour_state(ctx, mine, len(mine), rivals)
    decks = deck_strength(mine)
    return {
        "slot": slot, "seat": seat, "pick_no": len(mine) + 1, "seat_slots": seat_slots(order, len(picks), seat), "of": len(tuned), "next_pick": slot >= len(picks),
        "took": took, "rows": rows,
        "seat_info": {
            "owned": [c.id for c in mine],
            "pair": "".join(c for c in "WUBRG" if pair and c in pair), "splash": splash or "",
            "coloured_spells": coloured_spells(mine), "commit": round(commit_progress(ctx, mine), 2),
            "decks": {t: round(v, 2) for t, v in sorted(decks.items(), key=lambda kv: -kv[1]) if v > 0.05},
        },
        "tuning": tuning or {},
    }
