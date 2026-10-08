"""My Cubes: saved cube lists are private to their owner."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

IMG = "data:image/jpeg;base64," + "A" * 200
CARDS = [{"id": f"c{i}", "name": f"Card {i}", "type_line": "Creature", "cmc": 2, "prices": {"usd": "1"}} for i in range(5)]


def user():
    email = f"cube_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "secret123", "name": "Cuber"}, timeout=20)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def owner():
    return user()


@pytest.fixture(scope="module")
def other():
    return user()


def test_needs_login():
    assert requests.get(f"{API}/cubes", timeout=20).status_code == 401


def test_create_list_get_update_delete(owner, other):
    cards = CARDS + [{"id": "abc", "name": "My Token", "image": IMG, "is_custom": True}]
    r = requests.post(f"{API}/cubes", json={"name": "Test Cube", "cubecobra_id": "abcd", "cards": cards}, headers=owner, timeout=20)
    assert r.status_code == 200, r.text
    cube = r.json()
    assert cube["card_count"] == 6 and cube["custom_count"] == 1
    assert all("prices" not in c for c in cube["cards"])
    assert any(c["id"] == "custom-abc" and c["type_line"] == "Token — Custom" for c in cube["cards"])

    listing = requests.get(f"{API}/cubes", headers=owner, timeout=20).json()["cubes"]
    assert [c["id"] for c in listing].count(cube["id"]) == 1
    assert "cards" not in listing[0]

    # Someone else can't see, change or delete it.
    assert requests.get(f"{API}/cubes/{cube['id']}", headers=other, timeout=20).status_code == 404
    assert requests.put(f"{API}/cubes/{cube['id']}", json={"name": "Mine now"}, headers=other, timeout=20).status_code == 404
    assert requests.delete(f"{API}/cubes/{cube['id']}", headers=other, timeout=20).status_code == 404
    assert cube["id"] not in [c["id"] for c in requests.get(f"{API}/cubes", headers=other, timeout=20).json()["cubes"]]

    r = requests.put(f"{API}/cubes/{cube['id']}", json={"name": "Renamed", "cards": CARDS[:3]}, headers=owner, timeout=20)
    assert r.status_code == 200 and r.json()["name"] == "Renamed" and r.json()["card_count"] == 3

    assert requests.delete(f"{API}/cubes/{cube['id']}", headers=owner, timeout=20).status_code == 200
    assert requests.get(f"{API}/cubes/{cube['id']}", headers=owner, timeout=20).status_code == 404


def test_rejects_empty_and_bad_custom_cards(owner):
    assert requests.post(f"{API}/cubes", json={"name": "Empty", "cards": []}, headers=owner, timeout=20).status_code == 400
    bad = CARDS + [{"id": "x", "name": "Bad", "image": "https://example.com/a.png", "is_custom": True}]
    assert requests.post(f"{API}/cubes", json={"name": "Bad", "cards": bad}, headers=owner, timeout=20).status_code == 400
