"""Cube Analysis / Bot Brain pools built from a saved (private) cube stay with their owner."""
import os
import uuid

import requests

API = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/") + "/api"


def _user():
    email = f"labpriv_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "secret123", "name": "Lab"}, timeout=20)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _cards():
    tag = uuid.uuid4().hex[:6]
    return [{"id": str(uuid.uuid4()), "name": f"Private {tag} {i}", "mana_cost": "{1}", "cmc": 1, "type_line": "Artifact",
             "colors": [], "color_identity": []} for i in range(12)]


def test_private_pool_is_owner_only():
    owner, other = _user(), _user()
    label = f"Secret cube {uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/lab/source", json={"cards": _cards(), "label": label, "private": True}, headers=owner, timeout=120)
    assert r.status_code == 200, r.text
    key = r.json()["source"]
    assert key.startswith("mine:")

    def listed(headers=None):
        return any(p["label"] == label for p in requests.get(f"{API}/lab/pools", headers=headers or {}, timeout=20).json()["pools"])
    assert listed(owner) and not listed() and not listed(other)
    for headers in ({}, other):
        assert requests.get(f"{API}/lab/pool-export", params={"key": key}, headers=headers, timeout=20).status_code == 404
        assert requests.post(f"{API}/lab/source", json={"pool": key}, headers=headers, timeout=20).status_code == 404
    assert requests.get(f"{API}/lab/pool-export", params={"key": key}, headers=owner, timeout=20).status_code == 200
    assert requests.post(f"{API}/lab/source", json={"pool": key}, headers=owner, timeout=20).status_code == 200


def test_private_pool_needs_sign_in():
    r = requests.post(f"{API}/lab/source", json={"cards": _cards(), "label": "x", "private": True}, timeout=60)
    assert r.status_code == 401


def test_public_pools_still_shared():
    label = f"Public cube {uuid.uuid4().hex[:6]}"
    r = requests.post(f"{API}/lab/source", json={"cards": _cards(), "label": label}, timeout=120)
    assert r.status_code == 200, r.text
    assert any(p["label"] == label for p in requests.get(f"{API}/lab/pools", timeout=20).json()["pools"])
