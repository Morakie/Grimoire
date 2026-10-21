"""Bot Lab: look inside one pick of a rotisserie draft and try other weights.

Rebuilds the table as it was just before a pick slot, scores every card still available with the engine
(with each score's parts) and, when `tuning` overrides some TUNING values, scores it again with those so
the page can show how the ranking moves. The overrides only apply to this view, never to the live bots.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

from .combos import Combo
from .decktypes import deck_strength
from . import engines
from .engine import TUNING, BotContext, coloured_spells, colour_state, commit_progress
from .features import CardInfo
from .personas import Persona

# The weights the Lab offers, grouped for the page: (group, key, label, help, min, max, step).
# Labels describe what a person sees the bot do, not the code.
KNOBS: List[tuple] = [
    ("Rating and colours", "rating_weight", "Rating (Elo) weight", "How much raw CubeCobra Elo counts at all. Lower it to let synergy and the deck lead.", 0, 2, 0.05),
    ("Rating and colours", "commit_rating_cut", "Rating drop once committed", "How much less raw Elo counts once the bot has a deck (colours or deck type).", 0, 1, 0.05),
    ("Rating and colours", "power_late_drop", "Rating drop late in the draft", "How much less raw Elo counts by the last pick.", 0, 1, 0.05),
    ("Rating and colours", "flex_floor", "Off-colour value while open", "Share of its value an off-colour card keeps before the bot commits.", 0, 1, 0.05),
    ("Rating and colours", "committed_floor", "Off-colour value once committed", "Share of its value an off-colour card keeps after the bot commits.", 0, 1, 0.05),
    ("Rating and colours", "plan_colour", "Off-colour cards on plan", "How much an off-colour card (one new colour) keeps when it fits the bot's deck type, links or combos. Rating alone never counts.", 0, 1, 0.05),
    ("Rating and colours", "commit_pick", "Coloured spells to commit", "Coloured spells owned before the bot is fully in two colours.", 3, 15, 1),
    ("Synergy", "partner_weight", "Drafted-together weight", "Value for cards CubeCobra drafters put with the bot's cards.", 0, 1.5, 0.05),
    ("Synergy", "partner_full", "Links for full synergy", "Link strength to the bot's cards (all of them) that gives full synergy value. Raise it so a card linked to 8 of the bot's cards beats one linked to 3.", 1, 12, 0.5),
    ("Synergy", "drafted_with_share", "'Often drafted with' share", "How much the weaker 'often drafted with' links count next to 'synergistic' ones.", 0, 1, 0.05),
    ("Synergy", "combo_base", "Combo weight early", "Value of combo pieces at the start of the draft.", 0, 1.5, 0.05),
    ("Synergy", "combo_growth", "Combo weight growth", "Extra combo value by mid-draft.", 0, 1.5, 0.05),
    ("Deck types", "lean_weight", "Personality lean", "Early bonus for the deck type each bot leans towards (different for every bot). Fades as the draft goes on and when others are in that lane.", 0, 0.6, 0.05),
    ("Deck types", "crowd_margin", "Third seat backs off by", "How far behind the second seat in a deck type a third seat must be to back off fully (lower = backs off sooner).", 0.05, 1, 0.05),
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


def _knobs(engine: str = ""):
    """(knob rows, defaults) for an engine: engine 2 has its own weights (engine2.TUNING2)."""
    if engine == "engine2":
        from .engine2 import KNOBS2, TUNING2
        return KNOBS2, TUNING2
    return KNOBS, TUNING


def knob_list(engine: str = "") -> List[dict]:
    rows, defaults = _knobs(engine)
    return [{"group": g, "key": key, "label": label, "help": help_, "min": lo, "max": hi, "step": step,
             "default": defaults[key]} for g, key, label, help_, lo, hi, step in rows]


def clean_tuning(raw: Optional[dict], engine: str = "") -> Dict[str, float]:
    """Only known weights (of that engine), as numbers within each knob's range."""
    out: Dict[str, float] = {}
    rows, TUNING = _knobs(engine)
    limits = {k[1]: (k[4], k[5]) for k in rows}
    for key, val in (raw or {}).items():
        if key not in limits:
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
             n: int = 15, engine: str = "") -> dict:
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
        return ctx, engines.get(engine).score_pool(ctx)

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
        "tuning": tuning or {}, "engine": engine or engines.DEFAULT,
    }


# ---------------------------------------------------------------- Bot Brain: any cube or the VRD pool, no draft

def _brief(c: CardInfo) -> dict:
    return {"id": c.id, "name": c.name, "elo": round(c.elo), "colors": "".join(x for x in "WUBRG" if x in c.need),
            "land": c.is_land}


def card_dossier(index: Dict[str, CardInfo], combos: List[Combo], cid: str, max_partners: int = 60,
                 graph_size: int = 24) -> dict:
    """Everything the bots know about one card: rating, roles, deck types, narrow/universal, home colours,
    partners (strongest first) and combos, plus a small link graph of the card and its closest partners."""
    from .decktypes import is_narrow, is_universal
    c = index[cid]
    uni = is_universal(c)
    partners = sorted(((index[p], s) for p, s in c.partners.items() if p in index),
                      key=lambda ps: (-ps[1], -ps[0].elo))
    lines = []
    for ci in c.combos:
        cb = combos[ci]
        lines.append({"pieces": [_brief(index[p]) for p in cb.pieces if p in index], "weight": round(cb.weight, 2),
                      "counted": len(cb.pieces) <= TUNING["combo_max_pieces"]})
    lines.sort(key=lambda x: (not x["counted"], len(x["pieces"]), -x["weight"]))
    # Link graph: the card, its strongest partners, and the links among them.
    near = [p for p, _ in partners[:graph_size]]
    ids = {cid} | {p.id for p in near}
    edges = []
    for a in [c] + near:
        for b, s in a.partners.items():
            if b in ids and a.id < b:
                edges.append([a.id, b, s])
    return {
        **_brief(c), "power": round(c.power, 3), "cmc": c.cmc, "types": sorted(c.types),
        "roles": sorted(c.roles - {"cheap_threat"}), "key_of": sorted(c.key_of),
        "deck": {t: v for t, v in sorted(c.deck.items(), key=lambda kv: -kv[1])},
        "narrow": is_narrow(c, uni, c.staple), "universal": uni, "staple": c.staple,
        "home": {k: round(v, 2) for k, v in c.home.items()} if c.home else None,
        "partners": [{**_brief(p), "s": s} for p, s in partners[:max_partners]],
        "partner_count": {"synergy": sum(1 for _, s in partners if s >= 1), "all": len(partners)},
        "combos": lines[:20], "combo_count": len(lines),
        "graph": {"nodes": [_brief(x) for x in [c] + near], "edges": edges},
    }


def source_summary(index: Dict[str, CardInfo], combos: List[Combo]) -> dict:
    """An overview of how the bots see a card pool: each deck type's key cards and strongest members,
    the most connected cards, and how many cards have CubeCobra data."""
    from .decktypes import DECK_TYPES
    cards = list(index.values())
    syn = {c.id: sum(1 for p, s in c.partners.items() if s >= 1 and p in index) for c in cards}
    decks = []
    for t in DECK_TYPES:
        keys = sorted((c for c in cards if t in c.key_of), key=lambda c: -c.elo)
        members = sorted((c for c in cards if t not in c.key_of and c.deck.get(t, 0) >= 0.5),
                         key=lambda c: (-c.deck[t], -c.elo))
        decks.append({"type": t, "keys": [_brief(c) for c in keys[:12]], "key_count": len(keys),
                      "members": [_brief(c) for c in members[:12]], "member_count": len(members)})
    top = sorted(cards, key=lambda c: -syn[c.id])[:25]
    return {"cards": len(cards), "with_partners": sum(1 for c in cards if c.partners), "combos": len(combos),
            "decks": decks, "connected": [{**_brief(c), "links": syn[c.id]} for c in top if syn[c.id]]}


def source_payload(index: Dict[str, CardInfo], combos: List[Combo], cards: Sequence[dict]) -> dict:
    """What the Bot Brain page gets for a loaded pool: the overview, a light card list and the knobs."""
    light = [{"id": c["id"], "name": c["name"], "image": c.get("image"), "art_crop": c.get("art_crop"),
              "elo": round(index[c["id"]].elo), "colors": "".join(x for x in "WUBRG" if x in index[c["id"]].need),
              "land": index[c["id"]].is_land}
             for c in cards if c["id"] in index]
    return {"summary": source_summary(index, combos), "cards": light, "knobs": knob_list()}


def snake_order(seats: int, per_seat: int) -> List[int]:
    out: List[int] = []
    for r in range(per_seat):
        out.extend(range(seats) if r % 2 == 0 else range(seats - 1, -1, -1))
    return out


def _pick_rng(seed: int, slot: int):
    """Each pick gets its own random stream, so a draft re-run from any pick reproduces every earlier pick
    exactly, and the same weights give the same later picks."""
    import random
    return random.Random(seed * 1_000_003 + slot)


class DraftRun:
    """An all-bot rotisserie draft (snake order) that can be run a few picks at a time (the browser streams
    picks onto the page this way). `simulate` runs one to the end."""

    def __init__(self, index: Dict[str, CardInfo], combos: List[Combo], seats: int, per_seat: int, seed: int = 0,
                 tuning: Optional[Dict[str, float]] = None, start: Sequence[dict] = (),
                 tuned_seats: Optional[Iterable[int]] = None, stop: Optional[int] = None, personas: bool = False,
                 engine: str = ""):
        self.index, self.combos, self.seed, self.tuning = index, combos, seed, tuning
        self.engine = engine if engine in engines.NAMES else engines.DEFAULT
        # Personalities as at a real table (from the seed, so a re-draft gets the same ones): a random archetype
        # each and a different deck type to lean towards. Without them every bot drafts as "steady".
        if personas:
            import random as _random
            from .personas import assign_leans, lean_choices, random_persona
            rng = _random.Random(seed * 7919 + 17)
            self.personas = [random_persona(rng) for _ in range(seats)]
            assign_leans(rng, self.personas, lean_choices(c.name for c in index.values()))
            for p in self.personas:
                p.temperature = 0.03
        else:
            self.personas = [Persona("steady", temperature=0.03) for _ in range(seats)]
        self.order = snake_order(seats, min(per_seat, max(1, len(index) // max(seats, 1))))
        self.per = len(self.order) // seats
        self.only = frozenset(tuned_seats) if tuned_seats is not None else None
        self.remaining = list(index)
        self.by_seat: Dict[int, List[str]] = {s: [] for s in range(seats)}
        self.picks: List[dict] = []
        self.memo: dict = {}     # what each seat's pool says, shared across picks (picks are the same without it)
        # Replay the kept picks; stop at the first one that no longer fits (other seats, a card gone).
        for slot, p in enumerate(sorted(start, key=lambda p: p.get("order", 0))):
            cid = p.get("card_id")
            if slot >= len(self.order) or p.get("order") != slot or p.get("seat_index") != self.order[slot] \
                    or cid not in self.remaining:
                break
            self._take(slot, self.order[slot], cid)
        self.kept = len(self.picks)
        self.end = len(self.order) if stop is None else max(self.kept, min(int(stop), len(self.order)))

    def _take(self, slot: int, seat: int, cid: str) -> None:
        self.by_seat[seat].append(cid)
        self.picks.append({"order": slot, "seat_index": seat, "card_id": cid})
        name = self.index[cid].name.lower()
        self.remaining = [c for c in self.remaining if c != cid and self.index[c].name.lower() != name]

    @property
    def done(self) -> bool:
        return len(self.picks) >= self.end or not self.remaining

    def step(self, n: int = 1) -> List[dict]:
        """Make up to n more picks; returns them."""
        choose_pick = engines.get(self.engine).choose_pick
        made = []
        while n > 0 and not self.done:
            slot = len(self.picks)
            seat = self.order[slot]
            t = self.tuning if (self.only is None or seat in self.only) else None
            ctx = BotContext(self.index, self.combos, self.remaining, self.by_seat, seat, self.order, slot, self.per,
                             self.personas[seat], t or None, people=frozenset(), memo=self.memo)
            self._take(slot, seat, choose_pick(ctx, _pick_rng(self.seed, slot)))
            made.append(self.picks[-1])
            n -= 1
        return made

    def result(self) -> dict:
        seats = seat_summaries(self.index, self.combos, self.by_seat)
        for s in seats:
            p = self.personas[s["seat"]]
            s["persona"] = {"archetype": p.archetype, "lean": p.lean}
        return {"order": self.order, "picks": self.picks, "per_seat": self.per, "kept": self.kept, "seats": seats,
                "engine": self.engine}


def simulate(index: Dict[str, CardInfo], combos: List[Combo], seats: int, per_seat: int, seed: int = 0,
             tuning: Optional[Dict[str, float]] = None, start: Sequence[dict] = (),
             tuned_seats: Optional[Iterable[int]] = None, stop: Optional[int] = None, personas: bool = False,
             engine: str = "") -> dict:
    """An all-bot rotisserie draft (snake order) with the given weights. Returns the order and picks in
    the same shape as a real draft, so lab_view can look at any of its picks.

    `start` keeps the first picks of an earlier run (a rewind): the bots re-draft only from there on.
    `tuned_seats` limits the weights to some seats (the others use the current ones), to compare the two
    side by side in one draft. `stop` ends the draft at that table pick."""
    run = DraftRun(index, combos, seats, per_seat, seed, tuning, start, tuned_seats, stop, personas, engine)
    run.step(len(run.order))
    return run.result()


def seat_summaries(index: Dict[str, CardInfo], combos: List[Combo], by_seat: Dict[int, List[str]]) -> List[dict]:
    """What each seat ended up with: colours, deck types, finished combos and how many spells are on colour."""
    from .engine import best_pair, coloured_spells
    from .features import castable
    out = []
    for seat in sorted(by_seat):
        ids = by_seat[seat]
        pool = [index[c] for c in ids if c in index]
        pair = best_pair(pool) if coloured_spells(pool) >= 2 else frozenset()
        spells = [c for c in pool if not c.is_land]
        on = [c for c in spells if not pair or castable(c, pair)]
        owned = set(ids)
        done = [[index[p].name for p in cb.pieces] for cb in combos
                if len(cb.pieces) <= TUNING["combo_max_pieces"] and set(cb.pieces) <= owned]
        top = sorted(on, key=lambda c: -c.elo)[:23]
        decks = deck_strength(pool)
        out.append({
            "seat": seat, "picks": len(ids),
            "pair": "".join(c for c in "WUBRG" if c in pair),
            "decks": {t: round(v, 2) for t, v in sorted(decks.items(), key=lambda kv: -kv[1]) if v >= 0.25},
            "on_colour": round(100 * len(on) / max(len(spells), 1)),
            "avg_elo": round(sum(c.elo for c in top) / max(len(top), 1)),
            "creatures": sum(1 for c in top if c.is_creature),
            "combos": done[:6],
        })
    return out
