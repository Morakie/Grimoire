"""Bot Brain in the browser: the same engine, run locally in the page (Pyodide) instead of on the server.

The page downloads a saved pool once (GET /api/lab/pool-export), keeps it in the browser, and calls these
functions with JSON strings: no server calls while turning knobs or re-drafting. Every function returns a
JSON string. Nothing here touches the network.
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

from .combos import attach_combos, combos_from_dicts, with_cube_combos
from .decktypes import deck_strength
from .engine import best_pair, coloured_spells
from .features import build_card_index
from .lab import (DraftRun, card_dossier, clean_tuning, knob_list, lab_view, pick_slot, source_payload)


class Session:
    """One loaded pool and at most one draft being run a few picks at a time."""

    def __init__(self):
        self.index = None
        self.combos: list = []
        self.cards: List[dict] = []
        self.run: Optional[DraftRun] = None

    # ---------------------------------------------------------------- pool
    def load(self, raw: str) -> str:
        data = json.loads(raw)
        self.cards = data["cards"]
        self.index = build_card_index(self.cards, data.get("stats"))
        self.combos = with_cube_combos(self.index, combos_from_dicts(data.get("combos") or []))
        attach_combos(self.index, self.combos)
        self.run = None
        return json.dumps(source_payload(self.index, self.combos, self.cards))

    def card(self, cid: str) -> str:
        if cid not in self.index:
            return json.dumps({"error": "Card not found in this pool"})
        return json.dumps(card_dossier(self.index, self.combos, cid))

    # ---------------------------------------------------------------- drafts
    def run_start(self, raw: str) -> str:
        """Start a draft: {seats, picks, seed, tuning, start, tuned_seats, stop}. Returns its order and the
        picks kept from `start`."""
        cfg = json.loads(raw)
        self.run = DraftRun(self.index, self.combos, int(cfg.get("seats", 8)), int(cfg.get("picks", 45)),
                            int(cfg.get("seed", 0)), clean_tuning(cfg.get("tuning")) or None, cfg.get("start") or [],
                            cfg.get("tuned_seats"), cfg.get("stop"), bool(cfg.get("personas")))
        return json.dumps({"order": self.run.order, "per_seat": self.run.per, "kept": self.run.kept,
                           "picks": self.run.picks, "end": self.run.end,
                           "personas": [{"archetype": p.archetype, "lean": p.lean} for p in self.run.personas]})

    def run_step(self, n: int) -> str:
        """Make up to n more picks of the current draft. When it's finished, also returns the seat summaries."""
        if self.run is None:
            return json.dumps({"picks": [], "done": True})
        made = self.run.step(int(n))
        out = {"picks": made, "done": self.run.done}
        if self.run.done:
            out["seats"] = self.run.result()["seats"]
        return json.dumps(out)

    def view(self, raw: str) -> str:
        """The Bot Lab view of one pick (same as POST /api/lab/view)."""
        body = json.loads(raw)
        order, picks = body["order"], [p for p in body["picks"] if p.get("card_id") in self.index]
        per_seat = max(1, len(order) // max(1, len(set(order))))
        seat = None if body.get("slot") is not None else body.get("seat")
        slot = pick_slot(order, len(picks), seat, body.get("pick_no"), body.get("slot"))
        out = lab_view(self.index, self.combos, order, picks, per_seat, slot, clean_tuning(body.get("tuning")),
                       frozenset(), (), True, max(5, min(int(body.get("n", 15)), 40)))
        out["knobs"] = knob_list()
        return json.dumps(out)

    def lanes(self, raw: str) -> str:
        """Every seat's colours and deck types just before table pick `slot` (who is in which lane)."""
        body = json.loads(raw)
        slot = int(body["slot"])
        by_seat: Dict[int, List[str]] = {s: [] for s in set(body["order"])}
        for p in body["picks"]:
            if p["order"] < slot and p["card_id"] in self.index:
                by_seat[p["seat_index"]].append(p["card_id"])
        out = []
        for seat in sorted(by_seat):
            pool = [self.index[c] for c in by_seat[seat]]
            pair = best_pair(pool) if coloured_spells(pool) >= 2 else frozenset()
            decks = deck_strength(pool)
            out.append({"seat": seat, "pair": "".join(c for c in "WUBRG" if c in pair),
                        "decks": {t: round(v, 2) for t, v in decks.items() if v >= 0.1}})
        return json.dumps({"slot": slot, "seats": out})

    def web(self, raw: str) -> str:
        """A seat's synergy web: its cards and the CubeCobra links between them, plus how the cards it is
        looking at (`candidates`) link into it."""
        body = json.loads(raw)
        owned = [c for c in body.get("owned", []) if c in self.index]
        cands = [c for c in body.get("candidates", []) if c in self.index and c not in owned]
        ids = set(owned) | set(cands)
        nodes = []
        for cid in owned + cands:
            c = self.index[cid]
            deck = max(c.deck.items(), key=lambda kv: kv[1])[0] if c.deck else ""
            nodes.append({"id": cid, "name": c.name, "colors": "".join(x for x in "WUBRG" if x in c.need),
                          "elo": round(c.elo), "land": c.is_land, "key": sorted(c.key_of),
                          "deck": sorted(c.key_of)[0] if c.key_of else deck, "candidate": cid in cands})
        links: Dict[tuple, float] = {}      # each pair once, at its stronger direction
        for a in ids:
            for b, s in self.index[a].partners.items():
                if b in ids and b != a:
                    key = (a, b) if a < b else (b, a)
                    links[key] = max(links.get(key, 0.0), s)
        edges = [[a, b, s] for (a, b), s in links.items()]
        return json.dumps({"nodes": nodes, "edges": edges})


SESSION = Session()
