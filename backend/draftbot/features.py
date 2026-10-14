"""Per-card features the bots reason about.

Everything here is derived from the card data already stored on a draft (Scryfall fields plus
CubeCobra Elo), so it works for any cube. Custom cards (``is_custom``) are skipped entirely.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import median
from typing import Dict, FrozenSet, Iterable, List, Optional

COLORS = "WUBRG"
BASIC_TYPES = {"plains": "W", "island": "U", "swamp": "B", "mountain": "R", "forest": "G"}

_SYMBOL = re.compile(r"\{([^}]+)\}")


def _cost_colors(mana_cost: str) -> FrozenSet[str]:
    """Colors a card *requires* to cast. Hybrid and Phyrexian symbols are treated as flexible
    (castable without that color), so Dismember or Kitchen Finks don't lock a lane."""
    need = set()
    for sym in _SYMBOL.findall(mana_cost or ""):
        parts = sym.split("/")
        if len(parts) > 1:
            continue  # hybrid / phyrexian: optional
        if sym in COLORS:
            need.add(sym)
    return frozenset(need)


def _produced_colors(card: dict, text: str) -> FrozenSet[str]:
    """Colors a land (or mana rock/dork) can help produce: identity plus fetchable basic types."""
    produced = set(card.get("color_identity") or [])
    for word, color in BASIC_TYPES.items():
        if re.search(rf"\b{word}\b", text):
            produced.add(color)
    if "any color" in text or "one mana of any" in text:
        produced.update(COLORS)
    return frozenset(produced)


# Role tags read from rules text. Deliberately about *function*, never creature type.
ROLE_PATTERNS = {
    "removal": r"(destroy|exile) target (creature|nonland|permanent|artifact|planeswalker|tapped)|deals? (\d+|x) damage to (any target|target creature)|target creature gets -\d|sacrifices? (a|an) (creature|nontoken)|exile up to one (other )?target",
    "counter": r"counter target",
    "sweeper": r"(destroy|exile) all (creatures|nonland)|each creature|all creatures get -",
    "draw": r"draws? (a|two|three|four|seven|x|that many) cards?|investigate",
    "tutor": r"search your library for (a|an|up to one) (?!basic|land|plains|island|swamp|mountain|forest)",
    "ritual": r"add \{[wubrgc]\}\{[wubrgc]\}\{[wubrgc]\}",
    "reanimate": r"(return|put) (target |a |up to one )?(creature card|the top creature card|target card).{0,40}graveyard (to|onto) the battlefield|enchant creature card in a graveyard|from your graveyard to the battlefield",
    "cheat": r"put (a|an|that) (creature|artifact|permanent)? ?card from your hand onto the battlefield|creature card from your hand onto the battlefield",
    "artifact_cheat": r"search your library for an artifact card, put (it|that card) onto the battlefield",
    "self_mill": r"put that card into your graveyard|mills? (two|three|four|\d+|x) cards|surveil",
    "discard_outlet": r"(then )?discard (a|two|three|x) cards?|discard (a|two) cards?, then draw|draws? .*then discards?",
    "sac_outlet": r"sacrifice (a|another) (creature|artifact|permanent)[^.]*:",
    "death_payoff": r"whenever (a|another|one or more)[^.]* (creature|creatures)[^.]* (dies|die|is put into a graveyard)",
    "spells_payoff": r"whenever you cast (an|a) (instant|noncreature|instant or sorcery)|magecraft|prowess|storm",
    "artifact_payoff": r"for each artifact you control|whenever you cast an artifact|tap an untapped artifact|artifacts? you control",
    "token_maker": r"create (a|an|two|three|x|that many)[^.]*token",
    "anthem": r"creatures you control get \+",
    "graveyard_cast": r"from your graveyard|flashback|escape|you may cast[^.]*graveyard",
}
_ROLE_RE = {k: re.compile(v) for k, v in ROLE_PATTERNS.items()}


@dataclass
class CardInfo:
    id: str
    name: str
    cmc: float
    types: FrozenSet[str]
    need: FrozenSet[str]          # colors required to cast
    produces: FrozenSet[str]      # colors it helps produce (lands / mana sources)
    identity: FrozenSet[str]
    elo: float
    power: float                  # normalised 0..1 power within this cube
    roles: FrozenSet[str] = field(default_factory=frozenset)
    combos: List[int] = field(default_factory=list)   # indices into the draft's combo list
    partners: Dict[str, float] = field(default_factory=dict)  # CubeCobra package partners in this cube

    @property
    def is_land(self) -> bool:
        return "land" in self.types

    @property
    def is_creature(self) -> bool:
        return "creature" in self.types

    @property
    def is_fixing(self) -> bool:
        return len(self.produces) >= 2 and (self.is_land or "mana" in self.roles)


def _types(type_line: str) -> FrozenSet[str]:
    front = (type_line or "").split("//")[0].lower()
    main = front.split("—")[0]
    return frozenset(w for w in re.findall(r"[a-z]+", main))


_AGGRO_KEYWORDS = re.compile(r"\b(haste|first strike|double strike|prowess|menace|trample|flying|dash)\b|whenever [^.]* attacks|can't block|(gets|get) \+\d")
_BURN = re.compile(r"deals? (\d+|x) damage to (any target|target (player|opponent|creature or player|player or planeswalker))|each opponent loses")


def _roles(card: dict, types: FrozenSet[str], text: str) -> FrozenSet[str]:
    roles = {name for name, rx in _ROLE_RE.items() if rx.search(text)}
    cmc = card.get("cmc") or 0
    if "artifact" in types:
        roles.add("artifact")
    if "planeswalker" in types:
        roles.add("planeswalker")
    if "equipment" in (card.get("type_line") or "").lower():
        roles.add("equipment")
    if "creature" in types and cmc <= 3 and (cmc <= 1 or _AGGRO_KEYWORDS.search(text)):
        roles.add("aggro_creature")
    if _BURN.search(text) and not ("creature" in types and cmc >= 4):
        roles.add("burn")
    if cmc <= 1 and "draw" in roles and not ("creature" in types):
        roles.add("cantrip")
    if ("creature" in types and cmc >= 5) or ("planeswalker" in types and cmc >= 4):
        roles.add("finisher")
    if "creature" in types and 2 <= cmc <= 5 and (({"draw", "removal", "token_maker"} & roles) or re.search(r"initiative|monarch|venture", text)):
        roles.add("value_creature")
    if "creature" in types and (card.get("cmc") or 0) >= 6:
        roles.add("fatty")  # reanimation / cheat-into-play target
    if "artifact" in types and (card.get("cmc") or 0) >= 6:
        roles.add("big_artifact")
    if not ("land" in types) and re.search(r"add \{|add one mana|add (two|three) mana|add mana", text):
        roles.add("mana")
        if "creature" in types or re.search(r"search your library for (a|up to \w+) (basic )?lands?", text):
            roles.add("ramp")
    if "creature" in types and (card.get("cmc") or 0) <= 2:
        roles.add("cheap_threat")
    return frozenset(roles)


def _estimate_elo(card: dict, types: FrozenSet[str], text: str, elos: List[float], mid: float) -> float:
    """Rating for a card with no CubeCobra Elo (new or rarely-cubed cards).

    Defaults to the cube median, except for fast mana: a 0–1 mana non-creature that taps for mana
    (a "Mox") is one of the strongest card types in any cube, so it is rated like the cube's best
    cards instead of an average one."""
    ranked = sorted(elos)
    def pct(q):
        return ranked[min(len(ranked) - 1, int(len(ranked) * q))] if ranked else mid
    cmc = card.get("cmc") or 0
    taps_for_mana = re.search(r"\{t\}[^.]*: add", text) is not None
    if "creature" not in types and "land" not in types and taps_for_mana:
        if cmc == 0:
            return pct(0.99)
        if cmc == 1:
            return pct(0.95)
    return mid


def build_card_index(cube: Iterable[dict], stats: Optional[dict] = None) -> Dict[str, CardInfo]:
    """Build CardInfo for every non-custom card in a cube (cube entries are draft card dicts).

    `stats` (optional, from draftbot.cardstats.draft_stats) supplies live CubeCobra Elo, which replaces
    the CSV value, and each card's package partners within the cube."""
    stats = stats or {}
    live_elo = stats.get("elo") or {}
    partners = stats.get("partners") or {}
    cards = [dict(c, elo=live_elo.get(c["id"]) or c.get("elo")) for c in cube if not c.get("is_custom")]
    elos = [float(c["elo"]) for c in cards if c.get("elo")]
    mid = median(elos) if elos else 1200.0
    lo = sorted(elos)[int(len(elos) * 0.05)] if elos else mid - 200
    hi = sorted(elos)[int(len(elos) * 0.95) - 1] if elos else mid + 200
    span = max(hi - lo, 1.0)

    index: Dict[str, CardInfo] = {}
    for c in cards:
        text = (c.get("oracle_text") or "").lower()
        types = _types(c.get("type_line", ""))
        elo = float(c.get("elo") or _estimate_elo(c, types, text, elos, mid))
        x = (elo - lo) / span                      # ~0 at the 5th percentile, 1 at the 95th
        power = max(-0.15, x if x <= 1 else 1 + 0.7 * (x - 1))   # bombs keep standing out, gently compressed
        need = _cost_colors(c.get("mana_cost", ""))
        if "land" in types:
            need = frozenset()
        index[c["id"]] = CardInfo(
            id=c["id"],
            name=c.get("name", ""),
            cmc=float(c.get("cmc") or 0),
            types=types,
            need=need,
            produces=_produced_colors(c, text) if ("land" in types or "add" in text) else frozenset(),
            identity=frozenset(c.get("color_identity") or []),
            elo=elo,
            power=power,
            roles=_roles(c, types, text),
            partners=dict(partners.get(c["id"], {})),
        )
    return index


def front_name(name: str) -> str:
    return (name or "").split(" // ")[0].strip()


def lookup_by_name(index: Dict[str, CardInfo]) -> Dict[str, str]:
    """Lower-cased full and front-face names → card id."""
    out: Dict[str, str] = {}
    for cid, info in index.items():
        out.setdefault(info.name.lower(), cid)
        out.setdefault(front_name(info.name).lower(), cid)
    return out


def castable(card: CardInfo, lane: Optional[FrozenSet[str]]) -> bool:
    return lane is None or card.need <= lane
