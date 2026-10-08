"""
Seed / bootstrap script for Grimoire.

Creates the MongoDB indexes, a seed admin user, and (optionally) loads the
sample deck in data/sample_deck.json. Safe to run multiple times (idempotent).

Usage:
    cd backend && pip install -r requirements.txt     # ensures pymongo/bcrypt present
    python ../scripts/seed.py

Reads configuration from backend/.env (MONGO_URL, DB_NAME, ADMIN_EMAIL, ADMIN_PASSWORD).
"""
import os
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import bcrypt
from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / "backend" / ".env")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "grimoire")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").strip().lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def main():
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]

    # Indexes
    db.users.create_index("email", unique=True)
    db.users.create_index("id", unique=True)
    db.decks.create_index("id", unique=True)
    db.decks.create_index("share_id")
    db.decks.create_index("user_id")
    print("Indexes ensured.")

    # Admin user (needed to own the sample deck)
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        print("ADMIN_EMAIL / ADMIN_PASSWORD not set; skipping admin user and sample deck.")
        return
    admin = db.users.find_one({"email": ADMIN_EMAIL})
    if not admin:
        admin = {
            "id": str(uuid.uuid4()),
            "email": ADMIN_EMAIL,
            "password_hash": hash_password(ADMIN_PASSWORD),
            "name": "Admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        db.users.insert_one(admin)
        print(f"Created admin user: {ADMIN_EMAIL}")
    else:
        print(f"Admin user already exists: {ADMIN_EMAIL}")

    # Sample deck (optional)
    sample_path = ROOT / "data" / "sample_deck.json"
    if sample_path.exists() and db.decks.count_documents({"user_id": admin["id"]}) == 0:
        with open(sample_path) as f:
            deck = json.load(f)
        now = datetime.now(timezone.utc).isoformat()
        deck.update({
            "id": str(uuid.uuid4()),
            "user_id": admin["id"],
            "share_id": str(uuid.uuid4())[:8],
            "created_at": now,
            "updated_at": now,
        })
        db.decks.insert_one(deck)
        print(f"Inserted sample deck: {deck['name']}")
    else:
        print("Skipped sample deck (none found or admin already has decks).")

    print("Done.")


if __name__ == "__main__":
    main()
