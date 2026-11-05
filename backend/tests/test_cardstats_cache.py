"""CubeCobra card stats: a timeout or server error is not cached as "card missing" (pure Python, no server)."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from draftbot import cardstats

mm = pytest.importorskip("mongomock_motor")


class _Resp:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text
        self.url = type("U", (), {"path": "/tool/card/x"})()


def _page(name, elo):
    return f'<script>window.reactProps = {{"card": {{"name": "{name}", "elo": {elo}, "scryfall_id": "s1"}}}};</script>'


def _run(db, replies, names=("Sol Ring",)):
    async def fake_get(self, url):
        r = replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    import httpx
    orig = httpx.AsyncClient.get
    httpx.AsyncClient.get = fake_get
    try:
        asyncio.run(cardstats.ensure_stats(db, list(names), budget_s=5))
    finally:
        httpx.AsyncClient.get = orig


def _doc(db):
    return asyncio.run(db.card_stats.find_one({"key": "sol ring"}, {"_id": 0}))


def test_timeout_and_500_are_not_cached():
    db = mm.AsyncMongoMockClient()["t"]
    _run(db, [TimeoutError("slow")])
    assert _doc(db) is None
    _run(db, [_Resp(503)])
    assert _doc(db) is None
    _run(db, [_Resp(200, _page("Sol Ring", 1800))])
    assert _doc(db)["elo"] == 1800 and not _doc(db)["missing"]


def test_refresh_failure_keeps_good_stats():
    db = mm.AsyncMongoMockClient()["t"]
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    asyncio.run(db.card_stats.insert_one({"key": "sol ring", "name": "Sol Ring", "elo": 1700, "fetched_at": old}))
    _run(db, [_Resp(500)])
    assert _doc(db)["elo"] == 1700
    _run(db, [_Resp(404)])
    doc = _doc(db)
    assert doc["elo"] == 1700 and not doc.get("missing")


def test_missing_card_is_retried_after_a_few_days():
    db = mm.AsyncMongoMockClient()["t"]
    _run(db, [_Resp(404)])
    assert _doc(db)["missing"] is True
    _run(db, [])            # fresh "missing": no request at all
    stale = (datetime.now(timezone.utc) - cardstats.MISSING_MAX_AGE - timedelta(hours=1)).isoformat()
    asyncio.run(db.card_stats.update_one({"key": "sol ring"}, {"$set": {"fetched_at": stale}}))
    _run(db, [_Resp(200, _page("Sol Ring", 1900))])
    assert _doc(db)["elo"] == 1900
