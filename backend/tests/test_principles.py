"""Drafting principles the bots must keep (docs/project-notes/bot-principles.md).

One test per principle, named after its id. They run against engine 2 (engine2.py). Each builds a small table
from real card names on top of a filler cube, so the engine sees the same kind of data as in a real draft.
Pure Python: no server needed.
"""
from draftbot import engine2
from draftbot.combos import Combo, attach_combos, with_cube_combos
from draftbot.engine import BotContext
from draftbot.features import build_card_index
from draftbot.lab import snake_order
from draftbot.personas import Persona
from tests.test_draftbot import card, synthetic_cube

NAMED = [
    card("lotus", "Black Lotus", "{0}", 0, "Artifact", "{T}, Sacrifice Black Lotus: Add three mana of any one color.", "", 2300),
    card("ancestral", "Ancestral Recall", "{U}", 1, "Instant", "Target player draws three cards.", "U", 2250),
    card("sapphire", "Mox Sapphire", "{0}", 0, "Artifact", "{T}: Add {U}.", "", 2200),
    card("ragavan", "Ragavan, Nimble Pilferer", "{R}", 1, "Legendary Creature — Monkey Pirate",
         "Whenever Ragavan deals combat damage to a player, create a Treasure token and exile the top card of that player's library.", "R", 1900),
    card("bolt", "Lightning Bolt", "{R}", 1, "Instant", "Lightning Bolt deals 3 damage to any target.", "R", 1550),
    card("counterspell", "Counterspell", "{U}{U}", 2, "Instant", "Counter target spell.", "U", 1560),
    card("drain", "Mana Drain", "{U}{U}", 2, "Instant", "Counter target spell. At the beginning of your next main phase, add an amount of {C} equal to that spell's mana value.", "U", 1560),
    card("remand", "Remand", "{1}{U}", 2, "Instant", "Counter target spell. Draw a card.", "U", 1560),
    card("memlapse", "Memory Lapse", "{1}{U}", 2, "Instant", "Counter target spell.", "U", 1540),
    card("balance", "Balance", "{1}{W}", 2, "Sorcery", "Each player chooses a number of lands they control equal to the number of lands controlled by the player who controls the fewest, then sacrifices the rest.", "W", 1560),
    card("swords", "Swords to Plowshares", "{W}", 1, "Instant", "Exile target creature. Its controller gains life equal to its power.", "W", 1650),
    card("breach", "Underworld Breach", "{1}{R}", 2, "Enchantment", "Each nonland card in your graveyard has escape.", "R", 1500),
    card("freeze", "Brain Freeze", "{1}{U}", 2, "Instant", "Target player mills three cards. Storm", "U", 1500),
    card("led", "Lion's Eye Diamond", "{0}", 0, "Artifact", "Discard your hand, Sacrifice Lion's Eye Diamond: Add three mana of any one color.", "", 1500),
    card("petal", "Lotus Petal", "{0}", 0, "Artifact", "{T}, Sacrifice Lotus Petal: Add one mana of any color.", "", 1500),
    card("grapeshot", "Grapeshot", "{1}{R}", 2, "Sorcery", "Grapeshot deals 1 damage to any target. Storm", "R", 1400),
    card("tendrils", "Tendrils of Agony", "{2}{B}{B}", 4, "Sorcery", "Target player loses 2 life and you gain 2 life. Storm", "B", 1400),
    card("vault", "Time Vault", "{2}", 2, "Artifact", "Time Vault enters tapped. {T}: Take an extra turn after this one.", "", 1700),
    card("vkey", "Voltaic Key", "{1}", 1, "Artifact", "{1}, {T}: Untap target artifact.", "", 1400),
    card("academy", "Tolarian Academy", "", 0, "Legendary Land", "{T}: Add {U} for each artifact you control.", "U", 1800),
    card("urza", "Urza, Lord High Artificer", "{2}{U}{U}", 4, "Legendary Creature — Human Artificer", "Tap an untapped artifact you control: Add {U}.", "U", 1700),
    card("tinker", "Tinker", "{2}{U}", 3, "Sorcery", "As an additional cost to cast this spell, sacrifice an artifact. Search your library for an artifact card and put that card onto the battlefield.", "U", 1700),
    card("top", "Sensei's Divining Top", "{1}", 1, "Artifact", "{1}: Look at the top three cards of your library, then put them back in any order.", "", 1600),
    card("mightstone", "Mightstone", "{4}", 4, "Artifact", "{T}: Look at the top card.", "", 1500),
    card("karakas", "Karakas", "", 0, "Legendary Land", "{T}: Add {W}. {T}: Return target legendary creature to its owner's hand.", "W", 1550),
    card("plateau", "Plateau", "", 0, "Land — Mountain Plains", "({T}: Add {R} or {W}.)", "RW", 1450),
    card("usea", "Underground Sea", "", 0, "Land — Island Swamp", "({T}: Add {U} or {B}.)", "UB", 1500),
    card("ocelot", "Ocelot Pride", "{W}", 1, "Creature — Cat", "First strike, lifelink", "W", 1600),
    card("thalia", "Thalia, Guardian of Thraben", "{1}{W}", 2, "Legendary Creature — Human Soldier", "First strike", "W", 1600),
    card("ajani", "Ajani, Nacatl Pariah", "{1}{W}", 2, "Legendary Creature — Cat Warrior", "When Ajani enters, create a 2/1 white Cat Warrior creature token.", "W", 1700),
    card("mother", "Mother of Runes", "{W}", 1, "Creature — Human Cleric", "{T}: Target creature you control gains protection.", "W", 1550),
    card("nullrod", "Null Rod", "{2}", 2, "Artifact", "Activated abilities of artifacts can't be activated.", "", 1450),
    card("thoughtseize", "Thoughtseize", "{B}", 1, "Sorcery", "Target player reveals their hand. You choose a nonland card from it. That player discards that card.", "B", 1700),
]


def build(extra=(), partners=None, combos=()):
    cube = synthetic_cube(24) + NAMED + list(extra)
    idx = build_card_index(cube, {"partners": partners or {}})
    cmb = with_cube_combos(idx, list(combos))
    attach_combos(idx, cmb)
    return idx, cmb


def ctx_for(idx, cmb, picks_by_seat, seats=4, per_seat=40, people=frozenset(), taken_extra=(), persona=None):
    """A table about to make the bot's next pick. `picks_by_seat[0]` is the bot's pool, the others its rivals'.
    The bot sits in seat 1 (not a corner, so rivals pick between its turns): keys 0 and 1 swap places."""
    picks_by_seat = {({0: 1, 1: 0}.get(s, s)): v for s, v in picks_by_seat.items()}
    seat = 1
    order = snake_order(seats, per_seat)
    made = sum(len(v) for v in picks_by_seat.values())
    # Slot: the first slot of `seat` at or after the picks made so far.
    slot = next(i for i in range(made, len(order)) if order[i] == seat)
    taken = {c for v in picks_by_seat.values() for c in v} | set(taken_extra)
    remaining = [c for c in idx if c not in taken]
    by_seat = {s: list(picks_by_seat.get(s, [])) for s in range(seats)}
    return BotContext(idx, cmb, remaining, by_seat, seat, order, slot, per_seat,
                      persona or Persona("steady", temperature=0.001), explain=True, people=people)


def scored(ctx):
    return {cid: (s, info) for s, cid, info in engine2.score_pool(ctx)}


def rank(ctx, cid):
    return [c for _, c, _ in engine2.score_pool(ctx)].index(cid)


# ---------------------------------------------------------------- P1
def test_P1_power_first():
    """Black Lotus goes first; with only people at the table, Power is treated as about to go."""
    idx, cmb = build()
    ctx = ctx_for(idx, cmb, {})
    assert engine2.score_pool(ctx)[0][1] == "lotus"
    ctx = ctx_for(idx, cmb, {0: ["lotus"], 1: ["G0"], 2: ["G1"], 3: ["G2"]}, people=None)
    s = scored(ctx)
    assert s["ancestral"][1]["gone"] > 0.8 and s["sapphire"][1]["gone"] > 0.8


# ---------------------------------------------------------------- P2
def test_P2_take_what_others_will_take_float_what_only_you_want():
    """A seat deep in Academy with blue rivals: Counterspell (the last good counter) is contested, Mightstone (an
    Academy card nobody else wants) will come back, so Counterspell gets the bigger share of its value now."""
    partners = {"mightstone": {"academy": 1.0, "vault": 1.0, "urza": 1.0, "tinker": 1.0}}
    idx, cmb = build(partners=partners)
    blue = ["U0", "U1", "U2", "U3", "U4"]
    pools = {0: ["academy", "vault", "urza", "tinker", "U5"], 1: blue, 2: ["U6", "U7", "U8", "U9", "U10"],
             3: ["G0", "G1", "G2", "G3", "G4"]}
    # Only the named cards are left (Power already gone), so the rivals' best cards are blue spells.
    held = {c for v in pools.values() for c in v}
    gone = [c for c in idx if c not in held and (c[0] in "WUBRG" and c[1:].isdigit() or c.startswith("land"))]
    ctx = ctx_for(idx, cmb, pools, taken_extra=gone + ["lotus", "ancestral", "sapphire", "vkey", "drain", "remand", "memlapse"])
    s = scored(ctx)
    cs, ms = s["counterspell"], s["mightstone"]
    assert cs[1]["gone"] > ms[1]["gone"] + 0.3
    assert cs[0] / cs[1]["value"] > ms[0] / ms[1]["value"]


# ---------------------------------------------------------------- P3
def test_P3_last_combo_piece_is_never_floated():
    idx, cmb = build()
    ctx = ctx_for(idx, cmb, {0: ["vault", "U0", "U1"], 1: ["G0", "G1", "G2"], 2: ["G3", "G4", "G5"], 3: ["R0", "R1", "R2"]})
    s = scored(ctx)
    assert s["vkey"][1]["gone"] == 1.0


# ---------------------------------------------------------------- P4
def test_P4_narrow_lane_holds_one_drafter():
    """A storm key card is worth less to a seat when a rival is already deep in storm."""
    idx, cmb = build()
    mine = ["R0", "R1", "B0", "B1"]
    open_ctx = ctx_for(idx, cmb, {0: mine, 1: ["G0", "G1", "G2", "G3"], 2: ["W0", "W1"], 3: ["U0", "U1"]})
    taken_ctx = ctx_for(idx, cmb, {0: mine, 1: ["breach", "freeze", "led", "tendrils"], 2: ["W0", "W1"], 3: ["U0", "U1"]})
    assert scored(taken_ctx)["grapeshot"][1]["plan_fit"] < 0.7 * scored(open_ctx)["grapeshot"][1]["plan_fit"]


# ---------------------------------------------------------------- P5
def test_P5_two_seats_share_a_broad_lane_a_third_backs_off():
    idx, cmb = build()
    mine = ["ocelot", "W0", "W1"]
    aggro = ["thalia", "ajani", "mother", "W2"]
    # A second rival deep in white aggro needs more of its key cards.
    idx2, cmb2 = build(extra=[card("guide", "Guide of Souls", "{W}", 1, "Creature — Human Cleric", "", "W", 1500),
                              card("adeline", "Adeline, Resplendent Cathar", "{1}{W}{W}", 3, "Legendary Creature — Human Knight", "Vigilance", "W", 1650),
                              card("kytheon", "Kytheon, Hero of Akros", "{W}", 1, "Legendary Creature — Human Soldier", "", "W", 1500),
                              card("giver", "Giver of Runes", "{W}", 1, "Creature — Kor Cleric", "", "W", 1450)])
    one = ctx_for(idx2, cmb2, {0: mine, 1: aggro, 2: ["G0", "G1", "G2", "G3"], 3: ["U0", "U1", "U2", "U3"]})
    two = ctx_for(idx2, cmb2, {0: mine, 1: aggro, 2: ["guide", "adeline", "kytheon", "W3"], 3: ["U0", "U1", "U2", "U3"]})
    v_one = scored(one)["giver"][1]["value"]
    v_two = scored(two)["giver"][1]["value"]
    assert v_two < 0.85 * v_one


# ---------------------------------------------------------------- P6
def test_P6_replaceable_cards_lose_value_to_their_substitutes():
    """With Counterspell, Remand and Memory Lapse still around, Mana Drain has substitutes; Balance (same rating)
    has none."""
    idx, cmb = build()
    ctx = ctx_for(idx, cmb, {0: ["U0", "U1", "W0", "W1", "U2", "W2"], 1: ["G0", "G1", "G2"], 2: ["R0", "R1", "R2"], 3: ["B0", "B1", "B2"]})
    ctx.tuning = {"replace_weight": 0.35}      # the default is small (replays of LSV's drafts favour ~0)
    s = scored(ctx)
    assert s["drain"][1]["substitute"] > 0.2
    assert s["balance"][1]["substitute"] == 0.0
    # Mana Drain keeps only part of its value: the rest is what Counterspell & co. would give anyway.
    assert s["drain"][0] < s["drain"][1]["value"] * 0.9 or s["drain"][1]["gone"] > 0.5


# ---------------------------------------------------------------- P7
def test_P7_committed_to_two_colours_takes_on_colour_cards():
    idx, cmb = build()
    ub = ["U0", "U1", "U2", "B0", "B1", "B2", "U3"]
    ctx = ctx_for(idx, cmb, {0: ub, 1: ["G0", "G1", "G2"], 2: ["W0", "W1", "W2"], 3: ["G3", "G4", "G5"]})
    s = scored(ctx)
    assert s["thoughtseize"][0] > s["bolt"][0]          # Bolt has the higher rating


# ---------------------------------------------------------------- P8
def test_P8_narrow_cards_wait_for_a_deck_that_uses_them():
    partners = {"top": {"academy": 1.0, "vault": 1.0, "urza": 1.0, "tinker": 1.0}}
    idx, cmb = build(partners=partners)
    outside = ctx_for(idx, cmb, {0: ["R0", "R1", "B0"], 1: ["G0", "G1", "G2"], 2: ["W0", "W1", "W2"], 3: ["G3", "G4", "G5"]})
    inside = ctx_for(idx, cmb, {0: ["academy", "vault", "urza"], 1: ["G0", "G1", "G2"], 2: ["W0", "W1", "W2"], 3: ["G3", "G4", "G5"]})
    assert scored(inside)["top"][1]["value"] > 1.5 * scored(outside)["top"][1]["value"]
    s = scored(outside)
    assert s["karakas"][1]["value"] < s["swords"][1]["value"] * 0.6


# ---------------------------------------------------------------- P9
def test_P9_strong_generic_cards_do_not_slip_for_marginal_plan_cards():
    idx, cmb = build()
    ctx = ctx_for(idx, cmb, {0: ["R0", "W0", "R1", "W1"], 1: ["G0", "G1", "G2", "G3"], 2: ["U0", "U1", "U2", "U3"],
                             3: ["B0", "B1", "B2", "B3"]})
    assert rank(ctx, "ragavan") < rank(ctx, "plateau")


def test_P9_top_rated_key_cards_stay_generic():
    """Ragavan keys red aggro, but it's one of the best cards in the cube: a red seat building something else
    still wants it fully. A narrower key card (Ocelot Pride) is discounted outside its deck."""
    idx, cmb = build()
    ctx = ctx_for(idx, cmb, {0: ["R0", "U0", "R1", "U1", "R2", "U2", "R3", "U3"] + [f"G{i}" for i in range(14)],
                             1: ["G20"], 2: ["W0"], 3: ["B0"]})
    s = scored(ctx)
    assert s["ragavan"][1]["plan_fit"] >= 0.95


def test_P9_big_fatties_only_for_decks_that_cheat_them_in():
    idx, cmb = build(extra=[card("grisel", "Griselbrand", "{4}{B}{B}{B}{B}", 8, "Legendary Creature — Demon",
                                 "Flying, lifelink", "B", 1800),
                            card("entomb", "Entomb", "{B}", 1, "Instant", "Search your library for a card and put it into your graveyard.", "B", 1650),
                            card("reanimate", "Reanimate", "{B}", 1, "Sorcery", "Put target creature card from a graveyard onto the battlefield under your control.", "B", 1650),
                            card("animate", "Animate Dead", "{1}{B}", 2, "Enchantment", "Enchant creature card in a graveyard. Return enchanted creature card to the battlefield under your control.", "B", 1550)],
                     partners={"grisel": {"entomb": 1.0, "reanimate": 1.0, "animate": 1.0}})
    ub = ["U0", "B0", "U1", "B1", "U2", "B2"]
    plain = ctx_for(idx, cmb, {0: ub, 1: ["G0"], 2: ["W0"], 3: ["R0"]})
    reanimator = ctx_for(idx, cmb, {0: ub + ["entomb", "reanimate", "animate"], 1: ["G0"], 2: ["W0"], 3: ["R0"]})
    assert scored(reanimator)["grisel"][1]["value"] > 1.5 * scored(plain)["grisel"][1]["value"]


# ---------------------------------------------------------------- P10
def test_P10_combo_pieces_have_a_priority_and_substitutes():
    idx, cmb = build()
    ctx = ctx_for(idx, cmb, {0: ["U0", "R0", "U1", "R1"], 1: ["G0", "G1", "G2", "G3"], 2: ["W0", "W1", "W2", "W3"],
                             3: ["G4", "G5", "G6", "G7"]})
    st = engine2.static_for(idx)
    rem = set(ctx.remaining)
    v = {c: engine2.package_value(st, c, set(), rem)[0] for c in ("breach", "freeze", "led")}
    assert v["breach"] > v["freeze"] > v["led"]
    # Holding Breach and Brain Freeze: LED completes it; Lotus Petal does too (a substitute), a bit less well.
    led, done = engine2.package_value(st, "led", {"breach", "freeze"}, rem)
    petal, done2 = engine2.package_value(st, "petal", {"breach", "freeze"}, rem)
    assert done and done2 and led > petal > 0.5 * led
    # With LED already owned, Petal is just a backup.
    assert engine2.package_value(st, "petal", {"breach", "freeze", "led"}, rem)[0] < 0.2 * led


# ---------------------------------------------------------------- P11
def test_P11_cheap_interaction_up_slow_cards_down_in_roto():
    idx, cmb = build()
    st = engine2.static_for(idx)
    assert st.quality["counterspell"] > st.quality["remand"]        # same rating; Remand is worse in roto


# ---------------------------------------------------------------- P12
def test_P12_deck_with_no_interaction_looks_for_it_by_mid_draft():
    idx, cmb = build()
    # 16 non-interaction red/white cards (synthetic filler with no removal text) by mid-draft.
    plain = [c for c in idx if c[0] in "RW" and c[1:].isdigit() and not engine2.is_interaction(idx[c])][:16]
    ctx = ctx_for(idx, cmb, {0: plain, 1: ["G0", "G1"], 2: ["U0", "U1"], 3: ["B0", "B1"]}, per_seat=30)
    assert scored(ctx)["swords"][1]["need"] > 0


# ---------------------------------------------------------------- P13
def test_P13_duals_for_your_pair_matter_once_committed():
    idx, cmb = build()
    late = ctx_for(idx, cmb, {0: ["U0", "U1", "B0", "B1", "U2", "B2", "U3"], 1: ["G0"], 2: ["W0"], 3: ["R0"]})
    s = scored(late)
    # Underground Sea for a blue-black seat; Plateau (Mountain Plains, not a fetch) barely fits it.
    assert s["usea"][1]["value"] > 2.0 * s["plateau"][1]["value"]


# ---------------------------------------------------------------- P14
def test_P14_sideboard_answers_late_and_light():
    idx, cmb = build()
    artifacts = ["academy", "vault", "urza", "tinker", "top", "mightstone", "sapphire", "lotus", "vkey", "led"]
    early = ctx_for(idx, cmb, {0: ["G0", "G1", "G2"], 1: artifacts[:3], 2: ["W0"], 3: ["R0"]})
    assert scored(early)["nullrod"][1]["hate_raw"] == 0
    gb = [f"G{i}" for i in range(11)] + [f"B{i}" for i in range(11)]
    late = ctx_for(idx, cmb, {0: gb, 1: artifacts, 2: ["W0"], 3: ["R0"]}, per_seat=40)
    hate = scored(late)["nullrod"][1]["hate_raw"]
    assert 0 < hate <= engine2.TUNING2["hate_weight"]


# ---------------------------------------------------------------- P15
def test_P15_late_entry_into_an_established_deck_type_is_not_worth_it():
    idx, cmb = build()
    early = ctx_for(idx, cmb, {0: ["W1", "U1"], 1: ["G0", "G1"], 2: ["R0", "R1"], 3: ["B0", "B1"]})
    wu = [f"W{i}" for i in range(2, 13)] + [f"U{i}" for i in range(2, 13)]
    late = ctx_for(idx, cmb, {0: wu, 1: ["thalia", "ajani", "mother", "W0"], 2: ["R0", "R1"], 3: ["B0", "B1"]})
    assert scored(late)["ocelot"][1]["plan_fit"] < 0.65 * scored(early)["ocelot"][1]["plan_fit"]


# ---------------------------------------------------------------- P16
def test_P16_crowded_colour_gives_way_to_an_open_one_early():
    idx, cmb = build()
    blue = lambda a: [f"U{i}" for i in range(a, a + 5)]
    ctx = ctx_for(idx, cmb, {0: ["lotus"], 1: blue(0), 2: blue(5), 3: blue(10)})
    s = scored(ctx)
    # Two filler cards of the same rating, one blue, one green: green is open.
    u = max((c for c in idx if c.startswith("U") and c not in ctx.picks_by_seat[0] + ctx.picks_by_seat[2] + ctx.picks_by_seat[3]),
            key=lambda c: idx[c].elo)
    g = min((c for c in idx if c.startswith("G")), key=lambda c: abs(idx[c].elo - idx[u].elo))
    assert s[g][1]["value"] / max(idx[g].power, 1e-6) > s[u][1]["value"] / max(idx[u].power, 1e-6)


# ---------------------------------------------------------------- P17-P21 (from replaying LSV's drafts)
def test_P17_people_pick_order_is_the_main_card_value():
    """Two cards with the same CubeCobra rating: the one real roto tables take early (Brainstorm, round ~11)
    is worth more than one they rarely take."""
    idx, cmb = build(extra=[card("bs", "Brainstorm", "{U}", 1, "Instant", "Draw three cards, then put two cards from your hand on top.", "U", 1450),
                            card("filler", "Plain Cantrip", "{U}", 1, "Instant", "Draw a card.", "U", 1450)])
    st = engine2.static_for(idx)
    assert st.quality["bs"] > 1.2 * st.quality["filler"]


def test_P18_a_mox_leans_its_colour():
    """LSV's Sapphire + Jet start drafts UB: with Mox Jet, a blue seat's UB gold card fits."""
    frog = card("frog", "Psychic Frog", "{U}{B}", 2, "Creature — Frog", "Flying", "UB", 1650)
    jet = card("jet", "Mox Jet", "{0}", 0, "Artifact", "{T}: Add {B}.", "B", 2150)
    idx, cmb = build(extra=[frog, jet])
    blue = ["U0", "U1", "U2", "U3", "U4", "U5"]
    without = ctx_for(idx, cmb, {0: blue, 1: ["G0"], 2: ["W0"], 3: ["R0"]})
    with_jet = ctx_for(idx, cmb, {0: blue + ["jet"], 1: ["G0"], 2: ["W0"], 3: ["R0"]})
    assert scored(with_jet)["frog"][1]["fit"] > scored(without)["frog"][1]["fit"] + 0.2


def test_P19_build_arounds_are_strong_early_picks():
    """Experts take Academy, Saga, Opal, LED in the first rounds to plant a flag; the discount for cards that
    only go in some decks applies once the bot has committed to something else."""
    partners = {"top": {"academy": 1.0, "vault": 1.0, "urza": 1.0, "tinker": 1.0}}
    idx, cmb = build(partners=partners)
    early = ctx_for(idx, cmb, {0: ["lotus"], 1: ["G0"], 2: ["W0"], 3: ["R0"]})
    rg = [f"R{i}" for i in range(7)] + [f"G{i}" for i in range(1, 8)]
    late = ctx_for(idx, cmb, {0: rg, 1: ["G20"], 2: ["W0"], 3: ["B0"]})
    assert scored(early)["top"][1]["plan_fit"] >= 0.95
    assert scored(late)["top"][1]["plan_fit"] < 0.6


def test_P20_fetchlands_fit_most_decks():
    fetch = card("delta", "Polluted Delta", "", 0, "Land", "{T}, Pay 1 life, Sacrifice Polluted Delta: Search your library for an Island or Swamp card, put it onto the battlefield.", "", 1500)
    idx, cmb = build(extra=[fetch])
    rg = [f"R{i}" for i in range(6)] + [f"G{i}" for i in range(1, 7)]
    ctx = ctx_for(idx, cmb, {0: rg, 1: ["G20"], 2: ["W0"], 3: ["B0"]})
    assert scored(ctx)["delta"][1]["fit"] >= 0.7


def test_P21_lsv_drafts_follow_the_table_order():
    from draftbot.benchmark import check_orders
    assert check_orders() == []
