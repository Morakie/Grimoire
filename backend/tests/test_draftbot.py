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


def _two_seat_ctx(cube, combos, my_picks, rival_picks, persona=None):
    idx = build_card_index(cube)
    attach_combos(idx, combos)
    taken = set(my_picks) | set(rival_picks)
    remaining = [c for c in idx if c not in taken]
    order = [0, 1, 1, 0] * 20          # slot 0 is ours; the rival picks twice before our next turn
    slot = 0
    return BotContext(idx, combos, remaining, {0: list(my_picks), 1: list(rival_picks)}, 0, order, slot, 40,
                      persona or Persona("steady", temperature=0.001))


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
    few = {cid: s for s, cid, _ in score_pool(_two_seat_ctx(cube, [], ["rock0"], []))}
    glut = {cid: s for s, cid, _ in score_pool(_two_seat_ctx(cube, [], ["rock0", "rock1", "rock2"], []))}
    assert glut["rock4"] < few["rock4"] * 0.8, (few["rock4"], glut["rock4"])


def test_owned_lands_make_a_third_colour_a_splash():
    """Duals in a third colour (taken early, as in a powered cube) let that colour's cards in as a splash."""
    from draftbot.engine import splash_colour, TUNING
    cube = synthetic_cube() + [card(f"ub{i}", f"UB dual {i}", "", 0, "Land", "Add {U} or {B}.", "UB", 1450) for i in range(4)]
    index = build_card_index(cube)
    k = lambda key: TUNING[key]
    spells = [index[f"U{i}"] for i in range(4)] + [index[f"G{i}"] for i in range(4)]
    assert splash_colour(spells, frozenset("UG"), k) is None
    lands = [index[f"ub{i}"] for i in range(4)]
    assert splash_colour(spells + lands, frozenset("UG"), k) == "B"


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
