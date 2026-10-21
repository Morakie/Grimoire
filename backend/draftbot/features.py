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


def _hybrid_colors(mana_cost: str) -> FrozenSet[str]:
    """Colours of two-colour hybrid symbols ({U/R}, {W/B}). A card whose cost is only hybrid (Lutri, Lurrus)
    needs one of these colours, so it isn't colourless."""
    out = set()
    for sym in _SYMBOL.findall(mana_cost or ""):
        parts = sym.split("/")
        if len(parts) == 2 and all(x in COLORS for x in parts):
            out.update(parts)
    return frozenset(out)


def _heavy_colors(mana_cost: str) -> FrozenSet[str]:
    """Colours a card needs at least twice (Sheoldred's {2}{B}{B}): too heavy to splash."""
    syms = [sym for sym in _SYMBOL.findall(mana_cost or "") if sym in COLORS]
    return frozenset(c for c in set(syms) if syms.count(c) >= 2)


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
# "hate_*" tags mark answers to one kind of deck (sideboard cards): bots look at them late in the
# draft when someone at the table is building that deck (engine.table_targets).
ROLE_PATTERNS = {
    "hate_artifact": r"activated abilities of artifacts[^.]*can't be activated|destroy all (nonland )?artifacts|destroy (up to two|any number of) target artifacts|artifacts your opponents control (enter|don't)|artifact spells (your opponents cast )?cost \{",
    "hate_graveyard": r"exile (target player's|each opponent's|each player's|all) graveyards?|exile all cards from (all |target player's |each opponent's )?graveyards?|if a card (or token )?would be put into (an opponent's|a) graveyard from anywhere, exile|cards in graveyards (and libraries )?can't|can't cast spells from (their )?graveyards|nontoken creature would enter and it wasn't cast",
    "hate_counters": r"spells you control can't be countered|except during its controller's turn|counter target spell if it's blue|destroy target permanent if it's blue",
    "hate_creatures": r"creatures with power greater than the number|creatures without flying can't attack|can't attack you unless",
    "hate_spells": r"can't cast more than one spell|whenever a player casts their second spell|spells your opponents cast cost \{",
    # "exile up to one target" but not graveyard cards or our own permanents (Displacer Kitten blinks its own);
    # edicts only when an opponent sacrifices (a "Sacrifice a creature:" cost isn't removal).
    "removal": r"(destroy|exile) target (non\w+ )?(creature|nonland|permanent|artifact|planeswalker|tapped)|deals? (\d+|x) damage to (any target|target creature)|target creature gets -\d|(opponent|player)s? sacrifices? (a|an) (creature|nontoken)|exile up to one (other )?target (?!card)(?![^.]*you (control|own))|among any number of target creatures|deals that much damage to that (creature|permanent)",
    "counter": r"counter target",
    # Not "put a +1/+1 counter on each creature" (Ouroboroid) or "for each creature you control" (Gaea's Cradle).
    "sweeper": r"(destroy|exile) all (creatures|nonland)|(destroy|exile|damage to) each (other )?(creature|nonland)|all creatures get -|each creature[^.]{0,30} gets? -",
    "draw": r"draws? (a|two|three|four|seven|x|that many) cards?|investigate",
    "tutor": r"search your library for (a|an|up to one) (?!basic|land|plains|island|swamp|mountain|forest)",
    "ritual": r"add \{[wubrgc]\}\{[wubrgc]\}\{[wubrgc]\}",
    # Creature cards only: Sword of the Meek, Titania (lands) and Otharri return themselves or lands, not fatties.
    "reanimate": r"(return|put) (target |a |up to one )?(creature card|the top creature card|target card).{0,40}graveyard (to|onto) the battlefield|enchant creature card in a graveyard|creature cards?[^.]{0,40}from (your|a|their) graveyards? (to|onto) the battlefield",
    "cheat": r"put (a|an|that) (creature|artifact|permanent)? ?card from your hand onto the battlefield|creature card from your hand onto the battlefield",
    "artifact_cheat": r"search your library for an artifact card, put (it|that card) onto the battlefield",
    "self_mill": r"put that card into your graveyard|mills? (two|three|four|\d+|x) cards|surveil",
    "discard_outlet": r"(then )?discard (a|two|three|x) cards?|discard (a|two) cards?, then draw|draws? .*then discards?",
    "sac_outlet": r"sacrifice (a|another) (creature|artifact|permanent)[^.]*:",
    "death_payoff": r"whenever (a|another|one or more)[^.]* (creature|creatures)[^.]* (dies|die|is put into a graveyard)",
    "spells_payoff": r"whenever you cast (an|a) (instant|noncreature|instant or sorcery)|magecraft|prowess|storm",
    "artifact_payoff": r"for each artifact you control|whenever you cast an artifact|tap an untapped artifact|artifacts? you control",
    "token_maker": r"create (a|an|two|three|x|that many)[^.]*token|\b(investigate|mobilize|offspring|squad|amass|incubate)\b|for mirrodin!",
    "anthem": r"creatures you control get \+",
    "graveyard_cast": r"from your graveyard|flashback|escape|you may cast[^.]*graveyard",
    # Vintage-cube packages (enablers and payoffs, see combos.PACKAGES)
    "storm_payoff": r"(^|\n)storm\b|\bstorm \(",
    # Blinking OTHER creatures. Not cards that exile and return themselves transformed (Fable's chapter III,
    # Ajani): those aren't blink payoffs and were losing most of their rating for lack of "etb" creatures.
    "flicker": r"exile (up to one )?(another |other )?target[^.]*(creature|permanent)s? you (control|own)[^.]*return|exile (it|them), then return(?! (it|him|her|them) to the battlefield transformed)|then return (it|that card|those cards) to the battlefield(?! transformed)",
    "equip_fetch": r"search your library for an equipment|equipment card from your hand onto the battlefield",
    "land_recursion": r"play lands? from your graveyard|land cards? from your graveyard",
    "landfall": r"landfall|whenever a land (you control )?enters|whenever one or more lands (you control )?enter",
    "land_sac": r"sacrifice (this land|a land|an? (land|nonbasic land))\b|destroy target (nonbasic )?land",
    "extra_land": r"play (an additional land|two additional lands|any number of lands|lands from your graveyard)|additional land on each of your turns",
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
    heavy: FrozenSet[str] = field(default_factory=frozenset)  # colours needed two or more times ({B}{B})
    # Colourless non-mana cards (Top, Skullclamp): the colours of the decks they get drafted into, from
    # their CubeCobra partners in this cube (share per colour), and how much evidence that rests on (0..1).
    home: Dict[str, float] = field(default_factory=dict)
    home_evidence: float = 0.0
    staple: bool = False                    # on the TAKE_ON_SIGHT list
    hybrid: FrozenSet[str] = field(default_factory=frozenset)  # colours of {U/R}-style hybrid symbols
    bomb: bool = False                      # colourless card rated with the cube's top 3% (The One Ring): goes in any deck

    @property
    def conspiracy(self) -> bool:
        """Conspiracy cards (Power Play, Advantageous Proclamation) only matter in Conspiracy drafts."""
        return "conspiracy" in self.types
    phyrexian: bool = False                 # Phyrexian mana in its cost (Dismember): castable in any deck
    key_of: FrozenSet[str] = field(default_factory=frozenset)   # deck types this card defines (decktypes.py)
    deck: Dict[str, float] = field(default_factory=dict)        # membership 0..1 per deck type

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


# Hand-checked fixes for cards the patterns above get wrong: front-face name -> (roles to add, roles to drop).
# Cheaper and safer than bending a pattern for one card; add a line whenever `?explain=1` shows a misfire.
ROLE_OVERRIDES: Dict[str, tuple] = {
    "stock up": ({"draw"}, set()),                       # "put two of them into your hand"
    "oust": ({"removal"}, set()),                        # puts the creature into its owner's library
    "fable of the mirror-breaker": (set(), {"flicker"}), # chapter III transforms itself, not a blink payoff
    "displacer kitten": (set(), {"removal"}),            # blinks our own permanents
    "strip mine": (set(), {"land_sac"}),                 # land destruction, not a lands-deck sac outlet
    "wasteland": (set(), {"land_sac"}),
    "balance": ({"sweeper"}, set()),
    "gaea's cradle": (set(), {"sweeper"}),
}

# Reminder text "(...)" explains a keyword; it isn't what the card does. Treasure's "(... Add one mana of any
# color.)" made Hullbreacher a mana dork and cycling's "(... Draw a card.)" made every triome card draw.
_REMINDER = re.compile(r"\([^)]*\)")


def _roles(card: dict, types: FrozenSet[str], text: str) -> FrozenSet[str]:
    text = _REMINDER.sub("", text)
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
    if cmc <= 1 and "draw" in roles and not ({"creature", "land"} & types):
        roles.add("cantrip")
    if "creature" in types and re.search(r"\bwhen [^.]{0,40}\benters\b(?! tapped)", text):
        roles.add("etb")                      # blink targets
    if "land" in types and re.search(r"sacrifice [^:]*: search your library for", text):
        roles.add("fetchland")
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
        if cmc <= 1 and "creature" not in types:
            roles.add("fast_mana")            # Moxen, Lotus, Petal, Sol Ring...
        if "creature" in types or re.search(r"search your library for (a|up to \w+) (basic )?lands?", text):
            roles.add("ramp")
    if "creature" in types and (card.get("cmc") or 0) <= 2:
        roles.add("cheap_threat")
    if "ritual" in roles and not ({"instant", "sorcery"} & types):
        roles.discard("ritual")               # Grim Monolith, Workshop, Ugin: mana, but not storm rituals
    add, drop = ROLE_OVERRIDES.get(front_name(card.get("name") or "").lower(), (set(), set()))
    return frozenset((roles | add) - drop)


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


USE_CUBE_META = False    # merge synergy from CubeCobra's deck export (cubemeta.py) into card partners. Off until the
                         # replay benchmark shows it helps (2026-10-14: +1.5% top-3 on one 139-pick draft, within noise)


# Cards a group takes on sight whatever their CubeCobra rating says (Timetwister sits below Orcish
# Bowmasters there): rated at least as high as the cube's top picks and the rest of its Power (build_card_index).
TAKE_ON_SIGHT = frozenset(n.lower() for n in (
    "Black Lotus", "Ancestral Recall", "Time Walk", "Timetwister",
    "Mox Pearl", "Mox Sapphire", "Mox Jet", "Mox Ruby", "Mox Emerald",
))

HOME_MIN_EVIDENCE = 1.0   # partner strength (in coloured cards) needed before a colourless card gets a home
HOME_FULL_EVIDENCE = 4.0  # ... and for the home to count fully


def _attach_homes(index: Dict[str, CardInfo]) -> None:
    """Colourless non-mana spells go in some decks, not all (Top in blue control, Skullclamp in creature
    decks): give each one a home from the colours of its CubeCobra partners in this cube."""
    for info in index.values():
        if not info.need and info.hybrid and not info.is_land:
            # Hybrid-only cost (Lutri {U/R}{U/R}, Lurrus {W/B}{W/B}): at home in decks of either colour.
            info.home = {c: 1.0 / len(info.hybrid) for c in sorted(info.hybrid)}
            info.home_evidence = 1.0
            continue
        if info.need or info.is_land or info.phyrexian or "mana" in info.roles or not info.partners:
            continue
        weights = {c: 0.0 for c in COLORS}
        for pid, strength in info.partners.items():
            p = index.get(pid)
            if p is None or p.is_land or not p.need:
                continue
            for col in p.need:
                weights[col] += strength / len(p.need)
        total = sum(weights.values())
        if total < HOME_MIN_EVIDENCE:
            continue
        info.home = {c: v / total for c, v in weights.items() if v}
        info.home_evidence = min(1.0, total / HOME_FULL_EVIDENCE)


def build_card_index(cube: Iterable[dict], stats: Optional[dict] = None, meta: Optional[dict] = None) -> Dict[str, CardInfo]:
    """Build CardInfo for every non-custom card in a cube (cube entries are draft card dicts).

    `stats` (optional, from draftbot.cardstats.draft_stats) supplies live CubeCobra Elo, which replaces
    the CSV value, and each card's package partners within the cube."""
    stats = stats or {}
    live_elo = stats.get("elo") or {}
    cards = [dict(c, elo=live_elo.get(c["id"]) or c.get("elo")) for c in cube if not c.get("is_custom")]
    partners = {k: dict(v) for k, v in (stats.get("partners") or {}).items()}
    if USE_CUBE_META:
        from .cubemeta import cube_partners
        for a, row in cube_partners([(c["id"], c.get("name", "")) for c in cards], meta).items():
            mine = partners.setdefault(a, {})
            for b, s in row.items():
                mine[b] = max(mine.get(b, 0.0), s)
    elos = [float(c["elo"]) for c in cards if c.get("elo")]
    mid = median(elos) if elos else 1200.0
    lo = sorted(elos)[int(len(elos) * 0.05)] if elos else mid - 200
    hi = sorted(elos)[int(len(elos) * 0.95) - 1] if elos else mid + 200
    span = max(hi - lo, 1.0)
    # Power is drafted first: TAKE_ON_SIGHT cards rank with the cube's top ~2%, and with the rest of the Power
    # in the cube (CubeCobra rates Timetwister far below the other Power Nine: 1810 against 2225+ in PowerLSV, which
    # let Orcish Bowmasters and Ragavan outrank it). The floor is the lower quartile of the Power cards' own Elo.
    staple_floor = sorted(elos)[int(len(elos) * 0.98) - 1] if elos else hi
    power_elos = sorted(float(c["elo"]) for c in cards if c.get("elo") and (c.get("name") or "").lower() in TAKE_ON_SIGHT)
    if len(power_elos) >= 4:
        staple_floor = max(staple_floor, power_elos[len(power_elos) // 4])

    index: Dict[str, CardInfo] = {}
    for c in cards:
        text = (c.get("oracle_text") or "").lower()
        types = _types(c.get("type_line", ""))
        elo = float(c.get("elo") or _estimate_elo(c, types, text, elos, mid))
        staple = (c.get("name") or "").lower() in TAKE_ON_SIGHT
        if staple:
            elo = max(elo, staple_floor)
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
            heavy=frozenset() if "land" in types else _heavy_colors(c.get("mana_cost", "")),
            staple=staple,
            phyrexian="/P}" in (c.get("mana_cost") or "").upper(),
            hybrid=frozenset() if "land" in types else _hybrid_colors(c.get("mana_cost", "")),
        )
    # Colourless cards rated with the cube's top 3% go in any deck: never narrow (unless they are a deck type's
    # key card, like Time Vault), never a "utility artifact" to cut back on.
    bomb_floor = sorted(elos)[int(len(elos) * 0.97) - 1] if len(elos) >= 30 else float("inf")
    for info in index.values():
        if not info.need and not info.hybrid and not info.is_land and info.elo >= bomb_floor:
            info.bomb = True
    _attach_homes(index)
    from .decktypes import attach_deck_types
    from .engine import register_colourless
    attach_deck_types(index)
    register_colourless(index)
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
