"""Commander deck checks: legality and a bracket estimate.

`evaluate()` is pure (no network) so it is easy to test. The lists it needs, Game Changers and the
Commander banned list from Scryfall plus two-card combos from Commander Spellbook, are fetched by
`fetch_reference()` / `fetch_two_card_combos()` and cached in memory.

Bracket rules follow the official Commander Brackets (beta) as published by Wizards:
  1-2 (Exhibition / Core): no Game Changers, no mass land denial, no two-card infinite combos,
                           extra turns only in small numbers and never chained
  3 (Upgraded):            up to three Game Changers, no mass land denial, no early two-card combos,
                           no chained extra turns
  4 (Optimized):           no restrictions beyond the banned list
  5 (cEDH):                like 4, but built for tournament play, which a card list can't show
The estimate is the lowest bracket the list fits. Intent matters as much as cards, so it is a guide
for the pregame conversation rather than a verdict.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Dict, Iterable, List, Optional, Set

log = logging.getLogger(__name__)

SCRYFALL = "https://api.scryfall.com"
SPELLBOOK_URL = "https://backend.commanderspellbook.com/find-my-combos"
HEADERS = {"User-Agent": "GrimoireDeckBuilder/1.0", "Accept": "application/json"}

# ---------------------------------------------------------------------------
# Card text helpers
# ---------------------------------------------------------------------------

BASIC_NAMES = {"plains", "island", "swamp", "mountain", "forest", "wastes",
               "snow-covered plains", "snow-covered island", "snow-covered swamp",
               "snow-covered mountain", "snow-covered forest", "snow-covered wastes"}

# Mass land denial named in the bracket guidance, plus close relatives. Pattern matching below
# catches most of the rest ("destroy all lands", "each player sacrifices ... lands").
MLD_NAMES = {
    "armageddon", "ravages of war", "catastrophe", "decree of annihilation", "jokulhaups",
    "obliterate", "ruination", "sunder", "wildfire", "destructive force", "boom // bust",
    "impending disaster", "death cloud", "epicenter", "winter orb", "static orb", "rising waters",
    "hokori, dust drinker", "global ruin", "devastation", "keldon firebombers", "worldfire",
    "acid rain", "tsunami", "flashfires", "thoughts of ruin", "upheaval", "apocalypse",
    "cataclysm", "hall of gemstone",
}
MLD_PATTERNS = [
    re.compile(r"\b(destroy|exile)s? all (other |non[a-z]+ )?lands\b"),
    re.compile(r"\breturn all lands\b"),
    re.compile(r"\beach player sacrifices (all|.{0,40}?\blands?\b)"),
    re.compile(r"\bsacrifices? all lands\b"),
    re.compile(r"\blands don'?t untap during their controllers'? untap steps\b"),
]
EXTRA_TURN = re.compile(r"\btakes? an extra turn\b|\btake (two|three|\w+) extra turns\b")
TUTOR = re.compile(r"search(es)? (your|their) library for (a|an|any|up to \w+) (?!basic)(?![a-z ]*\bland\b)")
ANY_NUMBER = re.compile(r"a deck can have (any number|up to \w+) (of )?cards named")


def _text(card: dict) -> str:
    return (card.get("oracle_text") or "").lower()


def _types(card: dict) -> str:
    return (card.get("type_line") or "").lower()


def _front_name(name: str) -> str:
    return (name or "").split(" // ")[0].strip().lower()


def _names(card: dict) -> Set[str]:
    full = (card.get("name") or "").strip().lower()
    return {full, _front_name(full)} - {""}


def is_basic(card: dict) -> bool:
    return "basic" in _types(card) and "land" in _types(card) or _front_name(card.get("name", "")) in BASIC_NAMES


def is_mld(card: dict) -> bool:
    if _names(card) & MLD_NAMES:
        return True
    t = _text(card)
    return any(p.search(t) for p in MLD_PATTERNS)


def is_extra_turn(card: dict) -> bool:
    return bool(EXTRA_TURN.search(_text(card)))


def is_tutor(card: dict) -> bool:
    return "land" not in _types(card) and bool(TUTOR.search(_text(card)))


def can_be_commander(card: dict) -> bool:
    t = _types(card)
    first_face = t.split(" // ")[0]
    if "legendary" in first_face and "creature" in first_face:
        return True
    if "can be your commander" in _text(card):
        return True
    return "background" in t and "legendary" in t   # only alongside a "Choose a Background" commander


def _partner_kind(card: dict) -> Optional[str]:
    """Which partner-style keyword the card has, or None."""
    for line in _text(card).split("\n"):
        line = line.strip()
        m = re.match(r"partner with ([^(]+?)\s*(\(|$)", line)
        if m:
            return "with:" + m.group(1).strip()
        m = re.match(r"partner\s*[—-]\s*([^(]+?)\s*(\(|$)", line)
        if m:
            return "group:" + m.group(1).strip()
        if line == "partner" or line.startswith("partner ("):
            return "partner"
        if line.startswith("friends forever"):
            return "friends"
        if line.startswith("choose a background"):
            return "choose-background"
        if line.startswith("doctor's companion"):
            return "companion-of-doctor"
    return None


def valid_pair(a: dict, b: dict) -> bool:
    ka, kb = _partner_kind(a), _partner_kind(b)
    if ka == kb and ka in ("partner", "friends") or (ka and ka.startswith("group:") and ka == kb):
        return True
    if ka and ka.startswith("with:") and ka[5:] in _names(b) and kb and kb.startswith("with:") and kb[5:] in _names(a):
        return True
    for x, kx, y in ((a, ka, b), (b, kb, a)):
        if kx == "choose-background" and "background" in _types(y):
            return True
        if kx == "companion-of-doctor" and "time lord doctor" in _types(y):
            return True
    return False


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

BRACKET_NAMES = {1: "Exhibition", 2: "Core", 3: "Upgraded", 4: "Optimized", 5: "cEDH"}


def evaluate(commanders: List[dict], cards: List[dict], game_changers: Iterable[str],
             banned: Iterable[str], combos: Optional[List[List[str]]] = None,
             reference_ok: bool = True, combos_ok: bool = True) -> dict:
    """Check a Commander deck. `cards` is the main deck (not including commanders)."""
    gc = {n.lower() for n in game_changers}
    banned_set = {n.lower() for n in banned}
    everything = list(commanders) + list(cards)
    issues: List[dict] = []

    def issue(kind: str, text: str, names: Iterable[str] = ()):
        issues.append({"kind": kind, "text": text, "cards": sorted(set(names))})

    # Commanders
    if not commanders:
        issue("commander", "Choose a commander: hover a card and click its crown, or drag it to the Command Zone.")
    elif len(commanders) > 2:
        issue("commander", "A deck can have at most two commanders.", [c["name"] for c in commanders])
    else:
        for c in commanders:
            bg_only = "background" in _types(c) and "creature" not in _types(c)
            if not can_be_commander(c) or (bg_only and len(commanders) == 1):
                issue("commander", f"{c['name']} can't be a commander.", [c["name"]])
        if len(commanders) == 2 and not valid_pair(commanders[0], commanders[1]):
            issue("commander", "These two can't be paired: both need Partner (or Partner with each other, "
                  "Friends forever, a Background with Choose a Background, or Doctor's companion with a Doctor).",
                  [c["name"] for c in commanders])

    # Colour identity
    identity = set()
    for c in commanders:
        identity.update(c.get("color_identity") or [])
    if commanders:
        off = [c["name"] for c in cards if not set(c.get("color_identity") or []) <= identity]
        if off:
            issue("identity", f"{len(off)} card{'s' if len(off) != 1 else ''} outside your commander's colour identity.", off)

    # Singleton
    dupes = [c["name"] for c in everything if (c.get("quantity") or 1) > 1 and not is_basic(c) and not ANY_NUMBER.search(_text(c))]
    if dupes:
        issue("singleton", "Only one copy of each card is allowed, apart from basic lands.", dupes)

    # Deck size
    total = sum(int(c.get("quantity") or 1) for c in everything)
    if total != 100:
        issue("size", f"The deck has {total} cards including commanders; it needs exactly 100.")

    # Banned
    if reference_ok:
        hits = [c["name"] for c in everything if _names(c) & banned_set]
        if hits:
            issue("banned", "Banned in Commander.", hits)

    # ---- Bracket ----
    gc_cards = sorted({c["name"] for c in everything if _names(c) & gc})
    mld = sorted({c["name"] for c in everything if is_mld(c)})
    turns = sorted({c["name"] for c in everything if is_extra_turn(c)})
    tutors = sorted({c["name"] for c in everything if is_tutor(c)})
    combos = combos or []

    bracket, reasons = 2, []
    if gc_cards:
        bracket = 3
        reasons.append(f"{len(gc_cards)} Game Changer{'s' if len(gc_cards) != 1 else ''}")
    if combos:
        bracket = max(bracket, 3)
        reasons.append(f"{len(combos)} two-card combo{'s' if len(combos) != 1 else ''} (Bracket 4 if it can win early)")
    if len(turns) >= 3:
        bracket = max(bracket, 3)
        reasons.append(f"{len(turns)} extra-turn cards (Bracket 4 if they can be chained)")
    if len(gc_cards) > 3:
        bracket = 4
        reasons.append("more than three Game Changers")
    if mld:
        bracket = 4
        reasons.append("mass land denial")
    if bracket == 2:
        reasons.append("no Game Changers, two-card combos or mass land denial")

    return {
        "legal": not issues,
        "issues": issues,
        "card_count": total,
        "bracket": {
            "estimate": bracket,
            "label": "1–2" if bracket == 2 else str(bracket),
            "name": "Exhibition / Core" if bracket == 2 else BRACKET_NAMES[bracket],
            "reasons": reasons,
            "complete": reference_ok and combos_ok,
        },
        "game_changers": gc_cards,
        "mass_land_denial": mld,
        "extra_turns": turns,
        "tutors": tutors,
        "combos": combos,
    }


# ---------------------------------------------------------------------------
# Reference data (cached)
# ---------------------------------------------------------------------------

_REF: Dict[str, object] = {"at": 0.0, "game_changers": [], "banned": []}
_REF_TTL = 12 * 3600
_REF_LOCK = asyncio.Lock()
_COMBO_CACHE: Dict[str, List[List[str]]] = {}


async def _search_names(hc, query: str) -> List[str]:
    names, url, params = [], f"{SCRYFALL}/cards/search", {"q": query, "unique": "cards"}
    for _ in range(10):
        r = await hc.get(url, params=params)
        if r.status_code != 200:
            raise RuntimeError(f"Scryfall {r.status_code} for {query}")
        payload = r.json()
        names.extend(c["name"] for c in payload.get("data", []))
        if not payload.get("has_more"):
            break
        url, params = payload["next_page"], None
        await asyncio.sleep(0.1)
    return names


async def fetch_reference() -> Dict[str, object]:
    """Game Changers and Commander banned list, refreshed twice a day. Returns ok=False on failure."""
    import httpx

    async with _REF_LOCK:
        if time.time() - float(_REF["at"]) < _REF_TTL and _REF["game_changers"]:
            return {**_REF, "ok": True}
        try:
            async with httpx.AsyncClient(timeout=20.0, headers=HEADERS) as hc:
                gcs = await _search_names(hc, "is:gamechanger")
                await asyncio.sleep(0.1)
                banned = await _search_names(hc, "banned:commander")
        except Exception as exc:
            log.warning("Commander reference lookup failed: %s", exc)
            return {**_REF, "ok": bool(_REF["game_changers"])}
        # Include each face name so "Boom // Bust" style cards match either way.
        expand = lambda ns: sorted({n for name in ns for n in (name, name.split(" // ")[0])})
        _REF.update(at=time.time(), game_changers=expand(gcs), banned=expand(banned))
        return {**_REF, "ok": True}


async def fetch_two_card_combos(names: List[str], timeout: float = 15.0) -> Optional[List[List[str]]]:
    """Two-card combos fully inside this list, from Commander Spellbook. None if the lookup failed."""
    import httpx

    names = sorted({_front_name(n) for n in names if n})
    key = "|".join(names)
    if key in _COMBO_CACHE:
        return _COMBO_CACHE[key]
    body = "\n".join(f"1 {n}" for n in names)
    try:
        async with httpx.AsyncClient(timeout=timeout, headers=HEADERS) as hc:
            r = await hc.post(SPELLBOOK_URL, content=body.encode("utf-8"), headers={"Content-Type": "text/plain"})
        if r.status_code != 200:
            log.warning("Commander Spellbook returned %s", r.status_code)
            return None
        variants = r.json().get("results", {}).get("included", [])
    except Exception as exc:
        log.warning("Commander Spellbook lookup failed: %s", exc)
        return None
    seen, out = set(), []
    for v in variants:
        if v.get("requires"):
            continue
        pieces = [(u.get("card") or {}).get("name", "") for u in v.get("uses", [])]
        pieces = [p for p in pieces if p]
        if len(pieces) != 2:
            continue
        k = tuple(sorted(pieces))
        if k not in seen:
            seen.add(k)
            out.append(list(k))
    if len(_COMBO_CACHE) > 500:
        _COMBO_CACHE.clear()
    _COMBO_CACHE[key] = out
    return out
