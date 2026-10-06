from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import bcrypt
import jwt
import httpx
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
        r = await hc.get(f"{SCRYFALL}/cards/search", params={"q": f'!"{name}"', "unique": "prints", "order": "released"})
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

# ----------------------- Startup -----------------------

@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.decks.create_index("id", unique=True)
    await db.decks.create_index("share_id")
    await db.decks.create_index("user_id")
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
