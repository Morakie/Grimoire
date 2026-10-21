"""Unit tests for the draft bot engine (pure Python, no server needed)."""
import random

from draftbot.combos import Combo, attach_combos
from draftbot.engine import BotContext, choose_pick, float_risk, score_pool
from draftbot.features import build_card_index
from draftbot.personas import Persona
from draftbot.simulate import run_draft, summarise


def card(cid, name, cost="", cmc=0, type_line="Creature", text="", identity="", elo=1300):
    return {"id": cid, "name": name, "mana_cost": cost, "cmc": cmc, "type_line": type_line,
            "oracle_text": text, "color_identity": list(identity), "colors": list(identity), "elo": elo}


def synthetic_cube(n_per_colour=24, seed=1):
    rng = random.Random(seed)
    cube = []
    for col in "WUBRG":
        for i in range(n_per_colour):
            cmc = rng.randint(1, 5)
            cube.append(card(f"{col}{i}", f"{col} card {i}", "{%s}" % col + "{1}" * (cmc - 1), cmc,
                             rng.choice(["Creature — Test", "Instant", "Sorcery"]),
                             rng.choice(["", "Destroy target creature.", "Draw two cards."]), col, rng.randint(1150, 1650)))
    for i, pair in enumerate(["WU", "UB", "BR", "RG", "GW"]):
        cube.append(card(f"land{i}", f"{pair} dual", "", 0, "Land", f"Add {{{pair[0]}}} or {{{pair[1]}}}.", pair, 1400))
    return cube


def test_features_parse_colours_roles_and_skip_custom():
    cube = [
        card("a", "Dismember", "{1}{B/P}{B/P}", 3, "Instant", "Target creature gets -5/-5 until end of turn.", "B"),
        card("b", "Griselbrand", "{4}{B}{B}{B}{B}", 8, "Legendary Creature — Demon", "Flying, lifelink", "B"),
        card("c", "Reanimate", "{B}", 1, "Sorcery", "Put target creature card from a graveyard onto the battlefield under your control.", "B"),
        dict(card("d", "Homebrew", "{W}", 1), is_custom=True),
    ]
    idx = build_card_index(cube)
    assert "d" not in idx                                  # custom cards are ignored
    assert idx["a"].need == frozenset()                    # Phyrexian mana doesn't lock a colour
    assert "removal" in idx["a"].roles
    assert "fatty" in idx["b"].roles
    assert "reanimate" in idx["c"].roles


def _two_seat_ctx(cube, combos, my_picks, rival_picks, persona=None, explain=False):
    idx = build_card_index(cube)
    attach_combos(idx, combos)
    taken = set(my_picks) | set(rival_picks)
    remaining = [c for c in idx if c not in taken]
    order = [0, 1, 1, 0] * 20          # slot 0 is ours; the rival picks twice before our next turn
    slot = 0
    return BotContext(idx, combos, remaining, {0: list(my_picks), 1: list(rival_picks)}, 0, order, slot, 40,
                      persona or Persona("steady", temperature=0.001), explain=explain)


def test_uncontested_combo_piece_is_floated_but_contested_one_is_taken():
    base = synthetic_cube()
    breach = card("breach", "Breach", "{1}{R}", 2, "Enchantment", "", "R", 1500)
    led = card("led", "LED", "{0}", 0, "Artifact", "Add three mana of any one color.", "", 1350)
    freeze = card("freeze", "Freeze", "{1}{U}", 2, "Instant", "Storm", "U", 1350)
    cube = base + [breach, led, freeze]
    combos = [Combo(("breach", "led", "freeze"), 1.0)]

    # We own two pieces; the rival is drafting green and doesn't care about the third piece.
    ctx = _two_seat_ctx(cube, combos, ["breach", "led"], ["G0", "G1", "G2"])
    risk = float_risk(ctx, ["freeze"], set(ctx.remaining))["freeze"]
    assert risk < 0.5

    # Now the rival owns the other combo with the same piece, so it's contested.
    combos2 = combos + [Combo(("freeze", "G0"), 1.0)]
    ctx2 = _two_seat_ctx(cube, combos2, ["breach", "led"], ["G0", "G1", "G2"])
    risk2 = float_risk(ctx2, ["freeze"], set(ctx2.remaining))["freeze"]
    assert risk2 > risk


def test_two_pieces_make_the_third_a_priority():
    cube = synthetic_cube() + [
        card("vault", "Vault", "{2}", 2, "Artifact", "", "", 1450),
        card("key", "Key", "{1}", 1, "Artifact", "", "", 1250),
    ]
    combos = [Combo(("vault", "key"), 1.0)]
    no_pieces = {cid: s for s, cid, _ in score_pool(_two_seat_ctx(cube, combos, [], []))}
    with_vault = {cid: s for s, cid, _ in score_pool(_two_seat_ctx(cube, combos, ["vault"], []))}
    assert with_vault["key"] > no_pieces["key"] * 1.5


def test_full_bot_draft_is_coherent_and_beats_nothing_silly():
    cube = synthetic_cube(n_per_colour=40)
    seats, per_seat = 4, 30
    order = []
    while len(order) < seats * per_seat:
        order += list(range(seats)) + list(range(seats - 1, -1, -1))
    order = order[: seats * per_seat]
    result = run_draft(cube, [], order, seats, per_seat, seed=7)
    summary = summarise(result, [])
    assert all(len(s["picks"]) == per_seat for s in summary)
    assert all(s["on_lane_pct"] >= 60 for s in summary), [(s["lane"], s["on_lane_pct"]) for s in summary]


def test_choose_pick_is_deterministic_with_seed_and_low_temperature():
    cube = synthetic_cube()
    ctx = _two_seat_ctx(cube, [], [], [])
    a = choose_pick(ctx, random.Random(3))
    b = choose_pick(ctx, random.Random(3))
    assert a == b


def test_float_risk_values_are_sensible():
    cube = synthetic_cube() + [card("freeze", "Freeze", "{1}{G}", 2, "Instant", "", "G", 1350)]
    combos = [Combo(("freeze", "G0"), 1.0)]
    # Rival is green and holds G0, so Freeze completes their combo: they will very likely take it.
    contested = float_risk(_two_seat_ctx(cube, combos, [], ["G0", "G1"]), ["freeze"], None or set(build_card_index(cube)) - {"G0", "G1"})
    assert contested["freeze"] > 0.5


def test_splash_needs_real_value_and_values_its_fixing():
    from draftbot.engine import splash_colour, TUNING
    cube = synthetic_cube() + [
        card("bomb", "Splash Bomb", "{2}{G}", 3, "Creature — Test", "", "G", 1750),
        card("bomb2", "Splash Bomb 2", "{1}{G}", 2, "Instant", "", "G", 1700),
        card("dual", "UG dual", "", 0, "Land", "Add {U} or {G}.", "UG", 1400),
    ]
    idx = build_card_index(cube)
    ur = [f"U{i}" for i in range(8)] + [f"R{i}" for i in range(8)]
    # One middling green card is not a splash; two strong ones are.
    assert splash_colour([idx[c] for c in ur + ["G0"]], frozenset("UR"), TUNING.get) is None
    assert splash_colour([idx[c] for c in ur + ["bomb", "bomb2"]], frozenset("UR"), TUNING.get) == "G"
    ctx = _two_seat_ctx(cube, [], ur + ["bomb", "bomb2"], [])
    scores = {cid: s for s, cid, _ in score_pool(ctx)}
    assert scores["dual"] > scores["land1"]   # land1 is the UB dual: no splash help


def test_missing_elo_fast_mana_is_rated_highly():
    cube = synthetic_cube() + [dict(card("glee", "Gleemox", "{0}", 0, "Artifact", "{T}: Add one mana of any color.", ""), elo=None)]
    idx = build_card_index(cube)
    assert idx["glee"].power > 0.95


def test_deck_without_a_win_condition_looks_for_threats():
    cube = synthetic_cube() + [
        card("threat", "Big Threat", "{3}{U}", 4, "Creature — Test", "Flying", "U", 1400),
        card("spell", "Plain Spell", "{2}{U}", 3, "Instant", "Draw two cards.", "U", 1400),
    ]
    idx = build_card_index(cube)
    spells_only = [c for c in idx if c[0] in "UR" and not idx[c].is_creature][:24]
    creatures = [c for c in idx if c[0] in "UR" and idx[c].is_creature][:8]
    no_plan = {cid: s for s, cid, _ in score_pool(_two_seat_ctx(cube, [], spells_only, []))}
    has_plan = {cid: s for s, cid, _ in score_pool(_two_seat_ctx(cube, [], spells_only[:16] + creatures, []))}
    # Without a way to win, the threat clearly beats an equal-rated spell; with threats owned, the gap shrinks.
    assert no_plan["threat"] > no_plan["spell"] * 1.15
    assert (no_plan["threat"] / no_plan["spell"]) > (has_plan["threat"] / has_plan["spell"])


def test_committed_bot_ignores_off_colour_cards():
    cube = synthetic_cube()
    ctx = _two_seat_ctx(cube, [], [f"U{i}" for i in range(7)] + [f"R{i}" for i in range(7)], [])
    top5 = [cid for _, cid, _ in score_pool(ctx)[:5]]
    assert all(cid[0] in "UR" or cid.startswith("land") for cid in top5), top5


def test_cubecobra_card_page_is_parsed():
    from draftbot.cardstats import parse_card_page
    html = ('<script>window.reactProps = {"card": {"name": "Underworld Breach", "scryfall_id": "abc", "elo": 1585.6},'
            ' "draftedWithIDs": {"top": ["x", "y"]}, "synergisticIDs": {"top": ["y"]}};</script>')
    stats = parse_card_page(html)
    assert stats == {"name": "Underworld Breach", "cc_id": "abc", "elo": 1585.6, "drafted_with": ["x", "y"], "synergistic": ["y"]}
    assert parse_card_page("<html>404</html>") is None


def test_live_elo_and_package_partners_shape_picks():
    cube = synthetic_cube() + [
        card("breach", "Breach", "{1}{U}", 2, "Enchantment", "", "U", 1300),
        card("other", "Other", "{1}{U}", 2, "Enchantment", "", "U", 1300),
    ]
    stats = {"elo": {"breach": 1500}, "partners": {"breach": {"U0": 1.0, "U1": 1.0, "U2": 0.5},
                                                   "U0": {"breach": 1.0}, "U1": {"breach": 1.0}, "U2": {"breach": 0.5}}}
    idx = build_card_index(cube, stats)
    assert idx["breach"].elo == 1500 and idx["other"].elo == 1300
    ctx = _two_seat_ctx(cube, [], ["U0", "U1", "U2", "R0", "R1"], [])
    ctx.index = idx
    scores = {cid: s for s, cid, _ in score_pool(ctx)}
    plain = {cid: s for s, cid, _ in score_pool(_two_seat_ctx(cube, [], ["U0", "U1", "U2", "R0", "R1"], []))}
    assert scores["breach"] > plain["breach"] * 1.3


def test_cube_meta_synergy_becomes_partners_within_the_cube():
    from draftbot.cubemeta import cube_partners, synergy_strength
    meta = {"synergy": {"urza, lord high artificer": [("mox opal", 9.5), ("not in cube", 9.0)],
                        "thopter foundry": [("sword of the meek", 5.0)]}}
    cards = [("u", "Urza, Lord High Artificer"), ("m", "Mox Opal"), ("t", "Thopter Foundry"), ("s", "Sword of the Meek")]
    p = cube_partners(cards, meta)
    assert p["u"]["m"] == 1.0 and p["m"]["u"] == 1.0            # symmetric, capped at full strength
    assert p["t"]["s"] == synergy_strength(5.0) == 0.5
    assert synergy_strength(2.0) == 0.0
    assert "not in cube" not in str(p)
    assert cube_partners(cards, {"synergy": {}}) == {}


def test_plans_half_built_cheat_plan_wants_a_fatty_and_lands_pool_cuts_artifact_payoffs():
    from draftbot.engine import plan_fill, plan_strengths, plan_value, plan_conflict
    from draftbot.features import CardInfo
    def card(roles):
        return CardInfo(id="x", name="x", cmc=1, types=frozenset(), need=frozenset(), produces=frozenset(),
                        identity=frozenset(), elo=1500, power=0.5, roles=frozenset(roles))
    cheat_pool = {"cheat": 1}
    fill = plan_fill(cheat_pool); st = plan_strengths(fill)
    assert st["cheat"] == 0.5 and plan_value(card({"fatty"}), fill, st) > 0.4
    lands_pool = {"fetchland": 4, "land_sac": 3, "landfall": 1, "artifact": 3}
    st = plan_strengths(plan_fill(lands_pool))
    assert st["lands"] > st["artifacts"] and plan_conflict(card({"artifact_payoff"}), st) > 0.4
    assert plan_conflict(card({"land_recursion"}), st) == 0.0


def test_bot_report_ranks_real_picks_and_bot_picks_rank_first():
    from draftbot.report import build_report
    cube = synthetic_cube(n_per_colour=30)
    seats, per_seat = 4, 12
    order = []
    while len(order) < seats * per_seat:
        order += list(range(seats)) + list(range(seats - 1, -1, -1))
    order = order[: seats * per_seat]
    result = run_draft(cube, [], order, seats, per_seat, seed=3)
    index = result["index"]
    seq = {s: list(ids) for s, ids in result["picks"].items()}
    picks = [{"order": i, "seat_index": s, "card_id": seq[s].pop(0)} for i, s in enumerate(order)]
    rep = build_report(index, [], order, picks, per_seat, [{"index": s, "player_name": f"P{s}"} for s in range(seats)], skip_first=3)
    assert rep["overall"]["picks"] == seats * (per_seat - 3)
    # The bots drafted these picks themselves, so the engine should rank them near the top.
    assert rep["overall"]["median_rank"] <= 3, rep["overall"]
    d = rep["disagreements"][0]
    assert {"rating", "colour"} <= set(d["bot_top"][0]["parts"]) and len(d["bot_top"]) == 3
    assert set(rep["by_phase"]) == {"early", "middle", "late"}


def test_colourless_picks_do_not_commit_colours():
    """Moxen and rocks say nothing about colours: a bot that owns only those stays open."""
    cube = synthetic_cube() + [card(f"rock{i}", f"Rock {i}", "{1}", 1, "Artifact", "{T}: Add {C}.", "", 1600) for i in range(10)]
    rocks = [f"rock{i}" for i in range(9)]
    ctx = _two_seat_ctx(cube, [], rocks, [])
    fits = {cid: info["fit"] for _, cid, info in score_pool(ctx)}
    assert min(fits[f"{col}0"] for col in "WUBRG") > 0.3, fits
    # The same number of picks spent on two colours does commit.
    ctx = _two_seat_ctx(cube, [], [f"U{i}" for i in range(5)] + [f"R{i}" for i in range(4)], [])
    fits = {cid: info["fit"] for _, cid, info in score_pool(ctx)}
    assert fits["U10"] == 1.0 and fits["G10"] < 0.3


def test_combo_lines_do_not_stack():
    """A card in many half-built lines counts its best line in full and only a little of the rest."""
    from draftbot.engine import combo_value
    cube = synthetic_cube() + [card("kitten", "Kitten", "{3}{U}", 4, "Creature — Cat", "", "U", 1300)] + \
        [card(f"p{i}", f"Piece {i}", "{1}", 1, "Artifact", "", "", 1300) for i in range(8)]
    index = build_card_index(cube)
    one = [Combo(("kitten", "p0", "p1"), 1.0)]
    many = one + [Combo(("kitten", f"p{i}", f"p{i + 1}"), 1.0) for i in range(2, 8, 2)]
    for c in (one, many):
        attach_combos(index, c)
    owned = {"p0", "p2", "p4", "p6"}
    remaining = set(index) - owned
    attach_combos(index, one)
    v_one = combo_value(index["kitten"], owned, remaining, one, lambda _: 1.0)
    attach_combos(index, many)
    v_many = combo_value(index["kitten"], owned, remaining, many, lambda _: 1.0)
    assert v_many < v_one * 1.8, (v_one, v_many)
    long_line = [Combo(("kitten", "p0", "p2", "p3"), 1.0)]
    attach_combos(index, long_line)
    assert combo_value(index["kitten"], owned, remaining, long_line, lambda _: 1.0) == 0.0


def test_cube_combos_are_added_when_every_piece_is_in_the_cube():
    from draftbot.combos import with_cube_combos, _only_gains_life
    cube = synthetic_cube() + [card("oracle", "Thassa's Oracle", "{U}{U}", 2, "Creature — Merfolk", "", "U", 1500),
                               card("pact", "Tainted Pact", "{1}{B}", 2, "Instant", "", "B", 1360)]
    index = build_card_index(cube)
    combos = with_cube_combos(index, [])
    assert [tuple(sorted(c.pieces)) for c in combos] == [("oracle", "pact")]
    assert with_cube_combos(index, combos) == combos            # no duplicates
    assert _only_gains_life({"produces": [{"feature": {"name": "Infinite lifegain"}}]})
    assert not _only_gains_life({"produces": [{"feature": {"name": "Infinite lifegain"}}, {"feature": {"name": "Win the game"}}]})


def test_extra_mana_rocks_lose_value_without_an_artifact_plan():
    cube = synthetic_cube() + [card(f"rock{i}", f"Rock {i}", "{3}", 3, "Artifact", "{T}: Add {C}{C}.", "", 1600) for i in range(5)]
    # Compare the rating part: the float discount (only applied to the top 30) would blur the totals.
    few = {cid: i["rating"] for s, cid, i in score_pool(_two_seat_ctx(cube, [], ["rock0"], [], explain=True))}
    glut = {cid: i["rating"] for s, cid, i in score_pool(_two_seat_ctx(cube, [], ["rock0", "rock1", "rock2"], [], explain=True))}
    assert glut["rock4"] < few["rock4"] * 0.8, (few["rock4"], glut["rock4"])


def test_lands_alone_do_not_make_a_splash():
    """A dual or fetch taken for its other colour (a B/R fetch for a R/W deck) doesn't start a black splash."""
    from draftbot.engine import splash_colour, TUNING
    cube = synthetic_cube() + [card(f"rb{i}", f"RB fetch {i}", "", 0, "Land",
                                    "Pay 1 life, Sacrifice this land: Search your library for a Swamp or Mountain card.", "", 1600) for i in range(4)]
    index = build_card_index(cube)
    k = lambda key: TUNING[key]
    pool = [index[f"R{i}"] for i in range(4)] + [index[f"W{i}"] for i in range(4)] + [index[f"rb{i}"] for i in range(4)]
    assert splash_colour(pool, frozenset("WR"), k) is None


def test_splash_takes_single_pip_cards_only():
    """With a real black splash, {B} cards are castable but {B}{B} cards (Sheoldred) are not."""
    cube = synthetic_cube() + [card("bomb1", "Black bomb", "{2}{B}", 3, "Creature — Test", "", "B", 1800),
                               card("bomb2", "Black bomb 2", "{1}{B}", 2, "Instant", "Destroy target creature.", "B", 1800),
                               card("one", "One pip", "{3}{B}", 4, "Sorcery", "", "B", 1500),
                               card("two", "Two pips", "{2}{B}{B}", 4, "Creature — Test", "", "B", 1500)]
    mine = [f"U{i}" for i in range(6)] + [f"R{i}" for i in range(6)] + ["bomb1", "bomb2"]
    fits = {cid: info["fit"] for _, cid, info in score_pool(_two_seat_ctx(cube, [], mine, []))}
    assert fits["one"] > 0.5 and fits["two"] == 0.0, (fits["one"], fits["two"])


def test_bot_report_singleton_names_skip_other_printings():
    from draftbot.report import build_report
    cube = synthetic_cube() + [card("bolt1", "Bolt", "{R}", 1, "Instant", "Bolt deals 3 damage to any target.", "R", 1700),
                               card("bolt2", "Bolt", "{R}", 1, "Instant", "Bolt deals 3 damage to any target.", "R", 1700)]
    index = build_card_index(cube)
    order = [0, 1] * 10
    picks = [{"order": 0, "seat_index": 0, "card_id": "bolt1"}] + \
            [{"order": i, "seat_index": i % 2, "card_id": f"W{i}"} for i in range(1, 12)]
    seats = [{"index": 0, "player_name": "A"}, {"index": 1, "player_name": "B"}]
    rep = build_report(index, [], order, picks, 10, seats, skip_first=0, singleton_names=True)
    later = [r for r in rep["disagreements"] if r["order"] > 0]
    assert later and all(t["card"] != "bolt2" for r in later for t in r["bot_top"])


def test_sideboard_hate_only_late_and_only_against_a_real_target():
    """Null Rod is worth a look from the bot's own ~20th pick when a rival is building artifacts, never earlier,
    never without a target, and never against the bot's own artifact deck."""
    rods = [card("rod", "Null Rod", "{2}", 2, "Artifact", "Activated abilities of artifacts can't be activated.", "", 1300)]
    arts = [card(f"a{i}", f"Trinket {i}", "{1}", 1, "Artifact", "", "", 1300) for i in range(12)]
    cube = synthetic_cube(n_per_colour=40) + rods + arts
    mine = [f"U{i}" for i in range(12)] + [f"R{i}" for i in range(12)]
    rival_arts = [f"a{i}" for i in range(10)]

    def hate(mine_ids, rival_ids):
        rows = score_pool(_two_seat_ctx(cube, [], mine_ids, rival_ids, explain=True))
        return next(i["hate"] for _, c, i in rows if c == "rod")
    assert hate(mine[:10], rival_ids=rival_arts) == 0.0                      # too early
    assert hate(mine, rival_ids=rival_arts) > 0.1                          # own 25th pick, rival on artifacts
    assert hate(mine, rival_ids=[f"W{i}" for i in range(10)]) == 0.0       # nobody to answer
    assert hate(mine[:14] + rival_arts, rival_ids=rival_arts) == 0.0        # our own artifact deck


def test_uncommitted_rivals_still_want_top_cards_of_any_colour():
    """Rivals with a couple of blue picks aren't blue drafters yet: a top red card won't come back."""
    cube = synthetic_cube() + [card("rag", "Ragavan", "{R}", 1, "Creature — Monkey", "", "R", 1840)] + [
        card(f"ub{i}", f"Blue bomb {i}", "{1}{U}", 2, "Instant", "", "U", 1800) for i in range(3)]
    ctx = _two_seat_ctx(cube, [], [], ["U0", "U1"])
    remaining = set(build_card_index(cube)) - {"U0", "U1"}
    assert float_risk(ctx, ["rag"], remaining)["rag"] > 0.5


def test_universal_staples_do_not_make_partners():
    """Owning Sol Ring and a Mox says nothing about packages, however often they're drafted together."""
    from draftbot.engine import partner_sources, partner_value
    cube = synthetic_cube() + [
        card("sol", "Sol Ring", "{1}", 1, "Artifact", "{T}: Add {C}{C}.", "", 2260),
        card("strip", "Strip Mine", "", 0, "Land", "{T}: Add {C}. {T}, Sacrifice Strip Mine: Destroy target land.", "", 1800),
        card("top", "Top", "{1}", 1, "Artifact", "{1}: Look at the top three cards of your library.", "", 1550),
    ]
    idx = build_card_index(cube, {"partners": {"top": {"sol": 1.0, "strip": 1.0, "U0": 1.0}}})
    sources = partner_sources(idx, {"sol", "strip", "U0"})
    assert sources == {"U0"}
    assert partner_value(idx["top"], sources, lambda c: 1.0) < partner_value(idx["top"], {"sol", "strip", "U0"}, lambda c: 1.0)


def test_colourless_cards_with_a_home_fit_its_colours_only():
    """Top drafted with blue cards fits blue decks; it no longer counts as fitting a red-green deck."""
    from draftbot.engine import _lane_fit
    cube = synthetic_cube() + [card("top", "Top", "{1}", 1, "Artifact", "{1}: Look at the top three cards of your library.", "", 1550)]
    idx = build_card_index(cube, {"partners": {"top": {f"U{i}": 1.0 for i in range(5)}}})
    assert idx["top"].home == {"U": 1.0}
    assert _lane_fit(idx["top"], frozenset("UB")) == 1.0
    assert _lane_fit(idx["top"], frozenset("RG")) <= 0.4


def test_one_colour_utility_land_fits_decks_of_its_colour():
    from draftbot.engine import _lane_fit
    idx = build_card_index([card("kar", "Karakas", "", 0, "Legendary Land", "{T}: Add {W}.", "W", 1790)])
    assert _lane_fit(idx["kar"], frozenset("WR")) == 1.0
    assert _lane_fit(idx["kar"], frozenset("UB")) == 0.0


def test_power_nine_rated_with_the_top_picks():
    cube = synthetic_cube() + [card("tw", "Timetwister", "{2}{U}", 3, "Sorcery", "Each player shuffles their hand and graveyard into their library, then draws seven cards.", "U", 1300)]
    idx = build_card_index(cube)
    assert idx["tw"].power >= 0.99


def test_last_combo_piece_is_not_floated():
    """Holding Time Vault, the bot takes the Key now instead of hoping nobody else does."""
    cube = synthetic_cube() + [
        card("vault", "Vault", "{2}", 2, "Artifact", "", "", 2000),
        card("key", "Key", "{1}", 1, "Artifact", "", "", 1450),
    ]
    combos = [Combo(("vault", "key"), 1.0)]
    rows = {cid: i for _, cid, i in score_pool(_two_seat_ctx(cube, combos, ["vault"], [], explain=True))}
    assert rows["key"]["risk"] == 1.0 and rows["key"]["contested"] == 1.0


def _artifact_cube():
    """Synthetic cube with an artifact deck type: two key cards and a Bauble drafted with them."""
    return synthetic_cube() + [
        card("acad", "Tolarian Academy", "", 0, "Legendary Land", "Add {U} for each artifact you control.", "U", 1840),
        card("urza", "Urza, Lord High Artificer", "{2}{U}{U}", 4, "Legendary Creature — Human Artificer",
             "Tap an untapped artifact you control: Add {U}.", "U", 1660),
        card("saga", "Urza's Saga", "", 0, "Enchantment Land — Urza's Saga", "", "", 1720),
        card("bauble", "Mishra's Bauble", "{0}", 0, "Artifact", "Draw a card at the beginning of the next turn's upkeep.", "", 1540),
    ]


def _artifact_stats():
    # The Bauble's partners are mostly the artifact deck's key cards (like CubeCobra's data for it).
    return {"partners": {"bauble": {"acad": 1.0, "urza": 1.0, "saga": 1.0, "W0": 0.5, "R0": 0.5}}}


def test_narrow_artifacts_wait_for_an_artifact_deck():
    """Mishra's Bauble is worth little to a bot outside artifacts, and full value inside them."""
    from draftbot.engine import TUNING
    cube = _artifact_cube()
    idx = build_card_index(cube, _artifact_stats())
    assert idx["bauble"].deck.get("tolarian") == 1.0 and "tolarian" in idx["urza"].key_of

    def bauble(mine):
        ctx = _two_seat_ctx(cube, [], mine, [], explain=True)
        ctx.index = idx
        return next(i for _, c, i in score_pool(ctx) if c == "bauble")
    outside = bauble(["W0", "W1", "R0"])
    inside = bauble(["acad", "urza", "U0"])
    assert outside["deck"] <= TUNING["narrow_floor"] + 0.05
    assert "deck" not in inside or inside["deck"] > 0.9


def test_crowded_deck_type_is_left_to_the_seats_in_it():
    """Two seats already in artifacts: a third bot that isn't leading values the deck type's cards less."""
    from draftbot.engine import deck_outlook
    cube = _artifact_cube()
    idx = build_card_index(cube, _artifact_stats())
    ctx = _two_seat_ctx(cube, [], [], [])
    ctx.index = idx
    from draftbot.decktypes import DECK_TYPES
    rival = {t: 0.0 for t in DECK_TYPES}
    mine = dict(rival, tolarian=0.5)
    two = [dict(rival, tolarian=1.0), dict(rival, tolarian=0.9)]
    alone_eff, alone_open = deck_outlook(ctx, mine, [dict(rival, tolarian=1.0)])
    crowd_eff, crowd_open = deck_outlook(ctx, mine, two)
    assert alone_eff["tolarian"] == 0.5 and alone_open["tolarian"] == 0.25    # one seat, fully in: barely open
    _, shallow_open = deck_outlook(ctx, mine, [dict(rival, tolarian=0.5)])
    assert shallow_open["tolarian"] == 0.5                                     # one seat, just in: half open
    assert crowd_eff["tolarian"] < 0.5 and crowd_open["tolarian"] == 0.0      # shallow: pivot
    deep_eff, _ = deck_outlook(ctx, dict(rival, tolarian=1.0), two)
    assert deep_eff["tolarian"] == 1.0                                          # as deep as anyone: fight
    # A similar deck type isn't crowded by them: an artifact-synergy deck still fights for its own cards.
    other_eff, other_open = deck_outlook(ctx, dict(rival, artifacts=0.5), two)
    assert other_eff["artifacts"] == 0.5 and other_open["artifacts"] == 1.0


def test_only_peoples_fetch_picks_start_a_land_run():
    from draftbot.engine import land_run
    cube = synthetic_cube() + [card(f"f{i}", f"Fetch {i}", "", 0, "Land",
                                    "Search your library for a Plains or Island card.", "", 1700) for i in range(4)]
    idx = build_card_index(cube)
    order = [0, 1, 1, 0] * 20
    picks = {0: ["W0", "f0"], 1: ["f1", "f2"]}
    ctx = BotContext(idx, [], [c for c in idx if c not in {"W0", "f0", "f1", "f2"}], picks, 0, order, 4, 40)
    assert land_run(ctx) > 0.5                 # everyone counts as a person by default
    ctx.people = frozenset({0})
    assert land_run(ctx) == 0.0                # the bot in seat 1 taking fetches doesn't start a run


def test_phyrexian_mana_cards_fit_every_deck():
    from draftbot.decktypes import is_narrow, is_universal
    cube = synthetic_cube() + [card("dism", "Dismember", "{1}{B/P}{B/P}", 3, "Instant",
                                    "Target creature gets -5/-5 until end of turn.", "B", 1650)]
    idx = build_card_index(cube, {"partners": {"dism": {f"B{i}": 1.0 for i in range(6)}}})
    c = idx["dism"]
    assert not c.home and not is_narrow(c, is_universal(c), c.staple)


def test_open_picks_lean_but_do_not_commit():
    """Mana Vault leans towards a Tolarian deck (half a key); a Mox barely moves a pool."""
    from draftbot.decktypes import deck_strength
    cube = _artifact_cube() + [card("vault", "Mana Vault", "{1}", 1, "Artifact", "{T}: Add {C}{C}{C}.", "", 1890),
                               card("mox", "Mox Pearl", "{0}", 0, "Artifact", "{T}: Add {W}.", "", 2240)]
    stats = _artifact_stats()
    stats["partners"]["vault"] = {"acad": 1.0, "urza": 1.0, "W1": 0.5}
    idx = build_card_index(cube, stats)
    assert deck_strength([idx["vault"]])["tolarian"] == 0.25
    assert deck_strength([idx["mox"]])["tolarian"] == 0.0


def test_transforming_sagas_are_not_blink_payoffs():
    """Fable's chapter III exiles and returns itself transformed: not a blink card (it was losing 70% of its
    rating for lack of blink creatures). Real blink still is."""
    cube = [
        card("fable", "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki", "{2}{R}", 3,
             "Enchantment — Saga // Enchantment Creature — Goblin Shaman",
             "I — Create a 2/2 red Goblin Shaman creature token.\nIII — Exile this Saga, then return it to the "
             "battlefield transformed under your control.", "R", 1660),
        card("ajani", "Ajani, Nacatl Pariah // Ajani, Nacatl Avenger", "{1}{W}", 2, "Legendary Creature — Cat Warrior",
             "Whenever one or more other Cats you control die, you may exile Ajani, then return him to the battlefield "
             "transformed under his owner's control.", "RW", 1680),
        card("ephem", "Ephemerate", "{W}", 1, "Instant",
             "Exile target creature you control, then return it to the battlefield under its owner's control.", "W", 1600),
    ]
    idx = build_card_index(cube)
    assert "flicker" not in idx["fable"].roles and "flicker" not in idx["ajani"].roles
    assert "flicker" in idx["ephem"].roles
    assert "white_aggro" in idx["ajani"].key_of


def _aggro_cube():
    return synthetic_cube() + [
        card("ajani", "Ajani, Nacatl Pariah // Ajani, Nacatl Avenger", "{1}{W}", 2, "Legendary Creature — Cat Warrior",
             "When Ajani enters, create a 2/1 white Cat Warrior creature token.", "RW", 1700),
        card("ocelot", "Ocelot Pride", "{W}", 1, "Creature — Cat Cleric", "First strike, lifelink", "W", 1700),
        card("thalia", "Thalia, Guardian of Thraben", "{1}{W}", 2, "Legendary Creature — Human Soldier",
             "First strike", "W", 1650),
        card("mom", "Mother of Runes", "{W}", 1, "Creature — Human Cleric", "", "W", 1640),
    ]


def test_late_entry_into_an_established_aggro_deck_is_not_worth_it():
    """A seat with no aggro cards shouldn't pick up Ajani just for its rating once another seat is deep in
    aggro, least of all late in the draft."""
    cube = _aggro_cube()
    idx = build_card_index(cube)

    def ajani_deck(mine, rival, slot_pick):
        ctx = _two_seat_ctx(cube, [], mine, rival, explain=True)
        ctx.index = idx
        ctx.picks_per_seat = 20
        rows = {c: i for _, c, i in score_pool(ctx)}
        return rows["ajani"].get("deck", 1.0)
    early_open = ajani_deck(["U0"], [], 1)
    early_taken = ajani_deck(["U0"], ["ocelot", "thalia", "mom"], 1)
    late_taken = ajani_deck(["U0", "U1", "U2", "U3", "U4", "U5", "U6", "U7", "U8", "U9"], ["ocelot", "thalia", "mom"], 1)
    assert early_open > early_taken > late_taken
    assert late_taken <= 0.56                       # down to the key-card floor


def test_committed_bot_values_synergy_over_raw_rating():
    """Once committed, a card that goes with the deck beats a slightly higher-rated card that doesn't."""
    cube = synthetic_cube() + [
        card("syn", "Synergy card", "{1}{U}", 2, "Creature — Test", "", "U", 1560),
        card("big", "Generic good card", "{1}{U}", 2, "Creature — Test", "", "U", 1760),
    ]
    stats = {"partners": {"syn": {"U0": 1.0, "U1": 1.0, "U2": 1.0, "U3": 1.0}}}
    idx = build_card_index(cube, stats)
    mine = ["U0", "U1", "U2", "U3", "U4", "U5", "B0", "B1", "B2", "B3"]
    ctx = _two_seat_ctx(cube, [], mine, [], explain=True)
    ctx.index = idx
    ctx.order = [0] + [1] * 79          # our last pick: nothing floats, so this is rating vs synergy alone
    order = [c for _, c, _ in score_pool(ctx)]
    assert order.index("syn") < order.index("big")


def test_shared_deck_type_puts_its_cards_first():
    """A bot fighting a rival for a deck type gets a bonus on that deck type's key cards."""
    cube = _aggro_cube() + [card("adeline", "Adeline, Resplendent Cathar", "{1}{W}{W}", 3, "Legendary Creature",
                                 "Vigilance", "W", 1650)]
    idx = build_card_index(cube)

    def plan_part(rival):
        ctx = _two_seat_ctx(cube, [], ["ocelot", "thalia"], rival, explain=True)
        ctx.index = idx
        return {c: i for _, c, i in score_pool(ctx)}["adeline"]["plan"]
    assert plan_part(["mom", "ajani"]) > plan_part(["U0", "U1"]) + 0.1


def test_hate_cards_start_low_and_grow():
    """Sideboard answers count only a little at the bot's 20th pick and grow later."""
    from draftbot.engine import TUNING
    cube = synthetic_cube() + [
        card("rod", "Null Rod", "{2}", 2, "Artifact", "Activated abilities of artifacts can't be activated.", "", 1500),
    ] + [card(f"a{i}", f"Rock {i}", "{1}", 1, "Artifact", "{T}: Add {C}.", "", 1400) for i in range(12)]
    idx = build_card_index(cube)
    rival = [f"a{i}" for i in range(12)]
    mine_ids = [c for c in idx if c.startswith("U") or c.startswith("B")]

    def hate(n):
        ctx = _two_seat_ctx(cube, [], mine_ids[:n], rival, explain=True)
        ctx.index = idx
        return {c: i for _, c, i in score_pool(ctx)}["rod"]["hate"]
    early, later = hate(19), hate(30)
    assert early < 0.05 and later > 2 * early and later <= TUNING["hate_weight"]


def test_late_lands_do_not_outscore_real_cards_once_fixed():
    """Basics come from outside the draft: with a couple of duals owned, a five-colour land isn't the pick."""
    cube = synthetic_cube() + [
        card("gem", "Gemstone Mine", "", 0, "Land", "{T}: Add one mana of any color.", "", 1300),
    ]
    idx = build_card_index(cube)
    mine = [f"U{i}" for i in range(14)] + [f"W{i}" for i in range(14)] + ["land0", "land4"]
    ctx = _two_seat_ctx(cube, [], mine, [], explain=True)
    ctx.index = idx
    rows = {c: i for _, c, i in score_pool(ctx)}
    assert rows["gem"]["other"] <= 0.15


def test_reanimation_needs_something_to_reanimate():
    cube = synthetic_cube() + [
        card("rean", "Reanimate", "{B}", 1, "Sorcery",
             "Put target creature card from a graveyard onto the battlefield under your control.", "B", 1700),
        card("fat", "Griselbrand", "{4}{B}{B}{B}{B}", 8, "Legendary Creature — Demon", "Flying, lifelink", "B", 1500),
    ]
    idx = build_card_index(cube)

    def rating(mine, rival):
        ctx = _two_seat_ctx(cube, [], mine, rival, explain=True)
        ctx.index = idx
        return {c: i for _, c, i in score_pool(ctx)}["rean"]["rating"]
    base = [f"B{i}" for i in range(7)]
    with_target = rating(base + ["fat"], [])
    without = rating(base, ["fat"])          # the only fatty is gone
    assert without < 0.6 * with_target


def test_duals_do_not_win_on_drafted_with_partners():
    """A dual is drafted with every card of its colours: that says "these colours", not synergy."""
    cube = synthetic_cube() + [
        card("dual", "Hallowed Fountain", "", 0, "Land — Plains Island", "({T}: Add {W} or {U}.)", "WU", 1500),
        card("spell", "Real card", "{1}{U}", 2, "Instant", "Counter target spell.", "U", 1500),
    ]
    stats = {"partners": {"dual": {f"U{i}": 1.0 for i in range(6)}, "spell": {f"U{i}": 1.0 for i in range(6)}}}
    idx = build_card_index(cube, stats)
    ctx = _two_seat_ctx(cube, [], [f"U{i}" for i in range(6)] + [f"W{i}" for i in range(4)], [], explain=True)
    ctx.index = idx
    rows = {c: i for _, c, i in score_pool(ctx)}
    assert rows["dual"]["partners"] < 0.5 * rows["spell"]["partners"]


def test_role_tags_skip_reminder_text_and_known_misfires():
    cube = [
        card("hull", "Hullbreacher", "{2}{U}", 3, "Creature — Merfolk Rogue",
             "Flash\nIf an opponent would draw a card except the first one they draw in each of their draw steps, "
             "instead you create a Treasure token. (It's an artifact with \"{T}, Sacrifice this token: Add one mana of any color.\")", "U"),
        card("thop", "Thopter Foundry", "{W/B}{U}", 2, "Artifact",
             "{1}, Sacrifice a nontoken artifact: Create a 1/1 blue Thopter artifact creature token with flying. You gain 1 life.", "WUB"),
        card("cradle", "Gaea's Cradle", "", 0, "Legendary Land", "{T}: Add {G} for each creature you control.", "G"),
        card("mono", "Grim Monolith", "{2}", 2, "Artifact",
             "Grim Monolith doesn't untap during your untap step.\n{T}: Add {C}{C}{C}.\n{4}: Untap Grim Monolith."),
        card("rit", "Dark Ritual", "{B}", 1, "Instant", "Add {B}{B}{B}.", "B"),
        card("sword", "Sword of the Meek", "{2}", 2, "Artifact — Equipment",
             "Whenever a 1/1 creature you control enters, you may return Sword of the Meek from your graveyard to the "
             "battlefield, then attach it to that creature."),
        card("snuff", "Snuff Out", "{3}{B}", 4, "Instant", "Destroy target nonblack creature. It can't be regenerated.", "B"),
        card("kitten", "Displacer Kitten", "{3}{U}", 4, "Creature — Cat Nightmare",
             "Whenever you cast a noncreature spell, exile up to one target nonland permanent you control, then return "
             "that card to the battlefield under its owner's control.", "U"),
        card("stock", "Stock Up", "{2}{U}", 3, "Sorcery",
             "Look at the top five cards of your library. Put two of them into your hand and the rest on the bottom.", "U"),
        card("goryo", "Goryo's Vengeance", "{1}{R}", 2, "Instant",
             "Return target legendary creature card from your graveyard to the battlefield. It gains haste.", "R"),
    ]
    idx = build_card_index(cube)
    assert "mana" not in idx["hull"].roles                     # Treasure reminder text isn't the card's own mana
    assert "removal" not in idx["thop"].roles                  # a sacrifice cost isn't an edict
    assert "sweeper" not in idx["cradle"].roles
    assert "ritual" not in idx["mono"].roles and "ritual" in idx["rit"].roles
    assert "reanimate" not in idx["sword"].roles and "reanimate" in idx["goryo"].roles
    assert "removal" in idx["snuff"].roles
    assert "removal" not in idx["kitten"].roles and "flicker" in idx["kitten"].roles
    assert "draw" in idx["stock"].roles                        # ROLE_OVERRIDES


def test_role_saturation_and_utility_artifacts():
    from draftbot.engine import saturation_factor
    sweeper = build_card_index([card("w", "Wrath", "{2}{W}{W}", 4, "Sorcery", "Destroy all creatures.", "W")])["w"]
    assert saturation_factor(sweeper, {"sweeper": 2}, 0.5) == 1.0       # room for a third
    assert saturation_factor(sweeper, {"sweeper": 3}, 0.5) == 0.75      # one past the limit
    assert saturation_factor(sweeper, {"sweeper": 5}, 0.5) == 0.5
    # Colourless utility artifacts: past two, a deck without an artifact plan wants another one less.
    cube = synthetic_cube() + [card(f"ut{i}", f"Trinket {i}", "{1}", 1, "Artifact",
                                    "{1}, {T}: Look at the top card of your library.", "", 1600) for i in range(4)]
    few = {cid: i["rating"] for s, cid, i in score_pool(_two_seat_ctx(cube, [], ["ut0"], [], explain=True))}
    glut = {cid: i["rating"] for s, cid, i in score_pool(_two_seat_ctx(cube, [], ["ut0", "ut1"], [], explain=True))}
    assert glut["ut3"] < few["ut3"] * 0.7, (few["ut3"], glut["ut3"])


def test_cheat_spells_and_big_fatties_need_each_other():
    cube = synthetic_cube() + [
        card("sneak", "Sneak Attack", "{3}{R}", 4, "Enchantment",
             "{R}: You may put a creature card from your hand onto the battlefield. It gains haste.", "R", 1700),
        card("rean", "Reanimate", "{B}", 1, "Sorcery",
             "Put target creature card from a graveyard onto the battlefield under your control.", "B", 1700),
        card("fat", "Griselbrand", "{4}{B}{B}{B}{B}", 8, "Legendary Creature — Demon", "Flying, lifelink", "B", 1700),
        card("fat2", "Big Wurm", "{6}{B}", 7, "Creature — Wurm", "Trample", "B", 1500),
    ]
    idx = build_card_index(cube)

    def part(mine, rival, cid):
        ctx = _two_seat_ctx(cube, [], mine, rival, explain=True)
        ctx.index = idx
        return {c: i for _, c, i in score_pool(ctx)}[cid]["rating"]
    base = [f"B{i}" for i in range(4)] + [f"R{i}" for i in range(3)]
    # A cheat spell with no fatty to cheat in is worth much less (as reanimation spells already were).
    assert part(base, ["fat", "fat2"], "sneak") < 0.6 * part(base + ["fat2"], ["fat"], "sneak")
    # A fatty nobody can cast: worth much less without a reanimation or cheat spell.
    assert part(base, ["rean", "sneak"], "fat") < 0.6 * part(base + ["rean"], ["sneak"], "fat")


def test_bot_lab_rebuilds_a_pick_and_tries_other_weights():
    from draftbot.lab import clean_tuning, lab_view, pick_slot
    cube = synthetic_cube()
    idx = build_card_index(cube)
    order = [0, 1, 1, 0] * 6
    ids = sorted(idx, key=lambda c: -idx[c].elo)
    picks = [{"order": i, "seat_index": s, "card_id": ids[i]} for i, s in enumerate(order[:9])]
    # Only known weights, clamped to the knob's range; unchanged values dropped.
    assert clean_tuning({"partner_weight": 9, "nope": 1, "rock_cut": 0.35}) == {"partner_weight": 1.5}
    assert pick_slot(order, 9, 0, 2, None) == 3           # seat 0's 2nd pick
    assert pick_slot(order, 9, 1, None, None) == 9        # seat 1's next pick (slot 9 not made yet)
    v = lab_view(idx, [], order, picks, 12, 3, {"commit_rating_cut": 1.0}, n=5)
    assert v["seat"] == 0 and v["pick_no"] == 2 and v["took"]["card"] == ids[3]
    assert ids[3] in {r["card"] for r in v["rows"]} or v["took"]["rank"] > 5
    assert all(r["base_rank"] for r in v["rows"]) and "rating" in v["rows"][0]["parts"]
    assert ids[0] not in {r["card"] for r in v["rows"]}   # taken before this pick
    nxt = lab_view(idx, [], order, picks, 12, 9)
    assert nxt["next_pick"] and nxt["took"] is None


def test_bot_brain_dossier_summary_and_simulation():
    from draftbot.lab import card_dossier, lab_view, simulate, source_summary
    cube = synthetic_cube() + [card("acad", "Tolarian Academy", "", 0, "Legendary Land",
                                    "{T}: Add {U} for each artifact you control.", "U", 1800)]
    stats = {"partners": {"acad": {"U1": 1.0, "U2": 0.5}, "U1": {"acad": 1.0}, "U2": {"acad": 0.5}}}
    idx = build_card_index(cube, stats)
    d = card_dossier(idx, [], "acad")
    assert d["key_of"] == ["tolarian"] and d["narrow"]
    assert [p["id"] for p in d["partners"]] == ["U1", "U2"] and d["partner_count"] == {"synergy": 1, "all": 2}
    assert d["graph"]["nodes"][0]["id"] == "acad" and len(d["graph"]["edges"]) == 2
    s = source_summary(idx, [])
    assert s["cards"] == len(idx) and any(x["type"] == "tolarian" and x["key_count"] == 1 for x in s["decks"])
    sim = simulate(idx, [], 4, 10, seed=2)
    ids = [p["card_id"] for p in sim["picks"]]
    assert len(ids) == 40 == len(set(ids)) and sim["order"][:8] == [0, 1, 2, 3, 3, 2, 1, 0]
    assert simulate(idx, [], 4, 10, seed=2)["picks"] == sim["picks"]      # same seed, same draft
    v = lab_view(idx, [], sim["order"], sim["picks"], sim["per_seat"], 9, people=frozenset())
    assert v["took"]["card"] == sim["picks"][9]["card_id"]


def test_big_pools_go_to_spellbook_in_batches_that_cover_every_small_combo():
    from itertools import combinations
    from draftbot.combos import spellbook_batches
    assert spellbook_batches([f"c{i}" for i in range(500)]) == [[f"c{i}" for i in range(500)]]
    names = [f"c{i}" for i in range(903)]
    batches = spellbook_batches(names)
    assert len(batches) == 10 and all(len(b) <= 600 for b in batches)
    sets = [set(b) for b in batches]
    sample = names[::37]
    assert all(any(set(trio) <= s for s in sets) for trio in combinations(sample, 3))


def _lab_pool():
    from draftbot.combos import attach_combos as _attach
    idx = build_card_index(synthetic_cube())
    _attach(idx, [])
    return idx


def test_lab_simulate_rewind_keeps_earlier_picks_and_reproduces_the_rest():
    from draftbot.lab import simulate
    idx = _lab_pool()
    full = simulate(idx, [], 4, 12, seed=7)
    assert len(full["picks"]) == 48 and full["kept"] == 0
    again = simulate(idx, [], 4, 12, seed=7)
    assert again["picks"] == full["picks"]                        # same seed and weights: same draft
    rewound = simulate(idx, [], 4, 12, seed=7, start=full["picks"][:20])
    assert rewound["kept"] == 20
    assert rewound["picks"] == full["picks"]                      # unchanged weights: re-draft matches
    tuned = simulate(idx, [], 4, 12, seed=7, start=full["picks"][:20], tuning={"committed_floor": 1.0, "flex_floor": 1.0})
    assert tuned["picks"][:20] == full["picks"][:20]              # picks before the rewind never change
    assert len(tuned["seats"]) == 4 and all("pair" in s for s in tuned["seats"])


def test_lab_simulate_tuned_seats_and_stop():
    from draftbot.lab import simulate
    idx = _lab_pool()
    base = simulate(idx, [], 4, 12, seed=3)
    off = simulate(idx, [], 4, 12, seed=3, tuning={"committed_floor": 1.0, "flex_floor": 1.0}, tuned_seats=[])
    assert off["picks"] == base["picks"]                          # weights for no seat change nothing
    part = simulate(idx, [], 4, 12, seed=3, stop=10)
    assert len(part["picks"]) == 10 and len(part["order"]) == 48
    bad = simulate(idx, [], 4, 12, seed=3, start=[{"order": 0, "seat_index": 2, "card_id": base["picks"][0]["card_id"]}])
    assert bad["kept"] == 0                                       # a kept pick in the wrong seat is dropped


def test_shared_memo_never_changes_a_pick():
    """lab.simulate shares one memo across the draft's picks; re-scoring every pick without it must agree."""
    from draftbot.lab import _pick_rng, simulate
    from draftbot.combos import Combo, attach_combos as _attach
    idx = build_card_index(synthetic_cube())
    ids = sorted(idx)
    rng = random.Random(4)
    combos = [Combo(tuple(rng.sample(ids, rng.choice([2, 3]))), 0.8) for _ in range(30)]
    _attach(idx, combos)
    tuning = {"partner_weight": 0.8, "focus_start": 0.3}
    run = simulate(idx, combos, 4, 12, seed=11, tuning=tuning, tuned_seats=[1, 2])
    by_seat = {s: [] for s in range(4)}
    remaining = list(idx)
    for p in run["picks"]:
        seat, slot = p["seat_index"], p["order"]
        t = tuning if seat in (1, 2) else None
        ctx = BotContext(idx, combos, remaining, by_seat, seat, run["order"], slot, run["per_seat"],
                         Persona("steady", temperature=0.03), t, people=frozenset())
        assert choose_pick(ctx, _pick_rng(11, slot)) == p["card_id"]
        by_seat[seat].append(p["card_id"])
        name = idx[p["card_id"]].name.lower()
        remaining = [c for c in remaining if c != p["card_id"] and idx[c].name.lower() != name]


def test_browser_session_streams_the_same_draft_as_simulate():
    """The Bot Brain page runs drafts a few picks at a time in the browser; they must match lab.simulate."""
    import json
    from draftbot.browser import Session
    from draftbot.lab import simulate
    cube = synthetic_cube()
    s = Session()
    src = json.loads(s.load(json.dumps({"cards": cube, "stats": None, "combos": []})))
    assert src["summary"]["cards"] == len(cube) and src["knobs"]
    tuning = {"partner_weight": 0.9}
    json.loads(s.run_start(json.dumps({"seats": 4, "picks": 12, "seed": 5, "tuning": tuning})))
    picks = []
    while True:
        r = json.loads(s.run_step(5))
        picks += r["picks"]
        if r["done"]:
            break
    assert picks == simulate(s.index, s.combos, 4, 12, seed=5, tuning=tuning)["picks"]
    assert len(r["seats"]) == 4
    view = json.loads(s.view(json.dumps({"order": [p["seat_index"] for p in picks], "picks": picks, "slot": 10})))
    assert view["slot"] == 10 and view["rows"]


def test_core_cards_belong_to_a_deck_type_without_being_keys():
    """Lightning Bolt counts towards red aggro for a bot in it, but isn't a key card: bots outside red aggro
    still value it fully. Signature cards (Goblin Guide) are keys."""
    from draftbot.engine import deck_factor
    cube = synthetic_cube() + [
        card("bolt", "Lightning Bolt", "{R}", 1, "Instant", "Lightning Bolt deals 3 damage to any target.", "R", 1750),
        card("guide", "Goblin Guide", "{R}", 1, "Creature — Goblin Scout", "Haste", "R", 1600),
        card("ragavan", "Ragavan, Nimble Pilferer", "{R}", 1, "Legendary Creature — Monkey Pirate", "", "R", 1800),
    ]
    idx = build_card_index(cube)
    assert idx["bolt"].key_of == frozenset() and idx["bolt"].deck.get("red_aggro", 0) >= 0.5
    assert "red_aggro" in idx["guide"].key_of
    assert {"red_aggro", "tempo"} <= idx["ragavan"].key_of
    ctx = _two_seat_ctx(cube, [], ["U0"], [])
    from draftbot.decktypes import DECK_TYPES
    eff = {t: 0.0 for t in DECK_TYPES}
    assert deck_factor(ctx, idx["bolt"], eff, {t: 0.0 for t in DECK_TYPES}, 0.0) == 1.0
    assert deck_factor(ctx, idx["guide"], eff, {t: 0.0 for t in DECK_TYPES}, 0.0) < 1.0
