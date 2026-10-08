import sys

print(f"grimoire python {sys.version}", file=sys.stderr, flush=True)

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Header
from starlette.concurrency import run_in_threadpool
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import asyncio
import random
import bcrypt
import jwt
import httpx
import csv
import certifi
from pathlib import Path
from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta

from draftbot import BotContext, build_card_index, choose_pick, combos_from_dicts, fetch_combos, random_persona, bot_names
from draftbot.combos import attach_combos
from draftbot.cardstats import draft_stats, ensure_stats
from draftbot.personas import Persona
from draftbot.engine import suggest_picks
from draftbot.deckbuild import suggest_deck
from draftbot.packbot import choose_from_pack, rank_pack
import packdraft as pd
import vrd
from draftbot.simulate import run_draft, summarise
import commander as cmdr

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')


def _require_env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable '{key}'. "
            f"Set it in your Render service (or local backend/.env). "
            f"Required keys: MONGO_URL, DB_NAME, JWT_SECRET. "
            f"Optional: CORS_ORIGINS, ADMIN_EMAIL, ADMIN_PASSWORD."
        )
    return value


mongo_url = _require_env('MONGO_URL')
mongo_kwargs = {}
if mongo_url.startswith("mongodb+srv://"):
    mongo_kwargs["tlsCAFile"] = certifi.where()
client = AsyncIOMotorClient(mongo_url, **mongo_kwargs)
db = client[_require_env('DB_NAME')]

JWT_ALGORITHM = "HS256"
JWT_SECRET = _require_env("JWT_SECRET")

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ----------------------- Auth helpers -----------------------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

def create_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def public_user(user: dict) -> dict:
    return {"id": user["id"], "email": user["email"], "name": user.get("name", "")}

async def get_current_user(request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"id": payload["sub"]})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ----------------------- Models -----------------------

class RegisterInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(default="", max_length=60)

class LoginInput(BaseModel):
    email: EmailStr
    password: str

class DeckCard(BaseModel):
    id: str
    oracle_id: Optional[str] = ""
    name: str
    mana_cost: Optional[str] = ""
    cmc: float = 0
    type_line: Optional[str] = ""
    oracle_text: Optional[str] = ""
    colors: List[str] = []
    color_identity: List[str] = []
    rarity: Optional[str] = ""
    set: Optional[str] = ""
    set_name: Optional[str] = ""
    collector_number: Optional[str] = ""
    image: Optional[str] = None
    art_crop: Optional[str] = None
    elo: Optional[int] = None
    quantity: int = 1
    group_overrides: Dict[str, str] = {}

class DeckInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    format: str = "standard"
    description: str = Field(default="", max_length=20000)
    mainboard: List[DeckCard] = []
    sideboard: List[DeckCard] = []
    commander: List[DeckCard] = []

# ----------------------- Auth routes -----------------------

@api_router.post("/auth/register")
async def register(data: RegisterInput):
    email = data.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    user = {
        "id": str(uuid.uuid4()),
        "email": email,
        "password_hash": hash_password(data.password),
        "name": data.name or email.split("@")[0],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user)
    token = create_token(user["id"], user["email"])
    return {"token": token, "user": public_user(user)}

@api_router.post("/auth/login")
async def login(data: LoginInput):
    email = data.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(user["id"], user["email"])
    return {"token": token, "user": public_user(user)}

@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)

# ----------------------- Scryfall proxy -----------------------

SCRYFALL = "https://api.scryfall.com"
HEADERS = {"User-Agent": "GrimoireDeckBuilder/1.0", "Accept": "application/json"}

# CubeCobra ELO rankings (name -> elo) used as the default draft sort.
ELO: Dict[str, int] = {}
_elo_path = ROOT_DIR / "data" / "card_elo.csv"
if _elo_path.exists():
    with open(_elo_path, newline="", encoding="utf-8") as _f:
        for _row in csv.DictReader(_f):
            try:
                ELO[_row["Name"].strip().lower()] = int(float(_row["Elo"]))
            except (KeyError, ValueError, TypeError):
                continue

def elo_for(name: str):
    if not name:
        return None
    return ELO.get(name.strip().lower()) or ELO.get(name.split("//")[0].strip().lower())

def map_card(c: Dict[str, Any]) -> Dict[str, Any]:
    image = art = None
    if c.get("image_uris"):
        image = c["image_uris"].get("normal")
        art = c["image_uris"].get("art_crop")
    elif c.get("card_faces"):
        face = c["card_faces"][0]
        if face.get("image_uris"):
            image = face["image_uris"].get("normal")
            art = face["image_uris"].get("art_crop")
    mana_cost = c.get("mana_cost")
    if not mana_cost and c.get("card_faces"):
        mana_cost = c["card_faces"][0].get("mana_cost", "")
    return {
        "id": c["id"],
        "oracle_id": c.get("oracle_id", ""),
        "name": c["name"],
        "mana_cost": mana_cost or "",
        "cmc": c.get("cmc", 0),
        "type_line": c.get("type_line", ""),
        "oracle_text": c.get("oracle_text", "") or (c.get("card_faces", [{}])[0].get("oracle_text", "") if c.get("card_faces") else ""),
        "colors": c.get("colors") or c.get("color_identity") or [],
        "color_identity": c.get("color_identity", []),
        "rarity": c.get("rarity", ""),
        "set": c.get("set", ""),
        "set_name": c.get("set_name", ""),
        "collector_number": c.get("collector_number", ""),
        "image": image,
        "art_crop": art,
        "elo": elo_for(c.get("name", "")),
        "prices": c.get("prices", {}),
    }

@api_router.get("/cards/search")
async def search_cards(
    q: str = "",
    colors: str = "",
    type: str = "",
    set: str = "",
    cmc: str = "",
    page: int = 1,
):
    parts = []
    if q.strip():
        parts.append(q.strip())
    if colors.strip():
        parts.append(f"c>={colors.strip()}")
    if type.strip():
        parts.append(f"t:{type.strip()}")
    if set.strip():
        parts.append(f"s:{set.strip()}")
    if cmc.strip():
        parts.append(f"cmc={cmc.strip()}" if cmc.strip().isdigit() else f"cmc{cmc.strip()}")
    query = " ".join(parts).strip()
    if not query:
        raise HTTPException(status_code=400, detail="Empty search")
    async with httpx.AsyncClient(timeout=15.0, headers=HEADERS) as hc:
        r = await hc.get(f"{SCRYFALL}/cards/search", params={"q": query, "page": page, "unique": "cards"})
        if r.status_code == 404:
            return {"cards": [], "has_more": False, "total": 0}
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail="Scryfall error")
        data = r.json()
    return {
        "cards": [map_card(c) for c in data.get("data", [])],
        "has_more": data.get("has_more", False),
        "total": data.get("total_cards", 0),
    }

@api_router.get("/cards/printings")
async def card_printings(name: str):
    async with httpx.AsyncClient(timeout=15.0, headers=HEADERS) as hc:
        r = await hc.get(f"{SCRYFALL}/cards/search", params={"q": f'!"{name}"', "unique": "prints", "order": "released", "dir": "asc"})
        if r.status_code != 200:
            return {"printings": []}
        data = r.json()
    return {"printings": [map_card(c) for c in data.get("data", [])]}

class CollectionEntry(BaseModel):
    key: str
    name: str
    set: Optional[str] = None
    collector_number: Optional[str] = None

class CollectionInput(BaseModel):
    names: List[str] = []
    # Richer import path: each entry may pin an exact printing (set + collector number).
    entries: List[CollectionEntry] = []

def _name_keys(c: Dict[str, Any]) -> List[str]:
    """Every name a card can be looked up by: full name plus each face name."""
    keys = [c.get("name", "")]
    keys += [f.get("name", "") for f in c.get("card_faces") or []]
    return [k.strip().lower() for k in keys if k]

async def _scryfall_post(hc: httpx.AsyncClient, path: str, body: dict) -> httpx.Response:
    """POST to Scryfall, retrying briefly when it is busy (429 / 5xx). Raises a 502 if it still fails,
    so a Scryfall hiccup is reported instead of silently dropping cards."""
    for attempt in range(3):
        r = await hc.post(f"{SCRYFALL}{path}", json=body)
        if r.status_code == 200:
            return r
        if r.status_code not in (429, 500, 502, 503, 504):
            break
        await asyncio.sleep(1.0 * (attempt + 1))
    logger.warning("Scryfall %s failed: %s", path, r.status_code)
    raise HTTPException(status_code=502, detail="Scryfall is busy, please try again in a moment")


async def _collection_lookup(hc: httpx.AsyncClient, identifiers: List[dict]) -> List[dict]:
    out = []
    for i in range(0, len(identifiers), 75):
        if i:
            await asyncio.sleep(0.1)
        r = await _scryfall_post(hc, "/cards/collection", {"identifiers": identifiers[i:i + 75]})
        out.extend(r.json().get("data", []))
    return out

_OLDEST_CACHE: Dict[str, dict] = {}   # oracle_id -> oldest paper printing (raw Scryfall card)


async def _prefer_oldest(hc: httpx.AsyncClient, cards: List[dict]) -> List[dict]:
    """Swap each card for its first paper printing (original art), when Scryfall has one.
    Used wherever a list names cards without pinning a printing."""
    wanted = list(dict.fromkeys(c["oracle_id"] for c in cards if c.get("oracle_id") and c["oracle_id"] not in _OLDEST_CACHE))
    for i in range(0, len(wanted), 20):
        await asyncio.sleep(0.1)
        query = "(" + " or ".join(f"oracleid:{o}" for o in wanted[i:i + 20]) + ") not:reprint game:paper"
        url, params, best = f"{SCRYFALL}/cards/search", {"q": query, "unique": "prints", "order": "released", "dir": "asc"}, {}
        for _ in range(4):   # at most a few pages
            r = await hc.get(url, params=params)
            if r.status_code != 200:
                break
            payload = r.json()
            for c in payload.get("data", []):
                o = c.get("oracle_id")
                cur = best.get(o)
                # earliest release wins; a regular printing beats a promo from the same moment
                if cur is None or (cur.get("promo") and not c.get("promo") and c.get("released_at") == cur.get("released_at")):
                    best[o] = c
            if not payload.get("has_more"):
                break
            url, params = payload["next_page"], None
            await asyncio.sleep(0.1)
        for o in wanted[i:i + 20]:
            _OLDEST_CACHE[o] = best.get(o) or {}
    if len(_OLDEST_CACHE) > 20000:
        _OLDEST_CACHE.clear()
    return [(_OLDEST_CACHE.get(c.get("oracle_id")) or c) for c in cards]


async def _resolve_entries(entries: List[CollectionEntry], oldest: bool = True) -> Dict[str, Any]:
    """Resolve import entries in three passes: exact printing, exact name, fuzzy name."""
    entries = entries[:400]
    resolved: Dict[str, dict] = {}
    async with httpx.AsyncClient(timeout=20.0, headers=HEADERS) as hc:
        # Pass 1: exact printing for entries that specify set + collector number.
        pinned = [e for e in entries if e.set and e.collector_number]
        if pinned:
            ids = [{"set": e.set.lower(), "collector_number": e.collector_number} for e in pinned]
            by_print = {(c["set"].lower(), c["collector_number"]): c for c in await _collection_lookup(hc, ids)}
            for e in pinned:
                c = by_print.get((e.set.lower(), e.collector_number))
                if c:
                    resolved[e.key] = c

        # Pass 2: exact name (front face is enough for double-faced cards).
        pending = [e for e in entries if e.key not in resolved]
        if pending:
            names = list(dict.fromkeys(e.name for e in pending))
            by_name: Dict[str, dict] = {}
            for c in await _collection_lookup(hc, [{"name": n} for n in names]):
                for k in _name_keys(c):
                    by_name.setdefault(k, c)
            for e in pending:
                c = by_name.get(e.name.strip().lower())
                if c:
                    resolved[e.key] = c

        # Pass 3: fuzzy name for anything still missing (typos, odd punctuation).
        pending = [e for e in entries if e.key not in resolved][:25]
        for e in pending:
            await asyncio.sleep(0.1)
            r = await hc.get(f"{SCRYFALL}/cards/named", params={"fuzzy": e.name})
            if r.status_code == 200:
                resolved[e.key] = r.json()

        # Entries that didn't pin a printing get the original art.
        if oldest:
            pinned_keys = {e.key for e in entries if e.set and e.collector_number and e.key in resolved}
            loose = [k for k in resolved if k not in pinned_keys]
            if loose:
                try:
                    swapped = await _prefer_oldest(hc, [resolved[k] for k in loose])
                    resolved.update(zip(loose, swapped))
                except httpx.HTTPError as exc:   # keep Scryfall's default printings
                    logger.warning("Oldest-printing lookup failed: %s", exc)

    return {
        "resolved": {k: map_card(c) for k, c in resolved.items()},
        "not_found": [e.name for e in entries if e.key not in resolved],
    }

@api_router.post("/cards/collection")
async def card_collection(data: CollectionInput):
    if data.entries:
        return await _resolve_entries(data.entries)
    return await _collection_by_names(data.names)

async def _collection_by_names(names: List[str]) -> Dict[str, Any]:
    """Resolve card names (e.g. a cube list), using each card's original printing. Misses get a
    second chance through the front face and fuzzy matching (e.g. split cards like "Life // Death")."""
    names = [n for n in names if n and n.strip()][:800]
    raw = []
    missed = []
    async with httpx.AsyncClient(timeout=20.0, headers=HEADERS) as hc:
        for i in range(0, len(names), 75):
            if i:
                await asyncio.sleep(0.1)
            r = await _scryfall_post(hc, "/cards/collection", {"identifiers": [{"name": n} for n in names[i:i + 75]]})
            payload = r.json()
            raw.extend(payload.get("data", []))
            missed.extend(nf["name"] for nf in payload.get("not_found", []) if nf.get("name"))
        try:
            raw = await _prefer_oldest(hc, raw)
        except httpx.HTTPError as exc:   # keep Scryfall's default printings
            logger.warning("Oldest-printing lookup failed: %s", exc)
    found = [map_card(c) for c in raw]
    if missed:
        retry = await _resolve_entries([CollectionEntry(key=str(i), name=n.split("//")[0].strip()) for i, n in enumerate(missed)])
        found.extend(retry["resolved"].values())
        missed = [missed[int(k)] for k in range(len(missed)) if str(k) not in retry["resolved"]]
    return {"cards": found, "not_found": missed}

class ExtrasInput(BaseModel):
    ids: List[str] = Field(default=[], max_length=400)


_EXTRAS_CACHE: Dict[str, tuple] = {}   # card id -> (fetched at, prices, token ids)
_TOKEN_CACHE: Dict[str, dict] = {}     # token id -> mapped token card
_EXTRAS_TTL = 6 * 3600


@api_router.post("/cards/extras")
async def card_extras(data: ExtrasInput):
    """Current prices for the given Scryfall card ids, and the tokens those cards make.
    Prices change daily, so they come from Scryfall rather than the saved deck."""
    ids = list(dict.fromkeys(i for i in data.ids if i))
    now = datetime.now(timezone.utc).timestamp()
    stale = [i for i in ids if i not in _EXTRAS_CACHE or now - _EXTRAS_CACHE[i][0] > _EXTRAS_TTL]
    async with httpx.AsyncClient(timeout=20.0, headers=HEADERS) as hc:
        if stale:
            printings = await _collection_lookup(hc, [{"id": i} for i in stale])
            # Price each card by Scryfall's default (usually current, in-print) printing: decks default
            # to original art, and an Alpha or promo price says little about what the deck costs.
            await asyncio.sleep(0.1)
            names = list(dict.fromkeys(c["name"] for c in printings))
            default_price = {}
            for c in await _collection_lookup(hc, [{"name": n} for n in names]):
                default_price[c["name"]] = c.get("prices") or {}
            for c in printings:
                tokens = [p["id"] for p in c.get("all_parts") or []
                          if p.get("component") == "token" and p.get("id") != c["id"]]
                own = c.get("prices") or {}
                pr = default_price.get(c["name"]) or own
                _EXTRAS_CACHE[c["id"]] = (now, {"usd": pr.get("usd") or own.get("usd"), "usd_foil": pr.get("usd_foil") or own.get("usd_foil"),
                                               "tix": pr.get("tix") or own.get("tix")}, tokens)
        token_ids = list(dict.fromkeys(t for i in ids if i in _EXTRAS_CACHE for t in _EXTRAS_CACHE[i][2]))
        missing = [t for t in token_ids if t not in _TOKEN_CACHE]
        if missing:
            await asyncio.sleep(0.1)
            for t in await _collection_lookup(hc, [{"id": t} for t in missing]):
                _TOKEN_CACHE[t["id"]] = map_card(t)
    if len(_EXTRAS_CACHE) > 20000:
        _EXTRAS_CACHE.clear()
    if len(_TOKEN_CACHE) > 5000:
        _TOKEN_CACHE.clear()
    # The same token often exists in several printings: show each token name once.
    tokens, seen = [], set()
    for t in token_ids:
        tok = _TOKEN_CACHE.get(t)
        if not tok:
            continue
        key = (tok["name"], tok.get("oracle_text", ""), tok.get("type_line", ""))
        if key in seen:
            continue
        seen.add(key)
        makers = [i for i in ids if i in _EXTRAS_CACHE and t in _EXTRAS_CACHE[i][2]]
        tokens.append({**{k: tok[k] for k in ("id", "name", "type_line", "oracle_text", "image", "colors")}, "made_by": makers})
    return {
        "prices": {i: _EXTRAS_CACHE[i][1] for i in ids if i in _EXTRAS_CACHE},
        "tokens": tokens,
    }

BASIC_NAMES = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest", "C": "Wastes"}
_BASICS_CACHE: Dict[str, dict] = {}


@api_router.get("/cards/basics")
async def basic_lands():
    """One card per basic land type (original printing), keyed by colour: W U B R G and C (Wastes)."""
    if len(_BASICS_CACHE) < len(BASIC_NAMES):
        found = (await _collection_by_names(list(BASIC_NAMES.values())))["cards"]
        by_name = {c["name"]: c for c in found}
        for col, name in BASIC_NAMES.items():
            if name in by_name:
                _BASICS_CACHE[col] = by_name[name]
    return {"basics": _BASICS_CACHE}

@api_router.get("/cards/autocomplete")
async def card_autocomplete(q: str = ""):
    if len(q.strip()) < 2:
        return {"suggestions": []}
    async with httpx.AsyncClient(timeout=10.0, headers=HEADERS) as hc:
        r = await hc.get(f"{SCRYFALL}/cards/autocomplete", params={"q": q.strip()})
        if r.status_code != 200:
            return {"suggestions": []}
        return {"suggestions": r.json().get("data", [])[:12]}

# ----------------------- Deck helpers -----------------------

def deck_to_public(d: dict, owner_name: str = "") -> dict:
    return {
        "id": d["id"],
        "name": d["name"],
        "format": d.get("format", "standard"),
        "description": d.get("description", ""),
        "mainboard": d.get("mainboard", []),
        "sideboard": d.get("sideboard", []),
        "commander": d.get("commander", []),
        "share_id": d.get("share_id"),
        "user_id": d.get("user_id"),
        "owner_name": owner_name,
        "created_at": d.get("created_at"),
        "updated_at": d.get("updated_at"),
    }

async def _get_owned_deck(deck_id: str, user: dict) -> dict:
    deck = await db.decks.find_one({"id": deck_id})
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    if deck["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not your deck")
    return deck

# ----------------------- Deck routes -----------------------

@api_router.post("/decks")
async def create_deck(data: DeckInput, user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc).isoformat()
    deck = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "share_id": str(uuid.uuid4())[:8],
        "name": data.name,
        "format": data.format,
        "description": data.description,
        "mainboard": [c.model_dump() for c in data.mainboard],
        "sideboard": [c.model_dump() for c in data.sideboard],
        "commander": [c.model_dump() for c in data.commander],
        "created_at": now,
        "updated_at": now,
    }
    await db.decks.insert_one(deck)
    return deck_to_public(deck, user.get("name", ""))

@api_router.get("/decks")
async def list_decks(user: dict = Depends(get_current_user)):
    decks = await db.decks.find({"user_id": user["id"]}).sort("updated_at", -1).to_list(500)
    return [deck_to_public(d, user.get("name", "")) for d in decks]

@api_router.get("/decks/{deck_id}")
async def get_deck(deck_id: str, user: dict = Depends(get_current_user)):
    deck = await _get_owned_deck(deck_id, user)
    return deck_to_public(deck, user.get("name", ""))

@api_router.put("/decks/{deck_id}")
async def update_deck(deck_id: str, data: DeckInput, user: dict = Depends(get_current_user)):
    await _get_owned_deck(deck_id, user)
    update = {
        "name": data.name,
        "format": data.format,
        "description": data.description,
        "mainboard": [c.model_dump() for c in data.mainboard],
        "sideboard": [c.model_dump() for c in data.sideboard],
        "commander": [c.model_dump() for c in data.commander],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.decks.update_one({"id": deck_id}, {"$set": update})
    deck = await db.decks.find_one({"id": deck_id})
    return deck_to_public(deck, user.get("name", ""))

@api_router.delete("/decks/{deck_id}")
async def delete_deck(deck_id: str, user: dict = Depends(get_current_user)):
    await _get_owned_deck(deck_id, user)
    await db.decks.delete_one({"id": deck_id})
    return {"ok": True}

@api_router.post("/decks/{deck_id}/clone")
async def clone_deck(deck_id: str, user: dict = Depends(get_current_user)):
    deck = await db.decks.find_one({"id": deck_id})
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    now = datetime.now(timezone.utc).isoformat()
    clone = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "share_id": str(uuid.uuid4())[:8],
        "name": f"{deck['name']} (Copy)",
        "format": deck.get("format", "standard"),
        "description": deck.get("description", ""),
        "mainboard": deck.get("mainboard", []),
        "sideboard": deck.get("sideboard", []),
        "commander": deck.get("commander", []),
        "created_at": now,
        "updated_at": now,
    }
    await db.decks.insert_one(clone)
    return deck_to_public(clone, user.get("name", ""))

@api_router.get("/decks/public/{share_id}")
async def public_deck(share_id: str):
    deck = await db.decks.find_one({"share_id": share_id})
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    owner = await db.users.find_one({"id": deck["user_id"]})
    return deck_to_public(deck, owner.get("name", "") if owner else "")

# ----------------------- Commander checks -----------------------

class CommanderCheckInput(BaseModel):
    commander: List[DeckCard] = Field(default=[], max_length=4)
    mainboard: List[DeckCard] = Field(default=[], max_length=250)

@api_router.post("/commander/check")
async def commander_check(data: CommanderCheckInput):
    """Legality and bracket estimate for a Commander deck (no login needed, nothing is stored)."""
    commanders = [c.model_dump() for c in data.commander]
    cards = [c.model_dump() for c in data.mainboard]
    ref, combos = await asyncio.gather(
        cmdr.fetch_reference(),
        cmdr.fetch_two_card_combos([c["name"] for c in commanders + cards]),
    )
    return cmdr.evaluate(commanders, cards, ref["game_changers"], ref["banned"], combos or [],
                         reference_ok=bool(ref.get("ok")), combos_ok=combos is not None)

@api_router.get("/")
async def root():
    return {"message": "Grimoire API"}

@api_router.get("/health")
async def health():
    return {"status": "ok"}

# ===================== My Cubes (saved cube lists) =====================

CUBE_CARD_KEYS = ("id", "oracle_id", "name", "mana_cost", "cmc", "type_line", "oracle_text", "colors",
                  "color_identity", "rarity", "set", "set_name", "collector_number", "image", "art_crop", "elo", "is_custom")
MAX_CUBE_CARDS = 1200


class CubeInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    cubecobra_id: Optional[str] = Field(default=None, max_length=200)   # set when the list came from CubeCobra
    cards: List[dict] = Field(default=[], max_length=MAX_CUBE_CARDS)


class CubeUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    cubecobra_id: Optional[str] = Field(default=None, max_length=200)
    cards: Optional[List[dict]] = Field(default=None, max_length=MAX_CUBE_CARDS)


def _cube_cards(cards: List[dict]) -> List[dict]:
    """Keep only the card fields a draft needs (no prices etc.) and validate custom cards."""
    if not cards:
        raise HTTPException(status_code=400, detail="A cube needs at least one card")
    cleaned = _clean_custom_cards([c for c in cards if isinstance(c, dict) and c.get("id") and c.get("name")])
    return [{k: c[k] for k in CUBE_CARD_KEYS if k in c} for c in cleaned]


def cube_summary(c: dict) -> dict:
    cards = c.get("cards", [])
    art = next((x.get("art_crop") for x in cards if x.get("art_crop") and not x.get("is_custom")), None)
    return {
        "id": c["id"], "name": c["name"], "cubecobra_id": c.get("cubecobra_id"),
        "card_count": len(cards), "custom_count": sum(1 for x in cards if x.get("is_custom")),
        "art": art, "created_at": c["created_at"], "updated_at": c["updated_at"],
    }


async def _owned_cube(cube_id: str, user: dict) -> dict:
    c = await db.cubes.find_one({"id": cube_id}, {"_id": 0})
    if not c or c["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Cube not found")
    return c


@api_router.get("/cubes")
async def list_cubes(user: dict = Depends(get_current_user)):
    rows = db.cubes.find({"user_id": user["id"]}, {"_id": 0}).sort("updated_at", -1).limit(200)
    return {"cubes": [cube_summary(c) async for c in rows]}


@api_router.get("/cubes/{cube_id}")
async def get_cube(cube_id: str, user: dict = Depends(get_current_user)):
    c = await _owned_cube(cube_id, user)
    return {**cube_summary(c), "cards": c.get("cards", [])}


@api_router.post("/cubes")
async def create_cube(data: CubeInput, user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc).isoformat()
    cube = {"id": str(uuid.uuid4()), "user_id": user["id"], "name": data.name.strip(),
            "cubecobra_id": (data.cubecobra_id or "").strip() or None,
            "cards": _cube_cards(data.cards), "created_at": now, "updated_at": now}
    await db.cubes.insert_one(cube)
    return {**cube_summary(cube), "cards": cube["cards"]}


@api_router.put("/cubes/{cube_id}")
async def update_cube(cube_id: str, data: CubeUpdate, user: dict = Depends(get_current_user)):
    await _owned_cube(cube_id, user)
    update: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if data.name is not None:
        update["name"] = data.name.strip()
    if data.cubecobra_id is not None:
        update["cubecobra_id"] = data.cubecobra_id.strip() or None
    if data.cards is not None:
        update["cards"] = _cube_cards(data.cards)
    await db.cubes.update_one({"id": cube_id}, {"$set": update})
    c = await _owned_cube(cube_id, user)
    return {**cube_summary(c), "cards": c.get("cards", [])}


@api_router.delete("/cubes/{cube_id}")
async def delete_cube(cube_id: str, user: dict = Depends(get_current_user)):
    await _owned_cube(cube_id, user)
    await db.cubes.delete_one({"id": cube_id})
    return {"ok": True}

# ===================== Rotisserie Cube Draft =====================

class DraftCreate(BaseModel):
    name: str = "Cube Draft"
    num_players: int = Field(ge=1, le=12)   # everyone at the table, bots included
    num_seats: int = Field(ge=1, le=64)
    num_bots: int = Field(0, ge=0, le=11)    # bots seated straight away (the rest are people)
    double_draft_after: int = 0   # picks per seat made singly before turns grant 2; 0 = never
    pick_cap: int = 45            # picks per seat
    private: bool = False         # hidden from Open tables; join by link or code
    mode: str = Field(default="rotisserie", pattern="^(rotisserie|packs)$")
    pack_count: int = Field(default=3, ge=1, le=6)     # pack drafts: packs per seat
    pack_size: int = Field(default=15, ge=3, le=20)    # pack drafts: cards per pack
    timer: str = Field(default="shrinking", pattern="^(shrinking|off)$")
    pool: str = Field(default="cube", pattern="^(cube|vintage)$")   # "vintage" = VRD: every Vintage-legal paper card
    cube: List[dict] = []

class ClaimInput(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    player_token: Optional[str] = None

class PickInput(BaseModel):
    player_token: str
    seat_index: int
    card_id: str

class ChatInput(BaseModel):
    player_token: str
    text: str = Field(min_length=1, max_length=500)

class CancelInput(BaseModel):
    host_token: str

class AdminPickInput(BaseModel):
    host_token: str
    order: int
    card_id: str

def compute_pick_order(num_seats: int, double_after: int, pick_cap: int, pool_size: int) -> List[int]:
    """Snake order over seats with optional double-draft phase. Endpoints repeat
    naturally in a snake, so during the double phase boundary seats get 4 picks in a row."""
    order: List[int] = []
    counts = [0] * num_seats
    max_total = min(num_seats * pick_cap, pool_size)

    def slots():
        while True:
            for s in range(num_seats):
                yield s
            for s in range(num_seats - 1, -1, -1):
                yield s

    gen = slots()
    guard = 0
    while len(order) < max_total and guard < max_total * 4 + 100:
        guard += 1
        s = next(gen)
        if counts[s] >= pick_cap:
            continue
        picks = 2 if (double_after > 0 and counts[s] >= double_after) else 1
        picks = min(picks, pick_cap - counts[s], max_total - len(order))
        for _ in range(picks):
            order.append(s)
            counts[s] += 1
    return order

def draft_state(d: dict, light: bool = False) -> dict:
    picked_ids = [p["card_id"] for p in d.get("picks", [])]
    base = {
        "share_id": d["share_id"],
        "join_code": d.get("join_code"),
        "private": bool(d.get("private")),
        "name": d["name"],
        "status": d["status"],
        "num_players": d["num_players"],
        "num_seats": d["num_seats"],
        "seats_per_player": d["num_seats"] // d["num_players"],
        "double_draft_after": d["double_draft_after"],
        "pick_cap": d["pick_cap"],
        "seats": d["seats"],
        "players": [{"id": p["id"], "name": p["name"], "seats": p["seats"], "is_bot": bool(p.get("is_bot"))} for p in d.get("players", [])],
        "picks": d.get("picks", []),
        "pick_index": len(d.get("picks", [])),
        "order_len": len(d.get("order", [])),
        "current_seat_index": (d["order"][len(d.get("picks", []))] if d["status"] == "drafting" and len(d.get("picks", [])) < len(d.get("order", [])) else None),
        "messages": d.get("messages", [])[-50:],
        "mode": d.get("mode", "rotisserie"),
        "pool": d.get("pool", "cube"),
        "rev": d.get("rev", 0),
        "version": f'{d.get("rev", 0)}|{d.get("updated_at")}',   # changes on every write (picks, chat, seats)
    }
    if d.get("mode") == "packs":
        base.update({"pack_count": d.get("pack_count"), "pack_size": d.get("pack_size"), "timer": d.get("timer"),
                     "current_seat_index": None, "order_len": d["num_seats"] * d["pick_cap"]})
        if d.get("packs"):
            base["packs"] = pd.public_view(d)
        if d["status"] != "complete":       # picks stay hidden until the draft ends
            base["picks"] = []
            picked_ids = []
    if not light:
        base["cube"] = d.get("cube", [])
        base["bot_combos"] = [c["pieces"] for c in d.get("bot_combos", [])]
    else:
        base["picked_ids"] = picked_ids
    return base

@api_router.get("/cube/cubecobra")
async def cubecobra_fetch(id: str):
    cube_id = id.strip()
    if "/cube/" in cube_id:
        parts = [p for p in cube_id.split("/") if p]
        cube_id = parts[-1]
    cube_id = cube_id.split("?")[0]
    async with httpx.AsyncClient(timeout=20.0, headers=HEADERS, follow_redirects=True) as hc:
        r = await hc.get(f"https://cubecobra.com/cube/api/cubelist/{cube_id}")
        if r.status_code != 200:
            raise HTTPException(status_code=404, detail="Cube not found on CubeCobra")
        names = [ln.strip() for ln in r.text.splitlines() if ln.strip()]
    return {"names": names}

MAX_CUSTOM_CARDS = 30
MAX_CUSTOM_IMAGE = 400_000   # characters of data URL (~300 KB image); the client sends ~60 KB JPEGs


def _clean_custom_cards(cube: List[dict]) -> List[dict]:
    """Custom cards carry an uploaded image (as a data URL) and are treated as tokens: no mana cost,
    no colour, never chosen by bots. Normalise them and reject anything malformed or oversized."""
    customs = [c for c in cube if c.get("is_custom")]
    if len(customs) > MAX_CUSTOM_CARDS:
        raise HTTPException(status_code=400, detail=f"At most {MAX_CUSTOM_CARDS} custom cards per draft")
    out = []
    for c in cube:
        if not c.get("is_custom"):
            out.append(c)
            continue
        image = str(c.get("image") or "")
        if not image.startswith("data:image/") or len(image) > MAX_CUSTOM_IMAGE:
            raise HTTPException(status_code=400, detail="Each custom card needs an image under 300 KB")
        name = str(c.get("name") or "").strip()[:80] or "Custom card"
        out.append({
            "id": "custom-" + str(c.get("id") or uuid.uuid4().hex).removeprefix("custom-")[:40],
            "is_custom": True, "name": name, "image": image,
            "type_line": "Token — Custom", "mana_cost": "", "cmc": 0, "colors": [], "color_identity": [],
            "oracle_text": str(c.get("oracle_text") or "")[:500], "rarity": "special", "set": "", "elo": None,
        })
    return out


# Join codes: 5 characters without look-alikes (no 0/O, 1/I/L), easy to read out at the table.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


async def _new_join_code() -> str:
    for _ in range(20):
        code = "".join(random.choice(CODE_ALPHABET) for _ in range(5))
        if not await db.drafts.find_one({"join_code": code}, {"_id": 1}):
            return code
    raise HTTPException(status_code=503, detail="Could not create a table code, try again")


@api_router.get("/drafts/code/{code}")
async def find_by_code(code: str):
    """Look up a table by its join code (or its share id, which works as a code too)."""
    c = code.strip()
    d = await db.drafts.find_one({"join_code": c.upper()}, {"share_id": 1, "status": 1, "_id": 0}) \
        or await db.drafts.find_one({"share_id": c.lower()}, {"share_id": 1, "status": 1, "_id": 0})
    if not d or d.get("status") == "cancelled":
        raise HTTPException(status_code=404, detail="No table with that code")
    return {"share_id": d["share_id"], "status": d["status"]}


@api_router.post("/drafts")
async def create_draft(data: DraftCreate):
    if data.num_seats % data.num_players != 0:
        raise HTTPException(status_code=400, detail="Seats must divide evenly among players")
    if data.pool == "vintage":
        if data.mode != "rotisserie":
            raise HTTPException(status_code=400, detail="VRD is a rotisserie format")
        data.cube = []      # the draft's card list fills up as cards are picked
    elif not data.cube:
        raise HTTPException(status_code=400, detail="Cube is empty")
    if data.num_bots >= data.num_players:
        raise HTTPException(status_code=400, detail="Leave at least one seat for a person")
    data.cube = _clean_custom_cards(data.cube)
    if data.mode == "packs":
        need = pd.cards_needed(data.num_seats, data.pack_count, data.pack_size)
        if len(data.cube) < need:
            raise HTTPException(status_code=400, detail=f"The cube has {len(data.cube)} cards, but {data.num_seats} seats × "
                                f"{data.pack_count} packs × {data.pack_size} cards needs {need}. Use fewer or smaller packs.")
        data.pick_cap = data.pack_count * data.pack_size
    now = datetime.now(timezone.utc).isoformat()
    draft = {
        "id": str(uuid.uuid4()),
        "share_id": str(uuid.uuid4())[:8],
        "name": data.name,
        "status": "lobby",
        "num_players": data.num_players,
        "num_seats": data.num_seats,
        "double_draft_after": data.double_draft_after,
        "pick_cap": data.pick_cap,
        "mode": data.mode,
        "pool": data.pool,
        "pack_count": data.pack_count,
        "pack_size": data.pack_size,
        "timer": data.timer,
        "private": data.private,
        "join_code": await _new_join_code(),
        "cube": data.cube,
        "seats": [{"index": i, "player_id": None, "player_name": None} for i in range(data.num_seats)],
        "players": [],
        "order": [],
        "picks": [],
        "messages": [],
        "host_token": str(uuid.uuid4()),
        "created_at": now,
        "updated_at": now,
    }
    if data.num_bots:
        rng = random.Random()
        for _ in range(data.num_bots):
            _seat_bot(draft, rng)
    if data.pool == "vintage":
        _warm_vrd_pool()
    else:
        _warm_card_stats(draft["cube"])
    await db.drafts.insert_one(draft)
    return {**draft_state(draft), "host_token": draft["host_token"]}

@api_router.get("/drafts/open")
async def list_open_drafts():
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
    # Lobbies to join, plus drafts under way to watch. Private tables never appear here.
    live_cutoff = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    query = {"private": {"$ne": True}, "$or": [
        {"status": "lobby", "created_at": {"$gte": cutoff}},
        {"status": "drafting", "updated_at": {"$gte": live_cutoff}},
    ]}
    projection = {"_id": 0, "cube": 0, "bot_stats": 0, "bot_combos": 0, "messages": 0, "order": 0}
    cursor = db.drafts.find(query, projection).sort("created_at", -1).limit(40)
    lobbies, live = [], []
    async for d in cursor:
        row = {
            "share_id": d["share_id"],
            "name": d["name"],
            "status": d["status"],
            "num_players": d["num_players"],
            "num_seats": d["num_seats"],
            "players_joined": len(d.get("players", [])),
            "seats_claimed": sum(1 for s in d["seats"] if s["player_id"] is not None),
            "picks_made": len(d.get("picks", [])),
            "mode": d.get("mode", "rotisserie"),
            "pool": d.get("pool", "cube"),
            "created_at": d["created_at"],
        }
        (lobbies if d["status"] == "lobby" else live).append(row)
    sizes = {r["share_id"]: 0 for r in lobbies}
    if sizes:   # cube size for lobbies only, without loading whole cubes
        async for r in db.drafts.aggregate([{"$match": {"share_id": {"$in": list(sizes)}}},
                                            {"$project": {"_id": 0, "share_id": 1, "n": {"$size": {"$ifNull": ["$cube", []]}}}}]):
            sizes[r["share_id"]] = r["n"]
    for r in lobbies:
        r["cube_size"] = sizes[r["share_id"]]
    return {"drafts": lobbies, "live": live}

@api_router.get("/drafts/{share_id}")
async def get_draft(share_id: str):
    d = await db.drafts.find_one({"share_id": share_id}, {"_id": 0, "bot_stats": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft_state(d)

@api_router.get("/drafts/{share_id}/state")
async def get_draft_state(share_id: str, x_player_token: Optional[str] = Header(default=None),
                          x_known_version: Optional[str] = Header(default=None)):
    # Pack drafts poll every second or so. If nothing changed since the caller's last response and no
    # bot or timer is due to act, answer from a ~2 KB summary instead of loading the whole draft.
    if x_known_version:
        probe = await db.drafts.find_one({"share_id": share_id}, _PACK_PROBE)
        if probe and probe.get("mode") == "packs" and probe.get("status") == "drafting" \
                and f'{probe.get("rev", 0)}|{probe.get("updated_at")}' == x_known_version and not _pack_action_due(probe):
            return {"unchanged": True, "version": x_known_version, "server_time": datetime.now(timezone.utc).isoformat()}
    d = await _draft(share_id)
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found")
    if d.get("mode") == "packs":
        d = await pack_auto_actions(d)
        return _pack_state(d, x_player_token)
    d = await maybe_bot_pick(d)
    return draft_state(d, light=True)


# ===================== Pack drafts =====================

_PACK_PROBE = {"_id": 0, "share_id": 1, "rev": 1, "updated_at": 1, "status": 1, "mode": 1,
               "packs.queues": 1, "packs.since": 1, "packs.contents": 1, "packs.timer": 1,
               "players.seats": 1, "players.is_bot": 1}


def _bot_due(share_id: str, seat: int, since: Optional[str], now: datetime) -> bool:
    """A bot picks once its thinking time (seeded by when the pack arrived) has passed."""
    return bool(since) and datetime.fromisoformat(since) + timedelta(seconds=_bot_delay(share_id, f"{seat}:{since}")) <= now


def _pack_action_due(d: dict) -> bool:
    """Whether a bot or an expired timer should pick right now (works on the small probe document)."""
    st = d.get("packs") or {}
    if not st.get("queues"):
        return False
    now = datetime.now(timezone.utc)
    bots = {s for p in d.get("players", []) if p.get("is_bot") for s in p.get("seats", [])}
    for s in pd.seats_waiting(st):
        if s in bots and _bot_due(d["share_id"], s, st["since"].get(str(s)), now):
            return True
    return bool(pd.overdue(st, now.isoformat()))

def _player_by_token(d: dict, token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    return next((p for p in d.get("players", []) if p.get("token") == token and not p.get("is_bot")), None)


def _pack_state(d: dict, token: Optional[str]) -> dict:
    """Light state plus, for a seated player, the packs in front of their own seats and their picks."""
    out = draft_state(d, light=True)
    out["server_time"] = datetime.now(timezone.utc).isoformat()   # lets clients correct their clock for timers
    player = _player_by_token(d, token)
    if player and d.get("packs"):
        out["my"] = pd.private_view(d, player["seats"])
    return out


async def _save_pack_draft(d: dict) -> bool:
    """Write packs/picks/status if nobody else changed the draft since we read it (revision check)."""
    rev = d.get("rev", 0)
    status = "complete" if pd.is_complete(d["packs"]) else "drafting"
    d["status"] = status
    stamp = datetime.now(timezone.utc).isoformat()
    res = await db.drafts.update_one(
        {"share_id": d["share_id"], "rev": rev},
        {"$set": {"packs": d["packs"], "picks": d["picks"], "status": status, "rev": rev + 1, "updated_at": stamp}},
    )
    if res.modified_count:
        d["rev"] = rev + 1
        d["updated_at"] = stamp       # keep the version we report in step with the database
        return True
    return False


def _auto_choice(d: dict, seat: int, rng: random.Random, index, combos) -> str:
    """The card a bot (or the timer) takes for `seat`: the bot engine's pick from that seat's pack."""
    st = d["packs"]
    owned = [p["card_id"] for p in d["picks"] if p["seat_index"] == seat]
    pack = pd.pack_for(st, seat)
    try:
        return choose_from_pack(index, owned, pack, d["pick_cap"], combos, rng)
    except ValueError:
        return pack[0]


async def pack_auto_actions(d: dict) -> dict:
    """On each poll: bots pick once their thinking time has passed, and seats whose timer ran out get
    an automatic pick. Everything happens in memory and is saved in one revision-checked write; if
    someone else wrote first, the next poll simply tries again."""
    if d.get("status") != "drafting" or not d.get("packs"):
        return d
    bot_seats = {s for p in d["players"] if p.get("is_bot") for s in p["seats"]}
    changed = False
    deadline = datetime.now(timezone.utc) + timedelta(seconds=1.5)
    for _ in range(400):
        if pd.is_complete(d["packs"]) or datetime.now(timezone.utc) > deadline:
            break
        now = datetime.now(timezone.utc)
        acted = False
        overdue = set(pd.overdue(d["packs"], now.isoformat()))
        for seat in pd.seats_waiting(d["packs"]):
            since = d["packs"]["since"].get(str(seat))
            if seat in bot_seats:
                if not _bot_due(d["share_id"], seat, since, now):
                    continue
                flags = {"bot": True}
            elif seat in overdue:
                flags = {"auto": True}
            else:
                continue
            rng = random.Random(f"{d['share_id']}:{seat}:{len(d['picks'])}")
            index, combos = await _bot_index(d["share_id"])
            card = await run_in_threadpool(_auto_choice, d, seat, rng, index, combos)
            pd.apply_pick(d, seat, card, now.isoformat(), **flags)
            acted = changed = True
        if not acted:
            break
    if changed and not await _save_pack_draft(d):
        return await _draft(d["share_id"])
    return d


class PackAutopickInput(BaseModel):
    host_token: str
    seat_index: int


@api_router.post("/drafts/{share_id}/packs/autopick")
async def pack_autopick(share_id: str, data: PackAutopickInput):
    """Host: make the pick for a seat that's holding things up (e.g. someone left with the timer off)."""
    for _ in range(6):
        d = await _draft(share_id)
        if not d or d.get("mode") != "packs":
            raise HTTPException(status_code=404, detail="Pack draft not found")
        if d.get("host_token") != data.host_token:
            raise HTTPException(status_code=403, detail="Only the host can pick for a seat")
        if d["status"] != "drafting" or not pd.pack_for(d["packs"], data.seat_index):
            raise HTTPException(status_code=400, detail="That seat has no pack waiting")
        index, combos = await _bot_index(share_id)
        card = await run_in_threadpool(_auto_choice, d, data.seat_index, random.Random(), index, combos)
        pd.apply_pick(d, data.seat_index, card, auto=True)
        if await _save_pack_draft(d):
            return draft_state(d, light=True)
    raise HTTPException(status_code=409, detail="Busy, try again")


async def _pack_pick(share_id: str, data: "PickInput") -> dict:
    for _ in range(8):   # retry on concurrent writes (other players picking at the same moment)
        d = await _draft(share_id)
        if d["status"] != "drafting":
            raise HTTPException(status_code=400, detail="Draft is not active")
        player = _player_by_token(d, data.player_token)
        if not player or data.seat_index not in player["seats"]:
            raise HTTPException(status_code=403, detail="You do not control this seat")
        try:
            pd.apply_pick(d, data.seat_index, data.card_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        if await _save_pack_draft(d):
            return _pack_state(d, data.player_token)
    raise HTTPException(status_code=409, detail="Busy, try again")

@api_router.post("/drafts/{share_id}/claim")
async def claim_seats(share_id: str, data: ClaimInput):
    d = await _draft(share_id)
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found")
    if d["status"] != "lobby":
        raise HTTPException(status_code=400, detail="Draft already started")
    name = data.name.strip()
    # Reattach by token or by existing name
    for p in d["players"]:
        if (data.player_token and p["token"] == data.player_token) or p["name"].lower() == name.lower():
            return {"player_token": p["token"], "player_id": p["id"], "name": p["name"], "seats": p["seats"]}
    if len(d["players"]) >= d["num_players"]:
        raise HTTPException(status_code=400, detail="All player slots are taken")
    # Spread each player's seats evenly across the snake so no one holds both
    # end seats (which would grant back-to-back picks at the wheel on both ends).
    j = len(d["players"])  # join index -> seat class (index % num_players == j)
    assigned = sorted(s["index"] for s in d["seats"] if s["index"] % d["num_players"] == j)
    pid = str(uuid.uuid4())
    token = str(uuid.uuid4())
    for s in d["seats"]:
        if s["index"] in assigned:
            s["player_id"] = pid
            s["player_name"] = name
    d["players"].append({"id": pid, "token": token, "name": name, "seats": assigned})
    await db.drafts.update_one({"share_id": share_id}, {"$set": {"seats": d["seats"], "players": d["players"], "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"player_token": token, "player_id": pid, "name": name, "seats": assigned}

def _shuffle_seats(d: dict) -> None:
    """Randomise who sits where when the draft starts (seats stay spread around the snake)."""
    slots = list(range(d["num_players"]))
    random.shuffle(slots)
    for slot, p in zip(slots, d["players"]):
        p["seats"] = sorted(s["index"] for s in d["seats"] if s["index"] % d["num_players"] == slot)
    for s in d["seats"]:
        owner = next((p for p in d["players"] if s["index"] in p["seats"]), None)
        s["player_id"] = owner["id"] if owner else None
        s["player_name"] = owner["name"] if owner else None


@api_router.post("/drafts/{share_id}/start")
async def start_draft(share_id: str):
    d = await db.drafts.find_one({"share_id": share_id}, {"_id": 0, "bot_stats": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found")
    if d["status"] != "lobby":
        raise HTTPException(status_code=400, detail="Already started")
    if any(s["player_id"] is None for s in d["seats"]):
        raise HTTPException(status_code=400, detail="Not all seats are claimed yet")
    _shuffle_seats(d)
    now = datetime.now(timezone.utc).isoformat()
    if d.get("mode") == "packs":
        try:
            packs = pd.new_state(d["cube"], d["num_seats"], d["pack_count"], d["pack_size"], d.get("timer", "shrinking"), at=now)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        update = {"status": "drafting", "order": [], "packs": packs, "rev": 0, "started_at": now, "updated_at": now,
                  "seats": d["seats"], "players": d["players"]}
    else:
        pool_size = 10 ** 6 if d.get("pool") == "vintage" else len(d["cube"])
        order = compute_pick_order(d["num_seats"], d["double_draft_after"], d["pick_cap"], pool_size)
        update = {"status": "drafting", "order": order, "started_at": now, "updated_at": now,
                  "seats": d["seats"], "players": d["players"]}
    # Card knowledge for bots and pick suggestions: Spellbook combos plus CubeCobra ratings and
    # package partners (usually cached while the lobby filled up; bot tables wait a little for them).
    has_bots = any(p.get("is_bot") for p in d["players"])

    async def _stats():
        try:
            await ensure_stats(db, _cube_names(d["cube"]), budget_s=12.0 if has_bots else 2.0)
            return await draft_stats(db, d["cube"])
        except Exception as exc:  # bots and suggestions still work without these
            logger.warning("CubeCobra card stats unavailable: %s", exc)
            return None

    if d.get("pool") == "vintage":
        _warm_vrd_pool()            # bots' card knowledge lives in the shared VRD pool (loads in the background)
    else:
        # Both lookups can take several seconds for a cube the server hasn't seen before: run them together.
        combos, stats = await asyncio.gather(fetch_combos(build_card_index(d["cube"])), _stats())
        update["bot_combos"] = [c.to_dict() for c in combos]
        if stats is not None:
            update["bot_stats"] = stats
    if update.get("packs"):
        # Fetching card knowledge above can take a few seconds: start the pick clocks now, not before.
        later = datetime.now(timezone.utc).isoformat()
        update["packs"]["since"] = {k: later for k in update["packs"]["since"]}
        update["started_at"] = update["updated_at"] = later
    await db.drafts.update_one({"share_id": share_id}, {"$set": update})
    _CARDS_CACHE.pop(share_id, None)      # rebuild the bots' card index with the fresh stats
    d = await db.drafts.find_one({"share_id": share_id}, {"_id": 0, "bot_stats": 0})
    return draft_state(d)

@api_router.post("/drafts/{share_id}/cancel")
async def cancel_draft(share_id: str, data: CancelInput):
    d = await _draft(share_id)
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found")
    if d.get("host_token") != data.host_token:
        raise HTTPException(status_code=403, detail="Only the host can close this table")
    await db.drafts.update_one({"share_id": share_id}, {"$set": {"status": "cancelled", "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"status": "cancelled"}

@api_router.get("/drafts/{share_id}/build")
async def build_from_pool(share_id: str, seat: int, size: int = 40, x_player_token: Optional[str] = Header(default=None)):
    """Suggested deck for one seat's picks: main deck card ids plus basic land counts by colour."""
    d = await _draft(share_id)
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found")
    if d.get("mode") == "packs" and d["status"] != "complete":
        player = _player_by_token(d, x_player_token)
        if not player or seat not in player["seats"]:
            raise HTTPException(status_code=403, detail="Picks are hidden until the draft ends")
    size = max(20, min(size, 100))
    picked = {p["card_id"] for p in d.get("picks", []) if p["seat_index"] == seat}
    cards = await _cards(share_id)
    pool = [c for c in cards["cube"] if c["id"] in picked and not c.get("is_custom")]
    index = cards["index"]
    return await run_in_threadpool(suggest_deck, pool, index, size)

async def _vrd_card(card_id: str, cards: dict) -> dict:
    """A VRD pick's card data, checked: Vintage-legal, on paper, not a basic land."""
    hit = next((c for c in cards["pool_cards"] if c["id"] == card_id), None) if card_id in cards["pool_ids"] else None
    if hit:
        return hit
    async with httpx.AsyncClient(timeout=20.0, headers=HEADERS) as hc:
        found = await _collection_lookup(hc, [{"id": card_id}])
    if not found:
        raise HTTPException(status_code=400, detail="Card not found on Scryfall")
    raw = found[0]
    if vrd.is_basic(raw):
        raise HTTPException(status_code=400, detail="Basic lands are free; no need to draft them")
    if not vrd.is_legal(raw):
        raise HTTPException(status_code=400, detail=f"{raw.get('name')} isn't legal in Vintage (paper)")
    return map_card(raw)


@api_router.get("/drafts/{share_id}/cube")
async def draft_cube_since(share_id: str, start: int = 0):
    """Cards in the draft's card list from position `start` on. VRD drafts add cards as they're picked,
    so clients fetch just the new ones instead of reloading the whole draft."""
    doc = await db.drafts.find_one({"share_id": share_id}, {"_id": 0, "share_id": 1, "cube": {"$slice": [max(start, 0), 1000]}})
    if not doc:
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"cards": doc.get("cube", []), "start": max(start, 0)}


@api_router.get("/drafts/{share_id}/vrd/top")
async def vrd_top(share_id: str, limit: int = 60):
    """Highest-rated Vintage cards nobody has drafted yet (a starting list before you search)."""
    d = await _draft(share_id)
    if not d or d.get("pool") != "vintage":
        raise HTTPException(status_code=404, detail="VRD draft not found")
    cards = await _cards(share_id)
    if not cards["pool_cards"]:
        return {"cards": [], "warming": True}
    keep = set(_remaining_ids(d, cards))
    out = [c for c in cards["pool_cards"] if c["id"] in keep][: max(1, min(limit, 200))]
    return {"cards": out}


@api_router.post("/drafts/{share_id}/pick")
async def make_pick(share_id: str, data: PickInput):
    d = await _draft(share_id)
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found")
    if d.get("mode") == "packs":
        return await _pack_pick(share_id, data)
    if d["status"] != "drafting":
        raise HTTPException(status_code=400, detail="Draft is not active")
    pick_index = len(d["picks"])
    if pick_index >= len(d["order"]):
        raise HTTPException(status_code=400, detail="Draft is complete")
    current_seat = d["order"][pick_index]
    if data.seat_index != current_seat:
        raise HTTPException(status_code=409, detail="It is not that seat's turn")
    player = next((p for p in d["players"] if p["token"] == data.player_token), None)
    if not player or data.seat_index not in player["seats"]:
        raise HTTPException(status_code=403, detail="You do not control this seat")
    picked_ids = {p["card_id"] for p in d["picks"]}
    if data.card_id in picked_ids:
        raise HTTPException(status_code=409, detail="Card already taken")
    cards = await _cards(share_id)
    card_doc = None
    if cards.get("vintage"):
        card_doc = await _vrd_card(data.card_id, cards)
        if card_doc["name"].lower() in _taken_names(d, cards["cube"]):
            raise HTTPException(status_code=409, detail=f"{card_doc['name']} has already been drafted")
    elif data.card_id not in cards["ids"]:
        raise HTTPException(status_code=400, detail="Card not in cube")
    pick = {"order": pick_index, "seat_index": data.seat_index, "card_id": data.card_id, "ts": datetime.now(timezone.utc).isoformat()}
    new_status = "complete" if pick_index + 1 >= len(d["order"]) else "drafting"
    push: Dict[str, Any] = {"picks": pick}
    if card_doc:
        push["cube"] = card_doc
    # Only succeeds if nobody (e.g. a bot on a poll) picked in the meantime.
    res = await db.drafts.update_one({"share_id": share_id, "picks": {"$size": pick_index}},
                                     {"$push": push, "$set": {"status": new_status, "updated_at": pick["ts"]}})
    if not res.modified_count:
        raise HTTPException(status_code=409, detail="Someone else picked first; try again")
    if card_doc:
        await _vrd_add_card(share_id, card_doc)
    d = await _draft(share_id)
    return draft_state(d, light=True)


@api_router.post("/drafts/{share_id}/undo")
async def undo_pick(share_id: str, data: CancelInput):
    d = await _draft(share_id)
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found")
    if d.get("host_token") != data.host_token:
        raise HTTPException(status_code=403, detail="Only the host can undo picks")
    if d.get("mode") == "packs":
        raise HTTPException(status_code=400, detail="Undo isn't available in pack drafts")
    if not d.get("picks"):
        raise HTTPException(status_code=400, detail="No picks to undo")
    picks = d["picks"][:-1]
    await db.drafts.update_one({"share_id": share_id}, {"$set": {"picks": picks, "status": "drafting", "updated_at": datetime.now(timezone.utc).isoformat()}})
    d = await _draft(share_id)
    return draft_state(d, light=True)


@api_router.post("/drafts/{share_id}/reassign")
async def reassign_pick(share_id: str, data: AdminPickInput):
    d = await _draft(share_id)
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found")
    if d.get("host_token") != data.host_token:
        raise HTTPException(status_code=403, detail="Only the host can reassign picks")
    if d.get("mode") == "packs" or d.get("pool") == "vintage":
        raise HTTPException(status_code=400, detail="Reassign isn't available in this format; use Undo")
    pk = next((p for p in d.get("picks", []) if p["order"] == data.order), None)
    if not pk:
        raise HTTPException(status_code=404, detail="Pick not found")
    if data.card_id not in (await _cards(share_id))["ids"]:
        raise HTTPException(status_code=400, detail="Card not in cube")
    if any(p["card_id"] == data.card_id for p in d["picks"] if p["order"] != data.order):
        raise HTTPException(status_code=409, detail="Card already drafted")
    pk["card_id"] = data.card_id
    await db.drafts.update_one({"share_id": share_id}, {"$set": {"picks": d["picks"], "updated_at": datetime.now(timezone.utc).isoformat()}})
    d = await _draft(share_id)
    return draft_state(d, light=True)


@api_router.post("/drafts/{share_id}/chat")
async def post_chat(share_id: str, data: ChatInput):
    d = await _draft(share_id)
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found")
    player = next((p for p in d.get("players", []) if p["token"] == data.player_token), None)
    if not player:
        raise HTTPException(status_code=403, detail="Claim a seat to chat")
    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message is empty")
    msg = {"id": str(uuid.uuid4()), "name": player["name"], "text": text, "ts": datetime.now(timezone.utc).isoformat()}
    messages = d.get("messages", [])
    messages.append(msg)
    messages = messages[-200:]
    await db.drafts.update_one({"share_id": share_id}, {"$set": {"messages": messages, "updated_at": datetime.now(timezone.utc).isoformat()}})
    d = await _draft(share_id)
    return draft_state(d, light=True)


# ----------------------- Startup -----------------------


# ===================== Draft bots =====================
# Bots fill player slots chosen by the host. Their picks are made here on the server, lazily, by
# whichever state poll arrives after a short human-like delay. See docs/DRAFT_BOTS.md.

class BotInput(BaseModel):
    host_token: str

class BotRemoveInput(BaseModel):
    host_token: str
    player_id: str

_BACKGROUND: set = set()   # keep references to background tasks so they aren't garbage collected


def _cube_names(cube: List[dict]) -> List[str]:
    return [c.get("name", "") for c in cube if not c.get("is_custom")]


def _warm_card_stats(cube: List[dict]) -> None:
    """Start caching CubeCobra stats for a cube in the background (bots use them once the draft starts)."""
    task = asyncio.create_task(ensure_stats(db, _cube_names(cube), budget_s=600.0))
    _BACKGROUND.add(task)
    task.add_done_callback(_BACKGROUND.discard)


# Draft documents carry the whole cube plus CubeCobra stats (often over a megabyte). Polls and picks
# load drafts WITHOUT those heavy fields; the cube and the bots' card index are loaded once per draft
# and kept in memory (the cube never changes after the draft is created).
_HEAVY = {"_id": 0, "cube": 0, "bot_stats": 0, "bot_combos": 0}
_CARDS_CACHE: Dict[str, dict] = {}   # share_id -> {"cube", "ids", "index", "combos"}


async def _draft(share_id: str) -> Optional[dict]:
    """A draft without its cube and card stats (what polls, picks and lobby actions need)."""
    return await db.drafts.find_one({"share_id": share_id}, _HEAVY)


def _warm_vrd_pool() -> None:
    """Start loading (or, the very first time, building) the VRD bots' pool in the background.
    Only VRD tables call this; nothing ever waits for it (see vrd.py)."""
    async def lookup(ids):
        async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as hc:
            return await _collection_lookup(hc, ids)

    async def oldest(cards):
        async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as hc:
            return await _prefer_oldest(hc, cards)
    vrd.warm(db, lookup, map_card, fetch_combos, build_card_index, oldest)


async def _vrd_rebuild(entry: dict) -> None:
    """(Re)build a VRD draft's bot index: the shared pool plus any picked cards from outside it."""
    extras = [c for c in entry["cube"] if c["id"] not in entry["pool_ids"]]
    index = await run_in_threadpool(build_card_index, entry["pool_cards"] + extras, entry["stats"])
    combos = combos_from_dicts(entry["combo_dicts"])
    attach_combos(index, combos)
    entry.update(index=index, combos=combos, extras=len(extras),
                 ids=entry["pool_ids"] | {c["id"] for c in entry["cube"]})


async def _vrd_add_card(share_id: str, card: dict) -> None:
    """Keep the cached VRD card list in step after we save a pick (saves reloading the whole list)."""
    entry = _CARDS_CACHE.get(share_id)
    if entry and entry.get("vintage"):
        entry["cube"].append(card)
        entry["ids"].add(card["id"])
        if card["id"] not in entry["pool_ids"]:
            await _vrd_rebuild(entry)


def _taken_names(d: dict, cube: List[dict]) -> set:
    """Names already drafted (VRD is singleton across the table, whatever the printing)."""
    picked = {p["card_id"] for p in d.get("picks", [])}
    return {c["name"].lower() for c in cube if c["id"] in picked}


def _remaining_ids(d: dict, cards: dict) -> List[str]:
    """Card ids the bots may still pick: undrafted cube cards, or undrafted names from the VRD pool."""
    taken = {p["card_id"] for p in d.get("picks", [])}
    if cards.get("vintage"):
        names = _taken_names(d, cards["cube"])
        return [c["id"] for c in cards["pool_cards"] if c["id"] not in taken and c["name"].lower() not in names]
    return [cid for cid in cards["index"] if cid not in taken]


async def _cards(share_id: str) -> dict:
    """The draft's cube, card ids and bot card index, loaded once and cached."""
    hit = _CARDS_CACHE.get(share_id)
    if hit and hit.get("vintage") and hit.get("pool_ref") is not vrd.peek():
        # The VRD pool arrived (or gained its combos) since this entry was made: refresh the bot side.
        pool = vrd.peek()
        if pool:
            hit.update(pool_ref=pool, pool_cards=pool["cards"], pool_ids={c["id"] for c in pool["cards"]},
                       stats=pool.get("stats"), combo_dicts=pool.get("combos", []))
            await _vrd_rebuild(hit)
        return hit
    if hit:
        return hit
    doc = await db.drafts.find_one({"share_id": share_id}, {"_id": 0, "cube": 1, "bot_stats": 1, "bot_combos": 1, "status": 1, "pool": 1}) or {}
    if doc.get("pool") == "vintage":
        pool = vrd.peek()
        if not pool:
            _warm_vrd_pool()        # bots wait (and suggestions are empty) until it's ready; people can pick
        entry = {"vintage": True, "cube": doc.get("cube", []), "pool_ref": pool, "pool_cards": (pool or {}).get("cards", []),
                 "pool_ids": {c["id"] for c in (pool or {}).get("cards", [])}, "stats": (pool or {}).get("stats"),
                 "combo_dicts": (pool or {}).get("combos", [])}
        await _vrd_rebuild(entry)
        if len(_CARDS_CACHE) > 40:
            _CARDS_CACHE.clear()
        _CARDS_CACHE[share_id] = entry
        return entry
    cube = doc.get("cube", [])
    index = await run_in_threadpool(build_card_index, cube, doc.get("bot_stats"))
    combos = combos_from_dicts(doc.get("bot_combos", []))
    attach_combos(index, combos)
    entry = {"cube": cube, "ids": {c["id"] for c in cube}, "index": index, "combos": combos}
    if doc.get("status") in ("drafting", "complete"):   # card stats are only final once the draft starts
        if len(_CARDS_CACHE) > 40:
            _CARDS_CACHE.clear()
        _CARDS_CACHE[share_id] = entry
    return entry


async def _bot_index(share_id: str):
    c = await _cards(share_id)
    return c["index"], c["combos"]


def _bot_delay(share_id: str, pick_index) -> float:
    """Bots pick instantly by default (a "thinking" pause adds up fast with several bots between turns).
    BOT_DELAY_SCALE=1 brings back a human-like 0.8-1.7 s pause, stable per pick so concurrent polls agree."""
    try:
        scale = float(os.environ.get("BOT_DELAY_SCALE", "0"))
    except ValueError:
        scale = 1.0
    return scale * (0.8 + random.Random(f"{share_id}:{pick_index}").random() * 0.9)


async def maybe_bot_pick(d: dict) -> dict:
    """Let bots on the clock pick. With no delay configured, several consecutive bot picks happen in
    one poll (bounded so a request never runs long); otherwise one pick per poll once it's due."""
    deadline = datetime.now(timezone.utc) + timedelta(seconds=1.5)
    while True:
        before = len(d.get("picks", []))
        d = await _bot_pick_once(d)
        if len(d.get("picks", [])) == before or datetime.now(timezone.utc) > deadline:
            return d


async def _bot_pick_once(d: dict) -> dict:
    if d.get("status") != "drafting":
        return d
    pick_index = len(d.get("picks", []))
    if pick_index >= len(d.get("order", [])):
        return d
    seat = d["order"][pick_index]
    bot = next((p for p in d["players"] if p.get("is_bot") and seat in p["seats"]), None)
    if not bot:
        return d
    last = d["picks"][-1]["ts"] if d.get("picks") else d.get("started_at") or d["updated_at"]
    due = datetime.fromisoformat(last) + timedelta(seconds=_bot_delay(d["share_id"], pick_index))
    if datetime.now(timezone.utc) < due:
        return d

    cards = await _cards(d["share_id"])
    if cards.get("vintage") and not cards["pool_cards"]:
        return d                    # VRD bots wait a moment for their card pool to load
    index, combos = cards["index"], cards["combos"]
    picks_by_seat: Dict[int, List[str]] = {s["index"]: [] for s in d["seats"]}
    for p in d["picks"]:
        picks_by_seat.setdefault(p["seat_index"], []).append(p["card_id"])
    taken = {p["card_id"] for p in d["picks"]}
    remaining = _remaining_ids(d, cards)
    rng = random.Random(f"{d['share_id']}:{pick_index}:{bot['id']}")
    if remaining:
        ctx = BotContext(index, combos, remaining, picks_by_seat, seat, d["order"], pick_index,
                         d["pick_cap"], Persona.from_dict(bot.get("persona", {})))
        card_id = await run_in_threadpool(choose_pick, ctx, rng)
    else:
        # Bots ignore custom cards, but if those are all that's left they take one so the draft can finish.
        leftovers = [c["id"] for c in (await _cards(d["share_id"]))["cube"] if c["id"] not in taken]
        if not leftovers:
            return d
        card_id = rng.choice(leftovers)

    pick = {"order": pick_index, "seat_index": seat, "card_id": card_id, "ts": datetime.now(timezone.utc).isoformat(), "bot": True}
    status = "complete" if pick_index + 1 >= len(d["order"]) else "drafting"
    push: Dict[str, Any] = {"picks": pick}
    card_doc = None
    if cards.get("vintage"):       # VRD: the draft's card list grows as cards are picked
        card_doc = next((c for c in cards["pool_cards"] if c["id"] == card_id), None)
        if card_doc:
            push["cube"] = card_doc
    # Only succeeds if nobody else picked in the meantime (another poll, an undo, a reassign).
    res = await db.drafts.update_one(
        {"share_id": d["share_id"], "status": "drafting", "picks": {"$size": pick_index}},
        {"$push": push, "$set": {"status": status, "updated_at": pick["ts"]}},
    )
    if card_doc and res.modified_count:
        await _vrd_add_card(d["share_id"], card_doc)
    return await _draft(d["share_id"])


_SUGGEST_CACHE: Dict[tuple, list] = {}


@api_router.get("/drafts/{share_id}/suggestions")
async def pick_suggestions(share_id: str, seat: int, x_player_token: Optional[str] = Header(default=None)):
    """Two or three good picks for a seat right now, from the same engine the bots use.
    Rotisserie: uses only public information. Pack drafts: only the seat's own player may ask."""
    d = await _draft(share_id)
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found")
    if d["status"] != "drafting" or not any(s["index"] == seat for s in d["seats"]):
        return {"suggestions": []}
    if d.get("mode") == "packs":
        player = _player_by_token(d, x_player_token)
        if not player or seat not in player["seats"]:
            raise HTTPException(status_code=403, detail="You do not control this seat")
        pack = pd.pack_for(d["packs"], seat)
        if not pack:
            return {"suggestions": []}
        index, combos = await _bot_index(share_id)
        owned = [p["card_id"] for p in d["picks"] if p["seat_index"] == seat]
        ranked = await run_in_threadpool(rank_pack, index, owned, pack, d["pick_cap"], combos)
        best = ranked[0][0] if ranked else 0
        return {"suggestions": [cid for sc, cid in ranked[:3] if best <= 0 or sc >= 0.7 * best]}
    pick_index = len(d.get("picks", []))
    key = (share_id, pick_index, seat)
    if key not in _SUGGEST_CACHE:
        cards = await _cards(share_id)
        index, combos = cards["index"], cards["combos"]
        picks_by_seat: Dict[int, List[str]] = {s["index"]: [] for s in d["seats"]}
        for p in d["picks"]:
            picks_by_seat.setdefault(p["seat_index"], []).append(p["card_id"])
        remaining = _remaining_ids(d, cards)
        if not remaining:
            return {"suggestions": []}
        ctx = BotContext(index, combos, remaining, picks_by_seat, seat, d["order"], min(pick_index, len(d["order"]) - 1),
                         d["pick_cap"], Persona("steady"))
        top = await run_in_threadpool(suggest_picks, ctx, 3)
        if len(_SUGGEST_CACHE) > 500:
            _SUGGEST_CACHE.clear()
        # Keep suggestions that are reasonably close to the best one.
        best = top[0][1] if top else 0
        _SUGGEST_CACHE[key] = [cid for cid, sc in top if best <= 0 or sc >= 0.7 * best]
    out: Dict[str, Any] = {"suggestions": _SUGGEST_CACHE[key]}
    if d.get("pool") == "vintage":   # VRD: the page may not have these cards yet
        pool = {c["id"]: c for c in (await _cards(share_id))["pool_cards"]}
        out["cards"] = [pool[i] for i in out["suggestions"] if i in pool]
    return out


def _seat_bot(d: dict, rng: random.Random) -> None:
    """Seat a new bot in the next player slot (seats spread around the snake like a person's)."""
    name = bot_names(rng, 1, [p["name"] for p in d["players"]])[0]
    j = len(d["players"])
    assigned = sorted(s["index"] for s in d["seats"] if s["index"] % d["num_players"] == j)
    pid = str(uuid.uuid4())
    for s in d["seats"]:
        if s["index"] in assigned:
            s["player_id"] = pid
            s["player_name"] = name
    d["players"].append({"id": pid, "token": str(uuid.uuid4()), "name": name, "seats": assigned,
                         "is_bot": True, "persona": random_persona(rng).to_dict()})


@api_router.post("/drafts/{share_id}/bots")
async def add_bot(share_id: str, data: BotInput):
    d = await _draft(share_id)
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found")
    if d.get("host_token") != data.host_token:
        raise HTTPException(status_code=403, detail="Only the host can add bots")
    if d["status"] != "lobby":
        raise HTTPException(status_code=400, detail="Draft already started")
    if len(d["players"]) >= d["num_players"]:
        raise HTTPException(status_code=400, detail="All player slots are taken")
    _seat_bot(d, random.Random())
    await db.drafts.update_one({"share_id": share_id}, {"$set": {"seats": d["seats"], "players": d["players"], "updated_at": datetime.now(timezone.utc).isoformat()}})
    _warm_card_stats((await _cards(share_id))["cube"])
    return draft_state(d, light=True)


@api_router.post("/drafts/{share_id}/bots/remove")
async def remove_bot(share_id: str, data: BotRemoveInput):
    d = await _draft(share_id)
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found")
    if d.get("host_token") != data.host_token:
        raise HTTPException(status_code=403, detail="Only the host can remove bots")
    if d["status"] != "lobby":
        raise HTTPException(status_code=400, detail="Draft already started")
    if not any(p["id"] == data.player_id and p.get("is_bot") for p in d["players"]):
        raise HTTPException(status_code=404, detail="Bot not found")
    # Rebuild seat assignments in join order so seat spreading stays correct.
    players = [p for p in d["players"] if p["id"] != data.player_id]
    for s in d["seats"]:
        s["player_id"] = None
        s["player_name"] = None
    for j, p in enumerate(players):
        p["seats"] = sorted(s["index"] for s in d["seats"] if s["index"] % d["num_players"] == j)
        for s in d["seats"]:
            if s["index"] in p["seats"]:
                s["player_id"] = p["id"]
                s["player_name"] = p["name"]
    d["players"] = players
    await db.drafts.update_one({"share_id": share_id}, {"$set": {"seats": d["seats"], "players": players, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return draft_state(d, light=True)


_SIM_CACHE: Dict[str, Any] = {}   # cube_id -> (cards, not_found, combos); simulation only


class SimulateInput(BaseModel):
    cube_id: str
    seats: int = Field(8, ge=2, le=12)
    picks_per_seat: int = Field(45, ge=5, le=90)
    seed: int = 0
    tuning: Dict[str, float] = {}      # overrides for draftbot.engine.TUNING
    baseline: bool = True              # also run an Elo-greedy draft for comparison
    card_stats: bool = True            # use CubeCobra live Elo + package partners
    stats_budget: float = Field(60.0, ge=0, le=240)   # seconds to spend filling the stats cache this call


@api_router.post("/bots/simulate")
async def simulate_bots(data: SimulateInput):
    """Bot-only draft for tuning. Disabled unless ENABLE_BOT_SIM=true (set it on staging only)."""
    if os.environ.get("ENABLE_BOT_SIM", "").lower() != "true":
        raise HTTPException(status_code=404, detail="Not found")
    cached = _SIM_CACHE.get(data.cube_id)
    if not cached:
        names = (await cubecobra_fetch(data.cube_id))["names"]
        resolved = await _collection_by_names(list(dict.fromkeys(names)))
        cube = resolved["cards"]
        combos = await fetch_combos(build_card_index(cube))
        cached = _SIM_CACHE[data.cube_id] = (cube, resolved["not_found"], combos)
    cube, not_found, combos = cached
    resolved = {"not_found": not_found}
    stats = None
    if data.card_stats:
        await ensure_stats(db, _cube_names(cube), budget_s=data.stats_budget)
        stats = await draft_stats(db, cube)
    index = build_card_index(cube, stats)
    order = compute_pick_order(data.seats, 0, data.picks_per_seat, len(cube))
    bots = await run_in_threadpool(run_draft, cube, combos, order, data.seats, data.picks_per_seat, data.seed, (), index, data.tuning)
    greedy = await run_in_threadpool(run_draft, cube, combos, order, data.seats, data.picks_per_seat, data.seed, tuple(range(data.seats))) if data.baseline else None
    return {
        "cube_size": len(cube), "not_found": resolved["not_found"], "combos_in_cube": len(combos),
        "cards_with_stats": len((stats or {}).get("elo", {})),
        "seconds": round(bots["seconds"], 1),
        "bots": summarise(bots, combos),
        "elo_greedy_baseline": [{k: s[k] for k in ("seat", "lane", "on_lane_pct", "avg_elo_top23")} for s in summarise(greedy, combos)] if greedy else [],
    }

@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.decks.create_index("id", unique=True)
    await db.decks.create_index("share_id")
    await db.decks.create_index("user_id")
    await db.drafts.create_index("share_id", unique=True)
    await db.drafts.create_index("join_code", sparse=True)
    await db.card_stats.create_index("key", unique=True)
    await db.cubes.create_index("id", unique=True)
    await db.cubes.create_index("user_id")
    # Optional seed account (handy for local dev and tests). Only created when both values
    # are set explicitly; there is deliberately no built-in default password.
    admin_email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "")
    if not admin_email or not admin_password:
        return
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "name": "Admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})

app.include_router(api_router)

_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_credentials="*" not in _cors_origins,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
