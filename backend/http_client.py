"""One shared HTTP client for outside services (Scryfall, Commander Spellbook).

Opening a new client per request means a fresh TLS handshake every time (a few hundred ms on a
small server). A shared client keeps connections open and reuses them, so card search, autocomplete
and lookups only pay for the request itself.
"""
from contextlib import asynccontextmanager
from typing import Optional

import httpx

HEADERS = {"User-Agent": "GrimoireDeckBuilder/1.0", "Accept": "application/json"}

_client: Optional[httpx.AsyncClient] = None


def shared() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            headers=HEADERS,
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_connections=40, max_keepalive_connections=20, keepalive_expiry=60.0),
        )
    return _client


@asynccontextmanager
async def client():
    """`async with client() as hc:` works like `async with httpx.AsyncClient(...)`, minus the reconnect."""
    yield shared()


async def close() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
