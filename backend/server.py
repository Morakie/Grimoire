from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import random
import bcrypt
import jwt
import httpx
import csv
from pathlib import Path
from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_ALGORITHM = "HS256"
JWT_SECRET = os.environ["JWT_SECRET"]

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
    description: str = ""
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

class CollectionInput(BaseModel):
    names: List[str] = []

@api_router.post("/cards/collection")
async def card_collection(data: CollectionInput):
    names = [n for n in data.names if n and n.strip()][:400]
    found = []
    not_found = []
    async with httpx.AsyncClient(timeout=20.0, headers=HEADERS) as hc:
        for i in range(0, len(names), 75):
            chunk = names[i:i + 75]
            identifiers = [{"name": n} for n in chunk]
            r = await hc.post(f"{SCRYFALL}/cards/collection", json={"identifiers": identifiers})
            if r.status_code != 200:
                continue
            payload = r.json()
            for c in payload.get("data", []):
                found.append(map_card(c))
            for nf in payload.get("not_found", []):
                if nf.get("name"):
                    not_found.append(nf["name"])
    return {"cards": found, "not_found": not_found}

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

@api_router.get("/")
async def root():
    return {"message": "Grimoire API"}

@api_router.get("/health")
async def health():
    return {"status": "ok"}

# ===================== Rotisserie Cube Draft =====================

class DraftCreate(BaseModel):
    name: str = "Cube Draft"
    num_players: int = Field(ge=1, le=8)
    num_seats: int = Field(ge=1, le=64)
    double_draft_after: int = 0   # picks per seat made singly before turns grant 2; 0 = never
    pick_cap: int = 45            # picks per seat
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
        "name": d["name"],
        "status": d["status"],
        "num_players": d["num_players"],
        "num_seats": d["num_seats"],
        "seats_per_player": d["num_seats"] // d["num_players"],
        "double_draft_after": d["double_draft_after"],
        "pick_cap": d["pick_cap"],
        "seats": d["seats"],
        "players": [{"id": p["id"], "name": p["name"], "seats": p["seats"]} for p in d.get("players", [])],
        "picks": d.get("picks", []),
        "pick_index": len(d.get("picks", [])),
        "order_len": len(d.get("order", [])),
        "current_seat_index": (d["order"][len(d.get("picks", []))] if d["status"] == "drafting" and len(d.get("picks", [])) < len(d.get("order", [])) else None),
        "messages": d.get("messages", [])[-50:],
    }
    if not light:
        base["cube"] = d.get("cube", [])
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

@api_router.post("/drafts")
async def create_draft(data: DraftCreate):
    if data.num_seats % data.num_players != 0:
        raise HTTPException(status_code=400, detail="Seats must divide evenly among players")
    if not data.cube:
        raise HTTPException(status_code=400, detail="Cube is empty")
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
    await db.drafts.insert_one(draft)
    return {**draft_state(draft), "host_token": draft["host_token"]}

@api_router.get("/drafts/open")
async def list_open_drafts():
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
    cursor = db.drafts.find({"status": "lobby", "created_at": {"$gte": cutoff}}).sort("created_at", -1).limit(30)
    out = []
    async for d in cursor:
        out.append({
            "share_id": d["share_id"],
            "name": d["name"],
            "num_players": d["num_players"],
            "num_seats": d["num_seats"],
            "players_joined": len(d.get("players", [])),
            "seats_claimed": sum(1 for s in d["seats"] if s["player_id"] is not None),
            "cube_size": len(d.get("cube", [])),
            "created_at": d["created_at"],
        })
    return {"drafts": out}

@api_router.get("/drafts/{share_id}")
async def get_draft(share_id: str):
    d = await db.drafts.find_one({"share_id": share_id})
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft_state(d)

@api_router.get("/drafts/{share_id}/state")
async def get_draft_state(share_id: str):
    d = await db.drafts.find_one({"share_id": share_id})
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft_state(d, light=True)

@api_router.post("/drafts/{share_id}/claim")
async def claim_seats(share_id: str, data: ClaimInput):
    d = await db.drafts.find_one({"share_id": share_id})
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

@api_router.post("/drafts/{share_id}/start")
async def start_draft(share_id: str):
    d = await db.drafts.find_one({"share_id": share_id})
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found")
    if d["status"] != "lobby":
        raise HTTPException(status_code=400, detail="Already started")
    if any(s["player_id"] is None for s in d["seats"]):
        raise HTTPException(status_code=400, detail="Not all seats are claimed yet")
    order = compute_pick_order(d["num_seats"], d["double_draft_after"], d["pick_cap"], len(d["cube"]))
    await db.drafts.update_one({"share_id": share_id}, {"$set": {"status": "drafting", "order": order, "updated_at": datetime.now(timezone.utc).isoformat()}})
    d = await db.drafts.find_one({"share_id": share_id})
    return draft_state(d)

@api_router.post("/drafts/{share_id}/cancel")
async def cancel_draft(share_id: str, data: CancelInput):
    d = await db.drafts.find_one({"share_id": share_id})
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found")
    if d.get("host_token") != data.host_token:
        raise HTTPException(status_code=403, detail="Only the host can close this table")
    await db.drafts.update_one({"share_id": share_id}, {"$set": {"status": "cancelled", "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"status": "cancelled"}

@api_router.post("/drafts/{share_id}/pick")
async def make_pick(share_id: str, data: PickInput):
    d = await db.drafts.find_one({"share_id": share_id})
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found")
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
    if not any(c["id"] == data.card_id for c in d["cube"]):
        raise HTTPException(status_code=400, detail="Card not in cube")
    d["picks"].append({"order": pick_index, "seat_index": data.seat_index, "card_id": data.card_id, "ts": datetime.now(timezone.utc).isoformat()})
    new_status = "complete" if len(d["picks"]) >= len(d["order"]) else "drafting"
    await db.drafts.update_one({"share_id": share_id}, {"$set": {"picks": d["picks"], "status": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}})
    d = await db.drafts.find_one({"share_id": share_id})
    return draft_state(d, light=True)


@api_router.post("/drafts/{share_id}/chat")
async def post_chat(share_id: str, data: ChatInput):
    d = await db.drafts.find_one({"share_id": share_id})
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
    d = await db.drafts.find_one({"share_id": share_id})
    return draft_state(d, light=True)


# ----------------------- Startup -----------------------

@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.decks.create_index("id", unique=True)
    await db.decks.create_index("share_id")
    await db.decks.create_index("user_id")
    await db.drafts.create_index("share_id", unique=True)
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@grimoire.gg")
    admin_password = os.environ.get("ADMIN_PASSWORD", "grimoire123")
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

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
