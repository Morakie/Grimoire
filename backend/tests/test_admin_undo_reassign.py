"""Backend tests for host-only ADMIN tools: undo + reassign."""
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
def resolved_cube(session):
    r = session.post(f"{API}/cards/collection", json={"names": CUBE_NAMES})
    assert r.status_code == 200, r.text
    return r.json()["cards"]


def _make_active_draft(session, cube, num_players=2, num_seats=2, pick_cap=3):
    r = session.post(f"{API}/drafts", json={
        "name": "TEST_admin", "num_players": num_players, "num_seats": num_seats,
        "pick_cap": pick_cap, "double_draft_after": 0, "cube": cube,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    sid = data["share_id"]
    host_token = data["host_token"]

    tokens = []
    for i in range(num_seats):
        rc = session.post(f"{API}/drafts/{sid}/claim", json={"name": f"TEST_P{i}", "seat_index": i})
        assert rc.status_code == 200, rc.text
        tokens.append(rc.json()["player_token"])

    rs = session.post(f"{API}/drafts/{sid}/start")
    assert rs.status_code == 200, rs.text
    return sid, host_token, tokens


def _pick_current(session, sid, tokens, card_id):
    g = session.get(f"{API}/drafts/{sid}").json()
    seat = g["current_seat_index"]
    assert seat is not None
    r = session.post(f"{API}/drafts/{sid}/pick", json={
        "seat_index": seat, "player_token": tokens[seat], "card_id": card_id,
    })
    assert r.status_code == 200, r.text
    return seat


class TestUndo:
    def test_undo_wrong_token_forbidden(self, session, resolved_cube):
        sid, host_token, tokens = _make_active_draft(session, resolved_cube)
        _pick_current(session, sid, tokens, resolved_cube[0]["id"])
        r = session.post(f"{API}/drafts/{sid}/undo", json={"host_token": "bad"})
        assert r.status_code == 403

    def test_undo_no_picks_400(self, session, resolved_cube):
        sid, host_token, tokens = _make_active_draft(session, resolved_cube)
        r = session.post(f"{API}/drafts/{sid}/undo", json={"host_token": host_token})
        assert r.status_code == 400

    def test_undo_success_decrements_and_returns_card(self, session, resolved_cube):
        sid, host_token, tokens = _make_active_draft(session, resolved_cube)
        card0 = resolved_cube[0]["id"]
        _pick_current(session, sid, tokens, card0)

        g = session.get(f"{API}/drafts/{sid}").json()
        assert len(g["picks"]) == 1
        assert card0 in {p["card_id"] for p in g["picks"]}

        r = session.post(f"{API}/drafts/{sid}/undo", json={"host_token": host_token})
        assert r.status_code == 200
        g2 = session.get(f"{API}/drafts/{sid}").json()
        assert len(g2["picks"]) == 0
        assert card0 not in {p["card_id"] for p in g2["picks"]}
        assert g2["status"] == "drafting"

    def test_undo_from_complete_sets_drafting(self, session, resolved_cube):
        # 2 seats * pick_cap 1 => completes after 2 picks
        sid, host_token, tokens = _make_active_draft(session, resolved_cube, num_seats=2, pick_cap=1)
        _pick_current(session, sid, tokens, resolved_cube[0]["id"])
        _pick_current(session, sid, tokens, resolved_cube[1]["id"])
        g = session.get(f"{API}/drafts/{sid}").json()
        assert g["status"] == "complete"

        r = session.post(f"{API}/drafts/{sid}/undo", json={"host_token": host_token})
        assert r.status_code == 200
        g2 = session.get(f"{API}/drafts/{sid}").json()
        assert g2["status"] == "drafting"
        assert len(g2["picks"]) == 1

    def test_undo_repeated_steps_back(self, session, resolved_cube):
        sid, host_token, tokens = _make_active_draft(session, resolved_cube, pick_cap=3)
        for i in range(3):
            _pick_current(session, sid, tokens, resolved_cube[i]["id"])
        for expected in [2, 1, 0]:
            r = session.post(f"{API}/drafts/{sid}/undo", json={"host_token": host_token})
            assert r.status_code == 200
            g = session.get(f"{API}/drafts/{sid}").json()
            assert len(g["picks"]) == expected


class TestReassign:
    def test_reassign_success(self, session, resolved_cube):
        sid, host_token, tokens = _make_active_draft(session, resolved_cube)
        original = resolved_cube[0]["id"]
        new_card = resolved_cube[5]["id"]
        seat = _pick_current(session, sid, tokens, original)

        r = session.post(f"{API}/drafts/{sid}/reassign", json={
            "host_token": host_token, "order": 0, "card_id": new_card,
        })
        assert r.status_code == 200, r.text
        g = session.get(f"{API}/drafts/{sid}").json()
        pk = next(p for p in g["picks"] if p["order"] == 0)
        assert pk["card_id"] == new_card
        assert pk["seat_index"] == seat

    def test_reassign_wrong_token_403(self, session, resolved_cube):
        sid, host_token, tokens = _make_active_draft(session, resolved_cube)
        _pick_current(session, sid, tokens, resolved_cube[0]["id"])
        r = session.post(f"{API}/drafts/{sid}/reassign", json={
            "host_token": "nope", "order": 0, "card_id": resolved_cube[5]["id"],
        })
        assert r.status_code == 403

    def test_reassign_missing_order_404(self, session, resolved_cube):
        sid, host_token, tokens = _make_active_draft(session, resolved_cube)
        r = session.post(f"{API}/drafts/{sid}/reassign", json={
            "host_token": host_token, "order": 99, "card_id": resolved_cube[0]["id"],
        })
        assert r.status_code == 404

    def test_reassign_card_not_in_cube_400(self, session, resolved_cube):
        sid, host_token, tokens = _make_active_draft(session, resolved_cube)
        _pick_current(session, sid, tokens, resolved_cube[0]["id"])
        r = session.post(f"{API}/drafts/{sid}/reassign", json={
            "host_token": host_token, "order": 0, "card_id": "not-a-real-id",
        })
        assert r.status_code == 400

    def test_reassign_already_drafted_409(self, session, resolved_cube):
        sid, host_token, tokens = _make_active_draft(session, resolved_cube, pick_cap=3)
        card_a = resolved_cube[0]["id"]
        card_b = resolved_cube[1]["id"]
        _pick_current(session, sid, tokens, card_a)
        _pick_current(session, sid, tokens, card_b)
        r = session.post(f"{API}/drafts/{sid}/reassign", json={
            "host_token": host_token, "order": 0, "card_id": card_b,
        })
        assert r.status_code == 409
