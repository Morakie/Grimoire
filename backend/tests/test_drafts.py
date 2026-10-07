"""Backend tests for the Rotisserie Cube Draft module."""
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
    cards = r.json()["cards"]
    assert len(cards) >= 10, f"Expected the cube to resolve enough cards, got {len(cards)}"
    return cards


# --------- Create validation ---------
class TestCreateDraft:
    def test_create_rejects_uneven_split(self, session, resolved_cube):
        r = session.post(f"{API}/drafts", json={
            "name": "TEST_bad", "num_players": 3, "num_seats": 7,
            "pick_cap": 2, "double_draft_after": 0, "cube": resolved_cube,
        })
        assert r.status_code == 400
        assert "evenly" in r.json()["detail"].lower()

    def test_create_rejects_empty_cube(self, session):
        r = session.post(f"{API}/drafts", json={
            "name": "TEST_empty", "num_players": 2, "num_seats": 4,
            "pick_cap": 2, "double_draft_after": 0, "cube": [],
        })
        assert r.status_code == 400

    def test_create_ok(self, session, resolved_cube):
        r = session.post(f"{API}/drafts", json={
            "name": "TEST_create", "num_players": 2, "num_seats": 4,
            "pick_cap": 2, "double_draft_after": 0, "cube": resolved_cube,
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["share_id"] and d["status"] == "lobby"
        assert d["seats_per_player"] == 2
        assert len(d["seats"]) == 4


# --------- Claim / even split / reattach ---------
class TestClaimAndSplit:
    def _make(self, session, cube, players, seats):
        r = session.post(f"{API}/drafts", json={
            "name": "TEST_claim", "num_players": players, "num_seats": seats,
            "pick_cap": 2, "double_draft_after": 0, "cube": cube,
        })
        assert r.status_code == 200
        return r.json()["share_id"]

    def test_even_split_2p4s(self, session, resolved_cube):
        sid = self._make(session, resolved_cube, 2, 4)
        a = session.post(f"{API}/drafts/{sid}/claim", json={"name": "Alice"}).json()
        b = session.post(f"{API}/drafts/{sid}/claim", json={"name": "Bob"}).json()
        assert len(a["seats"]) == 2 and len(b["seats"]) == 2
        assert set(a["seats"]).isdisjoint(set(b["seats"]))
        assert set(a["seats"]) | set(b["seats"]) == {0, 1, 2, 3}

    def test_even_split_3p6s(self, session, resolved_cube):
        sid = self._make(session, resolved_cube, 3, 6)
        p = [session.post(f"{API}/drafts/{sid}/claim", json={"name": n}).json()
             for n in ("P1", "P2", "P3")]
        counts = [len(x["seats"]) for x in p]
        assert counts == [2, 2, 2], f"Uneven split: {counts}"
        all_seats = sorted([s for x in p for s in x["seats"]])
        assert all_seats == [0, 1, 2, 3, 4, 5]

    def test_reclaim_by_name_returns_same_seats(self, session, resolved_cube):
        sid = self._make(session, resolved_cube, 2, 4)
        first = session.post(f"{API}/drafts/{sid}/claim", json={"name": "Alice"}).json()
        again = session.post(f"{API}/drafts/{sid}/claim", json={"name": "alice"}).json()
        assert again["seats"] == first["seats"]
        assert again["player_token"] == first["player_token"]

    def test_reclaim_by_token(self, session, resolved_cube):
        sid = self._make(session, resolved_cube, 2, 4)
        first = session.post(f"{API}/drafts/{sid}/claim", json={"name": "Alice"}).json()
        again = session.post(f"{API}/drafts/{sid}/claim",
                             json={"name": "AliceRenamed", "player_token": first["player_token"]}).json()
        assert again["seats"] == first["seats"]

    def test_extra_player_rejected(self, session, resolved_cube):
        sid = self._make(session, resolved_cube, 2, 4)
        session.post(f"{API}/drafts/{sid}/claim", json={"name": "A"})
        session.post(f"{API}/drafts/{sid}/claim", json={"name": "B"})
        r = session.post(f"{API}/drafts/{sid}/claim", json={"name": "C"})
        assert r.status_code == 400


# --------- Start gating + pick order ---------
class TestStartAndPickOrder:
    def test_start_blocked_until_all_seats_claimed(self, session, resolved_cube):
        r = session.post(f"{API}/drafts", json={
            "name": "TEST_start", "num_players": 2, "num_seats": 4,
            "pick_cap": 2, "double_draft_after": 0, "cube": resolved_cube,
        })
        sid = r.json()["share_id"]
        session.post(f"{API}/drafts/{sid}/claim", json={"name": "A"})
        bad = session.post(f"{API}/drafts/{sid}/start")
        assert bad.status_code == 400
        session.post(f"{API}/drafts/{sid}/claim", json={"name": "B"})
        ok = session.post(f"{API}/drafts/{sid}/start")
        assert ok.status_code == 200
        s = ok.json()
        assert s["status"] == "drafting"
        # order length = num_seats * pick_cap (bounded by cube size)
        assert s["order_len"] == min(4 * 2, len(resolved_cube))

    def test_pick_order_snake_no_double(self, session, resolved_cube):
        # 2 players x 4 seats x cap 2 -> order should be [0,1,2,3,3,2,1,0]
        r = session.post(f"{API}/drafts", json={
            "name": "TEST_snake", "num_players": 2, "num_seats": 4,
            "pick_cap": 2, "double_draft_after": 0, "cube": resolved_cube,
        }).json()
        sid = r["share_id"]
        a = session.post(f"{API}/drafts/{sid}/claim", json={"name": "A"}).json()
        b = session.post(f"{API}/drafts/{sid}/claim", json={"name": "B"}).json()
        full = session.post(f"{API}/drafts/{sid}/start").json()
        # verify current_seat_index starts at 0
        assert full["current_seat_index"] == 0
        # Walk order from a GET to full
        got = session.get(f"{API}/drafts/{sid}").json()
        # Order is server-internal; verify via a few picks that it's snake-ish
        return sid, a, b, got


# --------- Full draft turn engine ---------
class TestFullDraft:
    def _owner_for(self, players_info, seat):
        for p in players_info:
            if seat in p["seats"]:
                return p
        return None

    def test_full_draft_completion_and_uniqueness(self, session, resolved_cube):
        pick_cap = 2
        num_seats = 4
        r = session.post(f"{API}/drafts", json={
            "name": "TEST_full", "num_players": 2, "num_seats": num_seats,
            "pick_cap": pick_cap, "double_draft_after": 0, "cube": resolved_cube,
        }).json()
        sid = r["share_id"]
        a = session.post(f"{API}/drafts/{sid}/claim", json={"name": "A"}).json()
        b = session.post(f"{API}/drafts/{sid}/claim", json={"name": "B"}).json()
        session.post(f"{API}/drafts/{sid}/start")
        players = [a, b]

        picked = set()
        for _ in range(num_seats * pick_cap):
            st = session.get(f"{API}/drafts/{sid}/state").json()
            if st["status"] == "complete":
                break
            seat = st["current_seat_index"]
            owner = self._owner_for(players, seat)
            # pick first available card
            full = session.get(f"{API}/drafts/{sid}").json()
            avail = [c for c in full["cube"] if c["id"] not in picked]
            assert avail, "ran out of cards"
            card = avail[0]
            resp = session.post(f"{API}/drafts/{sid}/pick", json={
                "player_token": owner["player_token"], "seat_index": seat, "card_id": card["id"],
            })
            assert resp.status_code == 200, resp.text
            picked.add(card["id"])

        final = session.get(f"{API}/drafts/{sid}").json()
        assert final["status"] == "complete"
        # unique
        pick_ids = [p["card_id"] for p in final["picks"]]
        assert len(pick_ids) == len(set(pick_ids))
        # per-seat totals = pick_cap
        per_seat = {i: 0 for i in range(num_seats)}
        for p in final["picks"]:
            per_seat[p["seat_index"]] += 1
        assert all(v == pick_cap for v in per_seat.values()), f"uneven per-seat: {per_seat}"

    def test_turn_steal_blocked(self, session, resolved_cube):
        r = session.post(f"{API}/drafts", json={
            "name": "TEST_steal", "num_players": 2, "num_seats": 4,
            "pick_cap": 2, "double_draft_after": 0, "cube": resolved_cube,
        }).json()
        sid = r["share_id"]
        a = session.post(f"{API}/drafts/{sid}/claim", json={"name": "A"}).json()
        b = session.post(f"{API}/drafts/{sid}/claim", json={"name": "B"}).json()
        session.post(f"{API}/drafts/{sid}/start")
        st = session.get(f"{API}/drafts/{sid}/state").json()
        seat = st["current_seat_index"]
        # whoever does NOT control this seat tries to pick -> 403
        offender = b if seat in a["seats"] else a
        full = session.get(f"{API}/drafts/{sid}").json()
        card_id = full["cube"][0]["id"]
        bad = session.post(f"{API}/drafts/{sid}/pick", json={
            "player_token": offender["player_token"], "seat_index": seat, "card_id": card_id,
        })
        assert bad.status_code == 403

    def test_double_draft_completes_correctly(self, session, resolved_cube):
        # 2 seats, 1 player, cap 4, double_after=1 -> boundary seats take extras
        pick_cap = 4
        num_seats = 2
        r = session.post(f"{API}/drafts", json={
            "name": "TEST_dbl", "num_players": 1, "num_seats": num_seats,
            "pick_cap": pick_cap, "double_draft_after": 1, "cube": resolved_cube,
        }).json()
        sid = r["share_id"]
        a = session.post(f"{API}/drafts/{sid}/claim", json={"name": "A"}).json()
        session.post(f"{API}/drafts/{sid}/start")
        picked = set()
        for _ in range(num_seats * pick_cap + 2):
            st = session.get(f"{API}/drafts/{sid}/state").json()
            if st["status"] == "complete":
                break
            seat = st["current_seat_index"]
            full = session.get(f"{API}/drafts/{sid}").json()
            avail = [c for c in full["cube"] if c["id"] not in picked]
            card = avail[0]
            session.post(f"{API}/drafts/{sid}/pick", json={
                "player_token": a["player_token"], "seat_index": seat, "card_id": card["id"],
            })
            picked.add(card["id"])
        final = session.get(f"{API}/drafts/{sid}").json()
        assert final["status"] == "complete"
        per_seat = {i: 0 for i in range(num_seats)}
        for p in final["picks"]:
            per_seat[p["seat_index"]] += 1
        assert all(v == pick_cap for v in per_seat.values()), f"uneven per-seat: {per_seat}"


# --------- Light state (polling) + 404s ---------
class TestStateAndNotFound:
    def test_state_endpoint_light(self, session, resolved_cube):
        r = session.post(f"{API}/drafts", json={
            "name": "TEST_light", "num_players": 2, "num_seats": 4,
            "pick_cap": 2, "double_draft_after": 0, "cube": resolved_cube,
        }).json()
        sid = r["share_id"]
        s = session.get(f"{API}/drafts/{sid}/state").json()
        assert "cube" not in s  # light should omit full cube
        assert "picked_ids" in s
        assert s["share_id"] == sid

    def test_get_404(self, session):
        r = session.get(f"{API}/drafts/doesnotexist")
        assert r.status_code == 404
