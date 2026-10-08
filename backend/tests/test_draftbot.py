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
