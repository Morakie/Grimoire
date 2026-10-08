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
    assert contested["freeze"] > 0.6
