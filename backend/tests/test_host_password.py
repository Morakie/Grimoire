"""Host password: host controls come back in another browser only with the password, not by name alone."""
import os
import uuid

import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

CUBE = [{"id": str(uuid.uuid4()), "name": f"Test Card {i}", "mana_cost": "{1}", "cmc": 1, "type_line": "Artifact",
         "colors": [], "color_identity": []} for i in range(12)]


def _table(password=None, **extra):
    body = {"name": "TEST_hostpw", "num_players": 2, "num_seats": 2, "pick_cap": 3, "cube": CUBE, **extra}
    if password is not None:
        body["host_password"] = password
    r = requests.post(f"{API}/drafts", json=body, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "host_password_hash" not in d
    host = requests.post(f"{API}/drafts/{d['share_id']}/claim", json={"name": "Host", "host_token": d["host_token"]},
                         timeout=20).json()
    assert host["host_token"] == d["host_token"]
    return d, host


def _claim(sid, **body):
    return requests.post(f"{API}/drafts/{sid}/claim", json={"name": "Host", **body}, timeout=20)


def test_name_alone_gives_seat_but_not_host_controls():
    d, host = _table("hunter2")
    r = _claim(d["share_id"])
    assert r.status_code == 200
    out = r.json()
    assert out["player_id"] == host["player_id"] and "host_token" not in out
    assert out["host_password_required"] is True


def test_wrong_password_is_refused_and_right_one_restores_host():
    d, host = _table("hunter2")
    assert _claim(d["share_id"], host_password="nope").status_code == 403
    out = _claim(d["share_id"], host_password=" hunter2 ").json()
    assert out["host_token"] == d["host_token"]


def test_same_browser_keeps_host_without_password():
    d, host = _table("hunter2")
    out = _claim(d["share_id"], player_token=host["player_token"]).json()
    assert out["host_token"] == d["host_token"]


def test_no_password_means_host_stays_with_its_browser():
    d, _ = _table()
    out = _claim(d["share_id"]).json()
    assert "host_token" not in out and out["host_password_required"] is False
    assert _claim(d["share_id"], host_password="anything").status_code == 403


def test_host_can_set_and_remove_password():
    d, _ = _table()
    sid = d["share_id"]
    assert requests.post(f"{API}/drafts/{sid}/host-password", json={"host_token": "bad", "password": "x"},
                         timeout=20).status_code == 403
    r = requests.post(f"{API}/drafts/{sid}/host-password", json={"host_token": d["host_token"], "password": "pw1"}, timeout=20)
    assert r.status_code == 200 and r.json()["host_password_set"] is True
    assert requests.get(f"{API}/drafts/{sid}/state", timeout=20).json()["host_password_set"] is True
    assert _claim(sid, host_password="pw1").json()["host_token"] == d["host_token"]
    requests.post(f"{API}/drafts/{sid}/host-password", json={"host_token": d["host_token"], "password": ""}, timeout=20)
    assert "host_token" not in _claim(sid).json()


def test_other_players_never_get_host_controls():
    d, _ = _table("hunter2")
    guest = requests.post(f"{API}/drafts/{d['share_id']}/claim", json={"name": "Guest", "host_password": "hunter2"},
                          timeout=20).json()
    assert "host_token" not in guest


def test_mirror_table_needs_password_from_another_browser():
    body = {"name": "TEST_mirror_pw", "num_players": 1, "num_seats": 3, "pick_cap": 3, "cube": CUBE, "mirror": True,
            "seat_names": ["Me", "Ann", "Bo"], "my_seat": 0, "host_password": "pw"}
    d = requests.post(f"{API}/drafts", json=body, timeout=20).json()
    sid = d["share_id"]
    locked = requests.post(f"{API}/drafts/{sid}/claim", json={"name": "Me"}, timeout=20).json()
    assert locked.get("host_password_required") and "player_token" not in locked
    assert requests.post(f"{API}/drafts/{sid}/claim", json={"name": "Me", "host_password": "bad"}, timeout=20).status_code == 403
    ok = requests.post(f"{API}/drafts/{sid}/claim", json={"name": "Me", "host_password": "pw"}, timeout=20).json()
    assert ok["player_token"] == d["player"]["player_token"] and ok["host_token"] == d["host_token"]
