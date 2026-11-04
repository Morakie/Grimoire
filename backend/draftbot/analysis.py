"""Cube analysis: a breakdown of a whole cube for the Cube Analysis page (/cube-analysis).

Built from the same card pool the bots use (a Bot Brain pool: CubeCobra Elo and partners, deck-type membership,
Spellbook combos) plus CubeCobra's real decks (cube_meta.json), so the page shows what the bots see:

- every card with its Elo rank, roles and the deck types it fits;
- every deck type the cube supports, how viable it is, and the cards that go in it (with how often real
  drafters played them in that kind of deck);
- every combo, with what it does and the deck types it belongs to;
- an overview: colours, curve, fixing, interaction, and how deep each colour pair is.

Pure Python, no network: the server hands it a loaded pool.
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional, Sequence

from .combos import Combo
from .cubemeta import _key as meta_key
from .cubemeta import load as load_meta
from .decktypes import CORE, DECK_TYPES, KEYS
from .features import CardInfo

COLOURS = "WUBRG"
PAIRS = ("WU", "UB", "BR", "RG", "GW", "WB", "UR", "BG", "RW", "GU")
PAIR_NAMES = {"WU": "Azorius", "UB": "Dimir", "BR": "Rakdos", "RG": "Gruul", "GW": "Selesnya", "WB": "Orzhov",
              "UR": "Izzet", "BG": "Golgari", "RW": "Boros", "GU": "Simic"}

FIT_MIN = 0.3          # deck-type fit a card needs to be listed under that deck type
FIT_STRONG = 0.5       # ...to count towards the deck type's depth
DECK_SIZE = 23         # non-land cards in a 40-card deck

# CubeCobra plan (cube_meta.json archetypes) that each deck type is played as, most specific first.
# Real drafters' decks are labelled by colours + plan, so a deck type only maps when its plan is clear.
PLAN_OF: Dict[str, tuple] = {
    "storm": ("Storm",), "reanimator": ("Reanimator",), "cheat": ("Sneak / cheat",), "control": ("Control",),
    "ramp": ("mono G Ramp", "Ramp"), "blink": ("Blink",), "tempo": ("UR Tempo", "Tempo"),
    "tolarian": ("U Artifacts", "Artifacts"), "workshop": ("Artifacts",), "artifacts": ("Artifacts",),
    "welder": ("R Artifacts", "Artifacts"), "white_aggro": ("mono W Aggro", "W Aggro", "Aggro"),
    "red_aggro": ("mono R Aggro", "R Aggro", "Aggro"), "gruul": ("RG Aggro", "Aggro"),
}

# Roles worth counting on the overview (features.ROLE_PATTERNS), with display names.
ROLE_NAMES = {
    "removal": "Removal", "counter": "Counterspells", "sweeper": "Sweepers", "draw": "Card draw", "tutor": "Tutors",
    "fast_mana": "Fast mana", "ritual": "Rituals", "reanimate": "Reanimation", "cheat": "Cheat into play",
    "token_maker": "Token makers", "flicker": "Blink", "hate_artifact": "Artifact hate",
    "hate_graveyard": "Graveyard hate",
}


def _colours(c: CardInfo) -> str:
    return "".join(x for x in COLOURS if x in c.need)


def _column(card: dict, c: CardInfo) -> str:
    """CubeCobra-style column: W/U/B/R/G, C (colourless), M (multicolour) or L (lands)."""
    if c.is_land:
        return "L"
    cols = [x for x in (card.get("colors") or []) if x in COLOURS]
    if not cols:      # double-faced cards keep their colours on the faces: fall back to what it needs to cast
        cols = [x for x in COLOURS if x in c.need or x in c.hybrid]
    if not cols:
        return "C"
    return cols[0] if len(cols) == 1 else "M"


def _type_group(c: CardInfo) -> str:
    for t in ("land", "creature", "planeswalker", "battle", "instant", "sorcery", "artifact", "enchantment"):
        if t in c.types:
            return t
    return "other"


def _fit(c: CardInfo, t: str) -> float:
    return 1.0 if t in c.key_of else float(c.deck.get(t, 0.0))


def _plan_rows(t: str, meta: dict) -> tuple:
    """(plan label, decks, {card key: (rate %, lift)}) for the CubeCobra plan a deck type maps to."""
    arch = meta.get("archetypes") or {}
    for label in PLAN_OF.get(t, ()):
        row = arch.get(label)
        if row:
            return label, int(row.get("decks") or 0), {meta_key(n): (float(r), float(l)) for n, r, l in row.get("cards") or []}
    return "", 0, {}


def _played(rows: dict, c: CardInfo) -> Optional[tuple]:
    k = meta_key(c.name)
    return rows.get(k) or rows.get(k.split(" // ")[0])


def viability(keys: int, depth: int, combos: int) -> tuple:
    """(score 0..100, label) for a deck type: key cards make it draftable at all, depth (cards that fit well)
    makes a full deck, combos add a little."""
    score = round(50 * min(keys, 6) / 6 + 40 * min(depth, 2 * DECK_SIZE) / (2 * DECK_SIZE) + 10 * min(combos, 5) / 5)
    if keys == 0:
        score = min(score, 20)
    label = "Strong" if score >= 70 else "Viable" if score >= 45 else "Thin" if score >= 25 else "Unlikely"
    return score, label


def cube_analysis(index: Dict[str, CardInfo], combos: List[Combo], cards: Sequence[dict],
                  meta: Optional[dict] = None) -> dict:
    meta = meta if meta is not None else load_meta()
    rows = [(card, index[card["id"]]) for card in cards if card.get("id") in index]
    by_elo = sorted((c for _, c in rows), key=lambda c: -c.elo)
    rank = {c.id: i + 1 for i, c in enumerate(by_elo)}

    # ---- combos, with the deck types every piece fits
    combo_rows = []
    for i, cb in enumerate(combos):
        pieces = [index[p] for p in cb.pieces if p in index]
        if len(pieces) < 2:
            continue
        need = set()
        for p in pieces:
            need |= set(p.need)
        decks = [t for t in DECK_TYPES if all(_fit(p, t) >= FIT_MIN for p in pieces)]
        combo_rows.append({"i": i, "pieces": [p.id for p in pieces], "weight": round(cb.weight, 3),
                           "produces": list(cb.produces), "sid": cb.sid,
                           "colors": "".join(x for x in COLOURS if x in need), "decks": decks,
                           "elo": round(sum(p.elo for p in pieces) / len(pieces))})
    combo_rows.sort(key=lambda r: (-r["weight"], len(r["pieces"])))
    combos_of: Dict[str, int] = Counter(p for r in combo_rows for p in r["pieces"])

    # ---- cards
    out_cards = []
    for card, c in rows:
        fits = sorted(((t, _fit(c, t)) for t in DECK_TYPES if _fit(c, t) >= FIT_MIN), key=lambda x: -x[1])
        out_cards.append({
            "id": c.id, "name": c.name, "mana_cost": card.get("mana_cost") or "", "cmc": c.cmc,
            "type_line": card.get("type_line") or "", "type": _type_group(c), "colors": _colours(c),
            "identity": "".join(x for x in COLOURS if x in c.identity), "produces": "".join(x for x in COLOURS if x in c.produces),
            "column": _column(card, c), "image": card.get("image"), "art_crop": card.get("art_crop"),
            "elo": round(c.elo), "rank": rank[c.id], "roles": sorted(r for r in c.roles if r in ROLE_NAMES),
            "keys": sorted(c.key_of), "fits": [[t, round(v, 2)] for t, v in fits], "combos": combos_of.get(c.id, 0),
            "links": sum(1 for p, s in c.partners.items() if s >= 1 and p in index),
        })

    # ---- deck types
    core_names = {t: {n.lower() for n in CORE.get(t, ())} for t in DECK_TYPES}
    decks = []
    for t in DECK_TYPES:
        plan, plan_decks, played_rows = _plan_rows(t, meta)
        members = []
        for _, c in rows:
            fit = _fit(c, t)
            played = _played(played_rows, c)
            if fit < FIT_MIN and not (played and played[1] >= 1.3):
                continue
            role = ("key" if t in c.key_of else "core" if c.name.lower() in core_names[t] or c.name.split(" // ")[0].lower() in core_names[t]
                    else "fits" if fit >= FIT_MIN else "played")
            members.append({"id": c.id, "fit": round(fit, 2), "role": role,
                            "rate": played[0] if played else None, "lift": played[1] if played else None})
        ids = {m["id"] for m in members}
        keys = sum(1 for m in members if m["role"] == "key")
        strong = [m for m in members if m["fit"] >= FIT_STRONG]
        depth = sum(1 for m in strong if not index[m["id"]].is_land)
        in_deck = [r for r in combo_rows if t in r["decks"]]
        score, label = viability(keys, depth, len(in_deck))
        weight = Counter()
        for m in strong:
            for x in index[m["id"]].need:
                weight[x] += m["fit"]
        total = sum(weight.values()) or 1.0
        colour_share = {x: round(weight[x] / total, 2) for x in COLOURS if weight[x] / total >= 0.08}
        nonland = sorted((index[m["id"]] for m in strong if not index[m["id"]].is_land), key=lambda c: -c.elo)[:DECK_SIZE]
        decks.append({
            "type": t, "score": score, "label": label, "keys": keys, "keys_listed": len(KEYS.get(t, ())),
            "depth": depth, "members": members, "combos": [r["i"] for r in in_deck],
            "colors": colour_share, "avg_elo": round(sum(c.elo for c in nonland) / len(nonland)) if nonland else 0,
            "seats": max(0, min(3, int(min(keys / 2.0, depth / float(DECK_SIZE))))),
            "plan": plan, "plan_decks": plan_decks, "missing_keys": [n for n in KEYS.get(t, ()) if n.lower() not in
                                                                    {index[i].name.lower() for i in ids}][:12],
        })
    decks.sort(key=lambda d: (-d["score"], d["type"]))

    return {"cards": out_cards, "decks": decks, "combos": combo_rows, "overview": _overview(rows),
            "roles": ROLE_NAMES, "pair_names": PAIR_NAMES,
            "meta": {"export": (meta.get("source") or {}).get("export_updated", ""),
                     "with_partners": sum(1 for _, c in rows if c.partners)}}


def _overview(rows) -> dict:
    cards = [c for _, c in rows]
    columns = Counter()
    types = Counter()
    curve: Dict[str, List[int]] = {}
    elo_sum = Counter()
    for card, c in rows:
        col = _column(card, c)
        columns[col] += 1
        types[_type_group(c)] += 1
        elo_sum[col] += c.elo
        if not c.is_land:
            curve.setdefault(col, [0] * 8)[min(7, int(c.cmc))] += 1
    roles = {}
    for r in ROLE_NAMES:
        per = Counter()
        for c in cards:
            if r in c.roles:
                per[_colours(c) if len(c.need) <= 1 else "M"] += 1
        roles[r] = {"total": sum(per.values()), "by": dict(per)}
    # Fixing: lands and mana sources that make two or more colours, per colour pair.
    fixing = {p: sum(1 for c in cards if c.is_fixing and set(p) <= set(c.produces)) for p in PAIRS}
    # Colour pairs: the cards a two-colour deck could play (its colours' cards and colourless ones), and how
    # strong its best 23 non-land cards are.
    pairs = []
    for p in PAIRS:
        ok = [c for c in cards if not c.is_land and set(c.need) <= set(p)]
        gold = sum(1 for c in ok if set(c.need) == set(p))
        best = sorted(ok, key=lambda c: -c.elo)[:DECK_SIZE]
        pairs.append({"pair": p, "name": PAIR_NAMES[p], "playable": len(ok), "gold": gold, "fixing": fixing[p],
                      "top_elo": round(sum(c.elo for c in best) / len(best)) if best else 0})
    pairs.sort(key=lambda r: -r["top_elo"])
    return {"total": len(cards), "columns": dict(columns), "types": dict(types), "curve": curve,
            "avg_elo": {k: round(elo_sum[k] / columns[k]) for k in columns},
            "roles": roles, "pairs": pairs,
            "lands": {"total": sum(1 for c in cards if c.is_land),
                      "fixing": sum(1 for c in cards if c.is_land and len(c.produces) >= 2)}}
