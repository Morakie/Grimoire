"""VRD helpers (pure Python, no server needed)."""
import vrd


def raw(name, type_line="Instant", vintage="legal", games=("paper", "mtgo")):
    return {"name": name, "type_line": type_line, "legalities": {"vintage": vintage}, "games": list(games)}


def test_legality_rules():
    assert vrd.is_legal(raw("Lightning Bolt"))
    assert vrd.is_legal(raw("Black Lotus", "Artifact", vintage="restricted"))
    assert not vrd.is_legal(raw("Chaos Orb", vintage="banned"))
    assert not vrd.is_legal(raw("Alchemy Card", vintage="not_legal", games=("arena",)))
    assert vrd.is_legal(raw("Mox Sapphire", "Artifact", vintage="restricted", games=("mtgo",)))   # online-only printing is fine
    assert not vrd.is_legal(raw("Island", "Basic Land — Island"))
    assert not vrd.is_legal(raw("Snow-Covered Forest", "Basic Snow Land — Forest"))
    assert vrd.is_basic(raw("Wastes", "Basic Land"))


def test_ranked_names_from_bundled_elo_list():
    names = vrd.ranked_names(50)
    assert len(names) == 50 and len({n.lower() for n in names}) == 50
    assert names[0] == "Black Lotus"        # highest CubeCobra Elo in the bundled list
