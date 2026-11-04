"""Cube analysis (draftbot/analysis.py): pure Python, no server needed."""
from draftbot.analysis import cube_analysis, viability
from draftbot.combos import Combo, attach_combos, combos_from_dicts
from draftbot.features import build_card_index

from tests.test_draftbot import card, synthetic_cube


def _cube():
    cube = synthetic_cube()
    cube += [
        card("ent", "Entomb", "{B}", 1, "Instant", "Search your library for a card, put that card into your graveyard.", "B", 1600),
        card("rea", "Reanimate", "{B}", 1, "Sorcery", "Put target creature card from a graveyard onto the battlefield under your control.", "B", 1650),
        card("gri", "Griselbrand", "{4}{B}{B}{B}{B}", 8, "Legendary Creature — Demon", "Flying, lifelink", "B", 1580),
        card("kit", "Felidar Guardian", "{3}{W}", 4, "Creature — Cat Beast", "When this enters, exile another target permanent you control, then return it.", "W", 1400),
        card("sai", "Saheeli Rai", "{1}{U}{R}", 3, "Legendary Planeswalker — Saheeli", "Create a token copy.", "UR", 1450),
        card("sol", "Sol Ring", "{1}", 1, "Artifact", "{T}: Add {C}{C}.", "", 1700),
    ]
    return cube


def test_analysis_lists_cards_deck_types_and_combos():
    cube = _cube()
    index = build_card_index(cube)
    combos = [Combo(("kit", "sai"), 0.9, ("Infinite tokens",), "123-456")]
    attach_combos(index, combos)
    out = cube_analysis(index, combos, cube, meta={})
    by_id = {c["id"]: c for c in out["cards"]}
    assert len(by_id) == len(cube)
    assert by_id["sol"]["rank"] == 1 and by_id["sol"]["column"] == "C"
    assert by_id["sai"]["column"] == "M" and by_id["land0"]["column"] == "L"
    assert by_id["kit"]["combos"] == 1
    rean = next(d for d in out["decks"] if d["type"] == "reanimator")
    roles = {m["id"]: m["role"] for m in rean["members"]}
    assert roles.get("ent") == "key" and roles.get("rea") == "key"
    assert rean["keys"] >= 2 and "Griselbrand" not in rean["missing_keys"]
    assert out["combos"][0]["produces"] == ["Infinite tokens"] and out["combos"][0]["sid"] == "123-456"
    assert len(out["overview"]["pairs"]) == 10
    assert out["overview"]["total"] == len(cube)
    scores = [d["score"] for d in out["decks"]]
    assert scores == sorted(scores, reverse=True)


def test_viability_needs_key_cards():
    assert viability(0, 60, 5)[1] == "Unlikely"
    assert viability(6, 46, 5) == (100, "Strong")
    assert viability(2, 20, 0)[1] in ("Thin", "Viable")


def test_combo_details_survive_a_round_trip():
    c = Combo(("a", "b"), 0.8, ("Infinite mana", "Infinite storm count"), "1-2")
    back = combos_from_dicts([c.to_dict()])[0]
    assert back == c
    old = combos_from_dicts([{"pieces": ["a", "b"], "weight": 0.7}])[0]   # pools saved before details existed
    assert old.produces == () and old.sid == ""
