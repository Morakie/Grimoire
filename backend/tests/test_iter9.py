"""Iteration 9 backend tests: seat spread, ELO on cards, printings earliest-first."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

CUBE_NAMES = [
    "Sol Ring", "Lightning Bolt", "Counterspell", "Llanowar Elves",
    "Mountain", "Island", "Forest", "Swamp",
    "Serra Angel", "Shock", "Giant Growth", "Doom Blade",
    "Wrath of God", "Dark Ritual", "Birds of Paradise", "Bayou",
]


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def cube(session):
    r = session.post(f"{API}/cards/collection", json={"names": CUBE_NAMES})
    assert r.status_code == 200
    return r.json()["cards"]


# -------- Seat spread: no player holds both end seats --------
class TestSeatSpread:
    def _make(self, session, cube, players, seats):
        r = session.post(f"{API}/drafts", json={
            "name": "SEAT_SPREAD", "num_players": players, "num_seats": seats,
            "pick_cap": 2, "double_draft_after": 0, "cube": cube,
        })
        assert r.status_code == 200, r.text
        return r.json()["share_id"]

    def test_2p8s_no_both_ends(self, session, cube):
        sid = self._make(session, cube, 2, 8)
        a = session.post(f"{API}/drafts/{sid}/claim", json={"name": "P1"}).json()
        b = session.post(f"{API}/drafts/{sid}/claim", json={"name": "P2"}).json()
        assert sorted(a["seats"] + b["seats"]) == list(range(8))
        # No player should hold both 0 and 7
        for p in (a, b):
            assert not (0 in p["seats"] and 7 in p["seats"]), f"Player holds both end seats: {p['seats']}"
        # Expected spread by index%num_players: P1=[0,2,4,6], P2=[1,3,5,7]
        assert set(a["seats"]) == {0, 2, 4, 6}
        assert set(b["seats"]) == {1, 3, 5, 7}

    def test_4p8s_no_both_ends(self, session, cube):
        sid = self._make(session, cube, 4, 8)
        players = [session.post(f"{API}/drafts/{sid}/claim", json={"name": f"P{i}"}).json()
                   for i in range(1, 5)]
        for p in players:
            assert len(p["seats"]) == 2
            assert not (0 in p["seats"] and 7 in p["seats"])
        # End seats 0 and 7 should belong to different players
        owner0 = next(p for p in players if 0 in p["seats"])
        owner7 = next(p for p in players if 7 in p["seats"])
        assert owner0["player_token"] != owner7["player_token"]


# -------- ELO on map_card --------
class TestCardElo:
    def test_collection_includes_elo(self, session):
        r = session.post(f"{API}/cards/collection", json={"names": ["Black Lotus", "Lightning Bolt"]})
        assert r.status_code == 200
        cards = r.json()["cards"]
        by_name = {c["name"]: c for c in cards}
        assert "Black Lotus" in by_name
        bl = by_name["Black Lotus"]
        assert "elo" in bl, f"Missing elo on Black Lotus: {bl.keys()}"
        assert isinstance(bl["elo"], int)
        assert bl["elo"] > 2000, f"Expected high elo for Black Lotus, got {bl['elo']}"

    def test_search_includes_elo(self, session):
        r = session.get(f"{API}/cards/search", params={"q": "Lightning Bolt"})
        assert r.status_code == 200
        cards = r.json().get("cards", [])
        assert cards, "No cards returned from search"
        # Scryfall relevance may return DFCs/split cards first; find Lightning Bolt in results.
        exact = [c for c in cards if c["name"] == "Lightning Bolt"]
        assert exact, f"'Lightning Bolt' not in search results: {[c['name'] for c in cards[:5]]}"
        assert "elo" in exact[0]


# -------- Printings earliest-first --------
class TestPrintingsOrder:
    def test_lightning_bolt_earliest_first(self, session):
        r = session.get(f"{API}/cards/printings", params={"name": "Lightning Bolt"})
        assert r.status_code == 200
        data = r.json()
        prints = data.get("printings") or data.get("cards") or []
        assert len(prints) >= 3
        # First printing should be LEA (Limited Edition Alpha), the earliest Magic set.
        first_set = (prints[0].get("set") or "").lower()
        assert first_set == "lea", f"Earliest printing set expected 'lea', got '{first_set}'"
