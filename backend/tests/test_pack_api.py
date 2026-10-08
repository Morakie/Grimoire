"""Pack drafts through the API: create, start, hidden packs and picks, bots, build deck."""
import os
import time
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

CUBE = [{"id": f"c{i}", "name": f"Card {i}", "type_line": "Creature", "cmc": 1 + i % 5,
         "mana_cost": "{%s}" % "WUBRG"[i % 5], "color_identity": ["WUBRG"[i % 5]]} for i in range(60)]


def create(**kw):
    body = {"name": "PACK_API", "num_players": 2, "num_bots": 1, "num_seats": 2, "mode": "packs",
            "pack_count": 3, "pack_size": 5, "cube": CUBE}
    body.update(kw)
    return requests.post(f"{API}/drafts", json=body, timeout=30)


def test_cube_too_small_is_rejected():
    r = create(pack_size=15)
    assert r.status_code == 400 and "needs 90" in r.json()["detail"]


def test_pack_draft_flow():
    d = create().json()
    sid = d["share_id"]
    assert d["mode"] == "packs" and d["pick_cap"] == 15
    me = requests.post(f"{API}/drafts/{sid}/claim", json={"name": "Human"}, timeout=20).json()
    assert requests.post(f"{API}/drafts/{sid}/start", timeout=60).status_code == 200
    hdr = {"X-Player-Token": me["player_token"]}

    # Without a token you see no pack contents and no picks.
    anon = requests.get(f"{API}/drafts/{sid}/state", timeout=20).json()
    assert "my" not in anon and anon["picks"] == []
    seat = me["seats"][0]
    # The other seat's player can't build from (or peek at) this seat's picks mid-draft.
    assert requests.get(f"{API}/drafts/{sid}/build", params={"seat": 1 - seat}, timeout=20).status_code == 403

    for _ in range(200):
        st = requests.get(f"{API}/drafts/{sid}/state", headers=hdr, timeout=20).json()
        if st["status"] == "complete":
            break
        mine = st["my"][str(seat)]
        if mine["pack"]:
            r = requests.post(f"{API}/drafts/{sid}/pick", json={"player_token": me["player_token"], "seat_index": seat,
                                                                "card_id": mine["pack"][0]}, timeout=20)
            assert r.status_code == 200, r.text
        else:
            time.sleep(0.5)
    final = requests.get(f"{API}/drafts/{sid}/state", timeout=20).json()
    assert final["status"] == "complete"
    assert len(final["picks"]) == 30                      # revealed at the end
    assert sum(1 for p in final["picks"] if p.get("bot")) == 15
    b = requests.get(f"{API}/drafts/{sid}/build", params={"seat": seat}, timeout=20)
    assert b.status_code == 200 and b.json()["main"]


def test_pick_from_wrong_pack_rejected():
    d = create().json()
    sid = d["share_id"]
    me = requests.post(f"{API}/drafts/{sid}/claim", json={"name": "Human"}, timeout=20).json()
    requests.post(f"{API}/drafts/{sid}/start", timeout=60)
    st = requests.get(f"{API}/drafts/{sid}/state", headers={"X-Player-Token": me["player_token"]}, timeout=20).json()
    mine = set(st["my"][str(me["seats"][0])]["pack"])
    other = next(c["id"] for c in CUBE if c["id"] not in mine)
    r = requests.post(f"{API}/drafts/{sid}/pick", json={"player_token": me["player_token"], "seat_index": me["seats"][0],
                                                        "card_id": other}, timeout=20)
    assert r.status_code == 409
