"""Private tables, join codes and the Drafting now list (/drafts/open "live")."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

CUBE = [{"id": f"c{i}", "name": f"Card {i}", "type_line": "Creature", "cmc": 2} for i in range(12)]


def make(private=False, name="CODE_TEST"):
    r = requests.post(f"{API}/drafts", json={
        "name": name, "num_players": 2, "num_seats": 2, "pick_cap": 2,
        "double_draft_after": 0, "private": private, "cube": CUBE,
    }, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


def test_join_code_shape_and_lookup():
    d = make()
    code = d["join_code"]
    assert len(code) == 5 and code.isalnum() and code.upper() == code
    assert not set(code) & set("01OIL")
    for c in (code, code.lower(), f"  {code} ", d["share_id"]):
        r = requests.get(f"{API}/drafts/code/{c.strip()}", timeout=20)
        assert r.status_code == 200 and r.json()["share_id"] == d["share_id"]
    assert requests.get(f"{API}/drafts/code/ZZZZZ9", timeout=20).status_code == 404


def test_private_tables_are_hidden_but_joinable():
    pub, priv = make(name="PUBLIC_T"), make(private=True, name="PRIVATE_T")
    listing = requests.get(f"{API}/drafts/open", timeout=20).json()
    ids = {d["share_id"] for d in listing["drafts"] + listing["live"]}
    assert pub["share_id"] in ids
    assert priv["share_id"] not in ids
    assert priv["private"] is True
    r = requests.get(f"{API}/drafts/code/{priv['join_code']}", timeout=20)
    assert r.status_code == 200


def test_started_public_draft_is_listed_live():
    d = make(name="LIVE_T")
    sid = d["share_id"]
    for n in ("A", "B"):
        assert requests.post(f"{API}/drafts/{sid}/claim", json={"name": n}, timeout=20).status_code == 200
    assert requests.post(f"{API}/drafts/{sid}/start", timeout=60).status_code == 200
    listing = requests.get(f"{API}/drafts/open", timeout=20).json()
    live = {x["share_id"]: x for x in listing["live"]}
    assert sid in live and live[sid]["status"] == "drafting"
    assert sid not in {x["share_id"] for x in listing["drafts"]}
