"""Open-lobby filtering (/drafts/open) and host cancel (/drafts/{share_id}/cancel)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

CUBE_NAMES = ["Sol Ring", "Lightning Bolt", "Counterspell", "Llanowar Elves",
              "Mountain", "Island", "Forest", "Swamp",
              "Serra Angel", "Shock", "Giant Growth", "Doom Blade"]


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


def _create(session, cube, name="TEST_LOBBY"):
    r = session.post(f"{API}/drafts", json={
        "name": name, "num_players": 2, "num_seats": 4,
        "pick_cap": 2, "double_draft_after": 0, "cube": cube,
    })
    assert r.status_code == 200, r.text
    return r.json()  # contains share_id and host_token


class TestOpenLobby:
    def test_create_returns_host_token(self, session, cube):
        d = _create(session, cube, "TEST_hostoken")
        assert "host_token" in d and len(d["host_token"]) >= 16

    def test_open_lists_lobby_drafts(self, session, cube):
        d = _create(session, cube, "TEST_openlist")
        r = session.get(f"{API}/drafts/open")
        assert r.status_code == 200
        sids = [x["share_id"] for x in r.json()["drafts"]]
        assert d["share_id"] in sids

    def test_open_excludes_cancelled(self, session, cube):
        d = _create(session, cube, "TEST_cancelme")
        r = session.post(f"{API}/drafts/{d['share_id']}/cancel",
                         json={"host_token": d["host_token"]})
        assert r.status_code == 200
        listing = session.get(f"{API}/drafts/open").json()["drafts"]
        assert d["share_id"] not in [x["share_id"] for x in listing]

    def test_open_excludes_started(self, session, cube):
        d = _create(session, cube, "TEST_started")
        sid = d["share_id"]
        session.post(f"{API}/drafts/{sid}/claim", json={"name": "A"})
        session.post(f"{API}/drafts/{sid}/claim", json={"name": "B"})
        r = session.post(f"{API}/drafts/{sid}/start")
        assert r.status_code == 200
        listing = session.get(f"{API}/drafts/open").json()["drafts"]
        assert sid not in [x["share_id"] for x in listing]


class TestCancel:
    def test_cancel_wrong_host_token_forbidden(self, session, cube):
        d = _create(session, cube, "TEST_wronghost")
        r = session.post(f"{API}/drafts/{d['share_id']}/cancel",
                         json={"host_token": "not-the-right-token"})
        assert r.status_code == 403

    def test_cancel_correct_host_token_ok(self, session, cube):
        d = _create(session, cube, "TEST_righthost")
        r = session.post(f"{API}/drafts/{d['share_id']}/cancel",
                         json={"host_token": d["host_token"]})
        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"

    def test_cancelled_draft_still_fetchable(self, session, cube):
        d = _create(session, cube, "TEST_fetchcanc")
        session.post(f"{API}/drafts/{d['share_id']}/cancel",
                     json={"host_token": d["host_token"]})
        r = session.get(f"{API}/drafts/{d['share_id']}")
        assert r.status_code == 200
        assert r.json()["status"] == "cancelled"

    def test_cancel_unknown_draft_404(self, session):
        r = session.post(f"{API}/drafts/nosuchsid/cancel",
                         json={"host_token": "anything"})
        assert r.status_code == 404
