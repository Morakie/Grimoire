"""Suggested deck from a drafted pool (pure Python, no server needed)."""
from draftbot.deckbuild import suggest_deck, _pips
from draftbot.features import build_card_index
from tests.test_draftbot import card, synthetic_cube


def _pool(cube, ids):
    by_id = {c["id"]: c for c in cube}
    return [by_id[i] for i in ids]


def test_pips_count_hybrid_as_half():
    assert _pips("{2}{U}{U}") == {"U": 2.0}
    assert _pips("{W/U}{R}") == {"W": 0.5, "U": 0.5, "R": 1.0}


def test_two_colour_pool_builds_forty_cards():
    cube = synthetic_cube()
    index = build_card_index(cube)
    # Mostly blue and red, a few strays, one UR-ish dual (none exist: use the UB dual as a stray land).
    ids = [f"U{i}" for i in range(15)] + [f"R{i}" for i in range(14)] + ["W1", "G2", "B3", "land1"]
    out = suggest_deck(_pool(cube, ids), index)
    assert out["colors"] == ["U", "R"]
    main = out["main"]
    assert all(m[0] in "UR" or m.startswith("land") for m in main)
    total = len(main) + sum(out["basics"].values())
    assert total == 40
    assert set(out["basics"]) <= {"U", "R"} and all(v > 0 for v in out["basics"].values())


def test_other_sizes_and_empty_pool():
    cube = synthetic_cube()
    index = build_card_index(cube)
    ids = [f"G{i}" for i in range(20)] + [f"W{i}" for i in range(20)]
    out = suggest_deck(_pool(cube, ids), index, size=60)
    assert len(out["main"]) + sum(out["basics"].values()) == 60
    assert suggest_deck([], index) == {"main": [], "basics": {}, "colors": [], "splash": None}


def test_custom_cards_never_in_main():
    cube = synthetic_cube() + [dict(card("custom-x", "Homebrew", "{U}", 1), is_custom=True)]
    index = build_card_index(cube)
    out = suggest_deck(_pool(cube, ["custom-x"] + [f"U{i}" for i in range(20)]), index)
    assert "custom-x" not in out["main"]
