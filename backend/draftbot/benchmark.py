"""How closely an engine drafts like LSV's tables (lsv_drafts.py).

Each draft is replayed on a card pool: before every real pick, the engine scores the cards still available for
that seat (with everyone treated as a person), and we record where the card actually taken ranks. LSV's own
seat is reported separately: his picks are the main target. Cards the pool doesn't have are skipped (they are
still removed from the table), and so are picks marked "?".
"""
from __future__ import annotations

import unicodedata
from statistics import median
from typing import Dict, List, Optional

from . import engines
from .engine import BotContext
from .lab import snake_order
from .lsv_drafts import DRAFTS
from .personas import Persona


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower().strip()
    return s.split(" // ")[0]


def name_index(index) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for cid, c in index.items():
        out.setdefault(_norm(c.name), cid)
    return out


def resolve(names: Dict[str, str], name: str) -> Optional[str]:
    """Card id for a name: exact (accents and case ignored), else a unique name starting with it."""
    n = _norm(name)
    if n in names:
        return names[n]
    hits = [cid for k, cid in names.items() if k.startswith(n)]
    return hits[0] if len(hits) == 1 else None


def check_orders() -> List[str]:
    """Problems with the reconstructed drafts: picks whose seat doesn't follow the snake order."""
    problems = []
    for d in DRAFTS:
        order = snake_order(d["seats"], 60)
        for i, (seat, _) in enumerate(d["picks"]):
            if order[i] + 1 != seat:
                problems.append(f"{d['video']} pick {i + 1}: seat {seat}, expected {order[i] + 1}")
                break
    return problems


def replay(index, combos, engine: str = "engine2", drafts=None, tuning: Optional[dict] = None,
           max_picks: Optional[int] = None) -> dict:
    """Ranks of the real picks under `engine`. Returns per-draft and overall summaries plus every pick row."""
    eng = engines.get(engine)
    names = name_index(index)
    rows = []
    per_draft = []
    for d in drafts or DRAFTS:
        seats = d["seats"]
        order = snake_order(seats, 60)
        by_seat = {s: [] for s in range(seats)}
        remaining = set(index)
        resolved = [(seat - 1, resolve(names, card) if card != "?" else None, card) for seat, card in d["picks"]]
        # Cards taken later still exist now; cards the pool lacks don't matter.
        memo: dict = {}
        mine = []
        for slot, (seat, cid, card) in enumerate(resolved):
            if max_picks is not None and slot >= max_picks:
                break
            if cid is not None and cid in remaining:
                ctx = BotContext(index, combos, list(remaining), by_seat, seat, order, slot, d.get("per_seat", 45),
                                 Persona("steady", temperature=0.001), tuning or None, people=None, memo=memo)
                ranked = [c for _, c, _ in eng.score_pool(ctx)]
                rank = ranked.index(cid) + 1
                top = [index[c].name for c in ranked[:3]]
                row = {"video": d["video"], "slot": slot + 1, "seat": seat + 1, "lsv": seat + 1 == d["lsv"],
                       "card": index[cid].name, "rank": rank, "top3": top, "round": len(by_seat[seat]) + 1}
                rows.append(row)
                mine.append(row)
                for v in d.get("verdicts", []):
                    if v["seat"] == seat + 1 and _norm(v["worse"]) == _norm(card):
                        better = resolve(names, v["better"])
                        if better in ranked:
                            row["verdict"] = {"better": v["better"], "better_rank": ranked.index(better) + 1,
                                              "ok": ranked.index(better) < ranked.index(cid)}
            if cid is not None:
                remaining.discard(cid)
                by_seat[seat].append(cid)
        per_draft.append({"video": d["video"], **summarise(mine)})
    return {"engine": engine, "overall": summarise(rows), "lsv": summarise([r for r in rows if r["lsv"]]),
            "early": summarise([r for r in rows if r["round"] <= 6]),
            "drafts": per_draft, "verdicts": [r for r in rows if "verdict" in r], "rows": rows}


def summarise(rows: List[dict]) -> dict:
    if not rows:
        return {"picks": 0}
    ranks = [r["rank"] for r in rows]
    n = len(ranks)
    return {"picks": n, "top1": round(sum(r == 1 for r in ranks) / n, 3), "top3": round(sum(r <= 3 for r in ranks) / n, 3),
            "top10": round(sum(r <= 10 for r in ranks) / n, 3), "median": median(ranks),
            "mean_log": round(sum(__import__("math").log(r) for r in ranks) / n, 3)}
