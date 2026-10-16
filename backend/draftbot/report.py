"""Bot report: replay a rotisserie draft and compare every player's pick with the bots' engine.

For each pick (after each seat's first few, when nothing is established yet) the engine rebuilds that
moment of the draft, scores every card still available and records where the player's card ranked, the
engine's top three and the score parts behind both. The summary shows how close the engine gets to real
players overall, by seat and by draft phase, plus the biggest disagreements to look at by hand.
"""
from __future__ import annotations

from statistics import median
from typing import Dict, List, Optional, Sequence

from .combos import Combo
from .engine import BotContext, score_pool
from .features import CardInfo
from .personas import Persona

PARTS = ("rating", "combo", "plan", "partners", "needs", "hate", "other", "colour", "contested")
BUCKETS = ((1, "top1"), (3, "top3"), (5, "top5"), (10, "top10"), (20, "top20"))


def _parts(info: dict) -> dict:
    return {k: info[k] for k in PARTS if k in info}


def _phase(n_owned: int, per_seat: int) -> str:
    t = n_owned / max(per_seat, 1)
    return "early" if t < 1 / 3 else ("middle" if t < 2 / 3 else "late")


def _stats(ranks: List[int]) -> dict:
    if not ranks:
        return {"picks": 0}
    out = {"picks": len(ranks), "median_rank": median(ranks)}
    for n, key in BUCKETS:
        out[key] = round(100 * sum(1 for r in ranks if r <= n) / len(ranks), 1)
    out["outside_top20"] = round(100 * sum(1 for r in ranks if r > 20) / len(ranks), 1)
    return out


def build_report(index: Dict[str, CardInfo], combos: List[Combo], order: Sequence[int],
                 picks: Sequence[dict], picks_per_seat: int, seats: Sequence[dict],
                 skip_first: int = 5, ignore_names: Sequence[str] = (), top_disagreements: int = 20,
                 singleton_names: bool = False) -> dict:
    """`picks` are the draft's pick records (order, seat_index, card_id) in order; `seats` the seat list
    (index, player_name). Picks of cards the engine doesn't know (custom cards) are skipped.
    `singleton_names`: once a name is drafted, other printings of it don't count as available (mirror tables)."""
    skip_names = {n.lower() for n in ignore_names}
    taken: set = set()
    taken_names: set = set()
    by_seat: Dict[int, List[str]] = {s["index"]: [] for s in seats}
    rows: List[dict] = []
    for p in sorted(picks, key=lambda x: x["order"]):
        seat, cid = p["seat_index"], p["card_id"]
        owned = len(by_seat.get(seat, []))
        if cid in index and owned >= skip_first:
            remaining = [c for c in index if c not in taken and index[c].name.lower() not in skip_names
                         and index[c].name.lower() not in taken_names]
            if cid not in remaining:
                remaining.append(cid)
            ctx = BotContext(index, combos, remaining, by_seat, seat, order, p["order"], picks_per_seat,
                             Persona("steady"), explain=True)
            scored = score_pool(ctx)
            rank = next((i + 1 for i, (_, c, _) in enumerate(scored) if c == cid), len(scored))
            best_score = scored[0][0] if scored else 0.0
            mine = next((s for s, c, _ in scored if c == cid), 0.0)
            rows.append({
                "order": p["order"], "seat": seat, "pick_no": owned + 1, "phase": _phase(owned, picks_per_seat),
                "card": cid, "rank": rank, "of": len(scored),
                "gap": round(best_score - mine, 3),
                "card_parts": _parts(next((i for _, c, i in scored if c == cid), {})),
                "bot_top": [{"card": c, "score": round(s, 3), "parts": _parts(i)} for s, c, i in scored[:3]],
            })
        taken.add(cid)
        if singleton_names and cid in index:
            taken_names.add(index[cid].name.lower())
        by_seat.setdefault(seat, []).append(cid)

    ranks = [r["rank"] for r in rows]
    by_seat_stats = {}
    for s in seats:
        r = [x["rank"] for x in rows if x["seat"] == s["index"]]
        by_seat_stats[str(s["index"])] = {"name": s.get("player_name") or f"Seat {s['index'] + 1}", **_stats(r)}
    by_phase = {ph: _stats([x["rank"] for x in rows if x["phase"] == ph]) for ph in ("early", "middle", "late")}
    # Biggest disagreements: picks the engine ranked far down, weighted by how big the score gap was.
    worst = sorted(rows, key=lambda x: (-(min(x["rank"], 60) * (0.5 + x["gap"]))))[:top_disagreements]
    return {
        "skip_first": skip_first,
        "overall": _stats(ranks),
        "by_seat": by_seat_stats,
        "by_phase": by_phase,
        "disagreements": worst,
        "picks": [{k: r[k] for k in ("order", "seat", "pick_no", "card", "rank", "gap")} for r in rows],
    }
