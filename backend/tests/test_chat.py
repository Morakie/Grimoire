"""Backend tests for Table Chat + Live Pick Feed (iteration 7)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

CUBE_NAMES = [
    "Sol Ring", "Lightning Bolt", "Counterspell", "Llanowar Elves",
    "Mountain", "Island", "Forest", "Swamp",
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


@pytest.fixture
def draft_in_lobby(session, cube):
    r = session.post(f"{API}/drafts", json={
        "name": "CHAT_TEST", "num_players": 2, "num_seats": 4,
        "pick_cap": 2, "double_draft_after": 0, "cube": cube,
    })
    sid = r.json()["share_id"]
    a = session.post(f"{API}/drafts/{sid}/claim", json={"name": "Alice"}).json()
    b = session.post(f"{API}/drafts/{sid}/claim", json={"name": "Bob"}).json()
    return sid, a, b


class TestChatEndpoint:
    def test_chat_post_ok_in_lobby(self, session, draft_in_lobby):
        sid, a, _ = draft_in_lobby
        r = session.post(f"{API}/drafts/{sid}/chat", json={
            "player_token": a["player_token"], "text": "hello from alice"
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert "messages" in data
        assert len(data["messages"]) >= 1
        last = data["messages"][-1]
        assert last["name"] == "Alice"
        assert last["text"] == "hello from alice"
        assert "id" in last and "ts" in last

    def test_chat_bad_token_403(self, session, draft_in_lobby):
        sid, _, _ = draft_in_lobby
        r = session.post(f"{API}/drafts/{sid}/chat", json={
            "player_token": "not-a-real-token", "text": "sneaky"
        })
        assert r.status_code == 403

    def test_chat_empty_text_rejected(self, session, draft_in_lobby):
        sid, a, _ = draft_in_lobby
        r = session.post(f"{API}/drafts/{sid}/chat", json={
            "player_token": a["player_token"], "text": ""
        })
        assert r.status_code == 422

    def test_chat_404_unknown_draft(self, session):
        r = session.post(f"{API}/drafts/doesnotexist/chat", json={
            "player_token": "x", "text": "hi"
        })
        assert r.status_code == 404

    def test_messages_persist_in_state(self, session, draft_in_lobby):
        sid, a, b = draft_in_lobby
        session.post(f"{API}/drafts/{sid}/chat", json={
            "player_token": a["player_token"], "text": "msg from A"
        })
        session.post(f"{API}/drafts/{sid}/chat", json={
            "player_token": b["player_token"], "text": "msg from B"
        })
        st = session.get(f"{API}/drafts/{sid}/state").json()
        assert "messages" in st
        texts = [m["text"] for m in st["messages"]]
        assert "msg from A" in texts
        assert "msg from B" in texts
        names = {m["name"] for m in st["messages"]}
        assert {"Alice", "Bob"}.issubset(names)

    def test_messages_persist_through_picks_and_last_50(self, session, cube):
        # New draft
        r = session.post(f"{API}/drafts", json={
            "name": "CHAT_TEST_persist", "num_players": 2, "num_seats": 4,
            "pick_cap": 2, "double_draft_after": 0, "cube": cube,
        }).json()
        sid = r["share_id"]
        a = session.post(f"{API}/drafts/{sid}/claim", json={"name": "Alice"}).json()
        b = session.post(f"{API}/drafts/{sid}/claim", json={"name": "Bob"}).json()
        session.post(f"{API}/drafts/{sid}/start")
        # Post a message before picking
        session.post(f"{API}/drafts/{sid}/chat", json={
            "player_token": a["player_token"], "text": "before pick"
        })
        # Make one pick
        st = session.get(f"{API}/drafts/{sid}/state").json()
        seat = st["current_seat_index"]
        owner = a if seat in a["seats"] else b
        full = session.get(f"{API}/drafts/{sid}").json()
        card_id = full["cube"][0]["id"]
        session.post(f"{API}/drafts/{sid}/pick", json={
            "player_token": owner["player_token"], "seat_index": seat, "card_id": card_id
        })
        st = session.get(f"{API}/drafts/{sid}/state").json()
        assert any(m["text"] == "before pick" for m in st["messages"])
        assert len(st["picks"]) == 1

    def test_state_messages_capped_at_50(self, session, draft_in_lobby):
        sid, a, _ = draft_in_lobby
        # Post 55 messages
        for i in range(55):
            session.post(f"{API}/drafts/{sid}/chat", json={
                "player_token": a["player_token"], "text": f"m{i}"
            })
        st = session.get(f"{API}/drafts/{sid}/state").json()
        assert len(st["messages"]) <= 50
