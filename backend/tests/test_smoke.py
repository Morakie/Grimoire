"""End-to-end smoke test of the main API surface.

Covers: /api/health, admin JWT login, /api/auth/me, cards search (Scryfall),
deck CRUD + public share, drafts create + /api/drafts/open + state.
"""
import os
import uuid
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")
BASE = BASE.rstrip("/")
API = f"{BASE}/api"

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me-locally")


# --- fixtures ---------------------------------------------------------------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data and isinstance(data["token"], str) and data["token"]
    assert data["user"]["email"] == ADMIN_EMAIL
    return data["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# --- health -----------------------------------------------------------------
class TestHealth:
    def test_health_ok(self):
        r = requests.get(f"{API}/health", timeout=15)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"


# --- auth -------------------------------------------------------------------
class TestAuth:
    def test_login_and_me(self, admin_token):
        r = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {admin_token}"}, timeout=15)
        assert r.status_code == 200
        me = r.json()
        assert me["email"] == ADMIN_EMAIL
        assert "id" in me

    def test_login_bad_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"}, timeout=15)
        assert r.status_code in (400, 401)

    def test_me_requires_auth(self):
        r = requests.get(f"{API}/auth/me", timeout=15)
        assert r.status_code in (401, 403)


# --- cards search -----------------------------------------------------------
class TestCardsSearch:
    def test_scryfall_search_returns_results(self):
        r = requests.get(f"{API}/cards/search", params={"q": "lightning bolt"}, timeout=30)
        assert r.status_code == 200, r.text
        payload = r.json()
        # response may be {data:[...]} or list
        cards = payload.get("cards") if isinstance(payload, dict) else payload
        assert isinstance(cards, list) and len(cards) > 0
        names = [c.get("name", "").lower() for c in cards]
        assert any("lightning bolt" in n for n in names)


# --- deck CRUD + public share ----------------------------------------------
class TestDeckCRUD:
    def _payload(self, name):
        return {
            "name": name,
            "format": "standard",
            "description": "regression test deck",
            "mainboard": [{"id": "test-bolt", "name": "Lightning Bolt", "quantity": 4}],
            "sideboard": [],
            "commander": [],
        }

    def test_full_crud_and_public_share(self, auth_headers):
        name = f"TEST_regression_{uuid.uuid4().hex[:6]}"
        # CREATE
        r = requests.post(f"{API}/decks", headers=auth_headers, json=self._payload(name), timeout=20)
        assert r.status_code == 200, r.text
        deck = r.json()
        deck_id = deck["id"]
        share_id = deck["share_id"]
        assert deck["name"] == name
        assert len(deck["mainboard"]) == 1

        # LIST (owned)
        r = requests.get(f"{API}/decks", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        assert any(d["id"] == deck_id for d in r.json())

        # GET
        r = requests.get(f"{API}/decks/{deck_id}", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        assert r.json()["id"] == deck_id

        # UPDATE
        upd = self._payload(name + "_upd")
        upd["description"] = "updated"
        r = requests.put(f"{API}/decks/{deck_id}", headers=auth_headers, json=upd, timeout=20)
        assert r.status_code == 200
        assert r.json()["description"] == "updated"
        # verify persisted
        r = requests.get(f"{API}/decks/{deck_id}", headers=auth_headers, timeout=20)
        assert r.json()["description"] == "updated"

        # PUBLIC SHARE (no auth)
        r = requests.get(f"{API}/decks/public/{share_id}", timeout=20)
        assert r.status_code == 200
        assert r.json()["id"] == deck_id

        # DELETE
        r = requests.delete(f"{API}/decks/{deck_id}", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        # verify gone
        r = requests.get(f"{API}/decks/{deck_id}", headers=auth_headers, timeout=20)
        assert r.status_code == 404

    def test_public_share_404(self):
        r = requests.get(f"{API}/decks/public/doesnotexist123", timeout=20)
        assert r.status_code == 404


# --- drafts -----------------------------------------------------------------
class TestDrafts:
    def _mini_cube(self, n=24):
        return [{"id": f"tcard-{i}", "name": f"TCard {i}", "mana_cost": "{1}"} for i in range(n)]

    def test_create_open_state(self):
        payload = {
            "name": f"TEST_regress_draft_{uuid.uuid4().hex[:6]}",
            "num_players": 2,
            "num_seats": 2,
            "pick_cap": 4,
            "cube": self._mini_cube(16),
        }
        r = requests.post(f"{API}/drafts", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        share_id = d["share_id"]
        assert "host_token" in d

        # listed in open drafts
        r = requests.get(f"{API}/drafts/open", timeout=20)
        assert r.status_code == 200
        open_list = r.json().get("drafts", [])
        assert any(x.get("share_id") == share_id for x in open_list)

        # state fetchable
        r = requests.get(f"{API}/drafts/{share_id}/state", timeout=20)
        assert r.status_code == 200
        state = r.json()
        assert state.get("status") in ("lobby", "drafting", "complete")

        # cleanup: cancel
        requests.post(f"{API}/drafts/{share_id}/cancel", json={"host_token": d["host_token"]}, timeout=15)
