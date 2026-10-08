"""Backend API tests for Grimoire MTG deck-builder."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me-locally")


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(session):
    r = session.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ----------------- Auth -----------------
class TestAuth:
    def test_register_new_user(self, session):
        email = f"TEST_{uuid.uuid4().hex[:8]}@example.com"
        r = session.post(f"{API}/auth/register", json={"email": email, "password": "secret123", "name": "Tester"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert "token" in d and d["user"]["email"].lower() == email.lower()

    def test_register_duplicate(self, session):
        r = session.post(f"{API}/auth/register", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "name": "x"})
        assert r.status_code == 400

    def test_login_admin(self, session):
        r = session.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200
        assert "token" in r.json()

    def test_login_invalid(self, session):
        r = session.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
        assert r.status_code == 401

    def test_me_requires_auth(self, session):
        r = session.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_me_with_token(self, session, auth_headers):
        r = session.get(f"{API}/auth/me", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL


# ----------------- Scryfall proxy -----------------
class TestCards:
    def test_search_cards(self, session):
        r = session.get(f"{API}/cards/search", params={"q": "lightning bolt"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert "cards" in d and len(d["cards"]) > 0
        card = d["cards"][0]
        for key in ("id", "name", "cmc", "colors", "type_line"):
            assert key in card

    def test_search_empty(self, session):
        r = session.get(f"{API}/cards/search", params={"q": ""})
        assert r.status_code == 400

    def test_search_filtered(self, session):
        r = session.get(f"{API}/cards/search", params={"q": "goblin", "colors": "R", "type": "creature"})
        assert r.status_code == 200
        assert len(r.json()["cards"]) > 0

    def test_printings(self, session):
        r = session.get(f"{API}/cards/printings", params={"name": "Lightning Bolt"})
        assert r.status_code == 200
        assert len(r.json()["printings"]) >= 1

    def test_autocomplete(self, session):
        r = session.get(f"{API}/cards/autocomplete", params={"q": "light"})
        assert r.status_code == 200
        d = r.json()
        assert "suggestions" in d
        assert isinstance(d["suggestions"], list)
        assert len(d["suggestions"]) > 0

    def test_autocomplete_short_query(self, session):
        r = session.get(f"{API}/cards/autocomplete", params={"q": "a"})
        assert r.status_code == 200
        assert r.json()["suggestions"] == []

    def test_collection_resolve(self, session):
        r = session.post(f"{API}/cards/collection",
                         json={"names": ["Lightning Bolt", "Counterspell", "Mountain", "FakeCardNameXyz"]})
        assert r.status_code == 200, r.text
        d = r.json()
        assert "cards" in d and "not_found" in d
        names = {c["name"] for c in d["cards"]}
        assert "Lightning Bolt" in names
        assert "Counterspell" in names
        assert "Mountain" in names
        assert any("FakeCardNameXyz".lower() in nf.lower() for nf in d["not_found"])

    def test_collection_empty(self, session):
        r = session.post(f"{API}/cards/collection", json={"names": []})
        assert r.status_code == 200
        assert r.json()["cards"] == []


# ----------------- Decks CRUD -----------------
class TestDecks:
    deck_id = None
    share_id = None

    def test_create_deck(self, session, auth_headers):
        payload = {"name": "TEST_Deck", "format": "standard", "description": "", "mainboard": [], "sideboard": [], "commander": []}
        r = session.post(f"{API}/decks", json=payload, headers=auth_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["name"] == "TEST_Deck"
        assert d["share_id"]
        TestDecks.deck_id = d["id"]
        TestDecks.share_id = d["share_id"]

    def test_get_deck(self, session, auth_headers):
        r = session.get(f"{API}/decks/{TestDecks.deck_id}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["id"] == TestDecks.deck_id

    def test_list_decks(self, session, auth_headers):
        r = session.get(f"{API}/decks", headers=auth_headers)
        assert r.status_code == 200
        assert any(d["id"] == TestDecks.deck_id for d in r.json())

    def test_update_deck(self, session, auth_headers):
        card = {"id": "abc123", "name": "Lightning Bolt", "mana_cost": "{R}", "cmc": 1, "type_line": "Instant",
                "colors": ["R"], "color_identity": ["R"], "quantity": 2}
        payload = {"name": "TEST_Deck_Updated", "format": "standard", "description": "d",
                   "mainboard": [card], "sideboard": [], "commander": []}
        r = session.put(f"{API}/decks/{TestDecks.deck_id}", json=payload, headers=auth_headers)
        assert r.status_code == 200
        # verify via GET
        r2 = session.get(f"{API}/decks/{TestDecks.deck_id}", headers=auth_headers)
        d = r2.json()
        assert d["name"] == "TEST_Deck_Updated"
        assert len(d["mainboard"]) == 1 and d["mainboard"][0]["quantity"] == 2

    def test_group_overrides_roundtrip(self, session, auth_headers):
        """Verify DeckCard.group_overrides persists through PUT/GET."""
        card = {"id": "ovr1", "name": "Serra Angel", "mana_cost": "{3}{W}{W}", "cmc": 5,
                "type_line": "Creature — Angel", "colors": ["W"], "color_identity": ["W"],
                "quantity": 1, "group_overrides": {"cmc": "0", "type": "Lands"}}
        payload = {"name": "TEST_Deck_Updated", "format": "standard", "description": "d",
                   "mainboard": [card], "sideboard": [], "commander": []}
        r = session.put(f"{API}/decks/{TestDecks.deck_id}", json=payload, headers=auth_headers)
        assert r.status_code == 200, r.text
        r2 = session.get(f"{API}/decks/{TestDecks.deck_id}", headers=auth_headers)
        assert r2.status_code == 200
        mb = r2.json()["mainboard"]
        assert len(mb) == 1
        assert mb[0].get("group_overrides") == {"cmc": "0", "type": "Lands"}

    def test_public_share(self, session):
        r = session.get(f"{API}/decks/public/{TestDecks.share_id}")
        assert r.status_code == 200
        d = r.json()
        assert d["share_id"] == TestDecks.share_id
        assert "name" in d

    def test_clone_deck(self, session, auth_headers):
        r = session.post(f"{API}/decks/{TestDecks.deck_id}/clone", headers=auth_headers)
        assert r.status_code == 200
        d = r.json()
        assert "(Copy)" in d["name"]
        # cleanup clone
        session.delete(f"{API}/decks/{d['id']}", headers=auth_headers)

    def test_delete_deck(self, session, auth_headers):
        r = session.delete(f"{API}/decks/{TestDecks.deck_id}", headers=auth_headers)
        assert r.status_code == 200
        r2 = session.get(f"{API}/decks/{TestDecks.deck_id}", headers=auth_headers)
        assert r2.status_code == 404

    def test_unauthenticated_deck_access(self, session):
        r = session.get(f"{API}/decks")
        assert r.status_code == 401
