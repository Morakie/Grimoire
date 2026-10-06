# Grimoire — MTG Deck Builder & Analyzer

Grimoire is a fast, modern web app for **Magic: The Gathering** players to build,
optimize, and organize decks. It searches live card data from the public
[Scryfall API](https://scryfall.com/docs/api), visualizes your mana curve and
color distribution, and lets you save, clone, and publicly share decklists.

> This repository is a **platform-independent export**. It was originally built
> on the Emergent platform and has been cleaned so it runs anywhere. See
> [`docs/MIGRATION.md`](docs/MIGRATION.md) for exactly what was removed/changed.

---

## Features

- **Card search** (Scryfall) by name, color, and type, with autocomplete and a
  responsive grid of high-res card art + mana symbols.
- **Deck builder** with a top "find & add" bar, **Mainboard / Sideboard / Commander**
  sections, quantity controls (max 4 copies, basic lands unlimited), and quick-add.
- **Moxfield/Arena-style board**: View (Text / Visual Grid), Group (Type / Mana Value /
  Color / Custom), Sort (Manual / Name / Mana Value), and **drag-and-drop** to reorder,
  move between groups (with manual override), or move between Mainboard/Sideboard.
- **Analytics**: mana curve (CMC 0–7+), color distribution, total cards, average CMC,
  and card-type breakdown.
- **Import / Export** decklists (plain text and JSON; export uses
  `<qty> <name> (<SET>) <collector#>` — Moxfield/MTGA compatible).
- **Accounts** (JWT email/password), a **My Decks** dashboard (create/edit/clone/delete),
  **guest mode** (build without an account; sign in only when saving), and
  **public share links** (`/d/:shareId`).

---

## Tech Stack

| Layer     | Technology |
|-----------|------------|
| Frontend  | React 19, React Router 7, CRACO, Tailwind CSS, shadcn/ui (Radix), Recharts, @dnd-kit, lucide-react, sonner |
| Backend   | FastAPI (Python 3.11+), Motor (async MongoDB), PyJWT, bcrypt, httpx |
| Database  | MongoDB 7 |
| Auth      | Custom JWT (email/password) — **not** a third-party provider |
| External  | Scryfall API (public, no key) |
| Package managers | **yarn** (frontend), **pip** (backend) |

---

## Prerequisites

- **Node.js** 18+ and **yarn** (`npm i -g yarn`)
- **Python** 3.11+ and **pip**
- **MongoDB** 7 — either Docker (recommended) or a hosted instance (e.g. MongoDB Atlas)

---

## Local Setup (step by step)

### 1. Get the code & env files
```bash
git clone <your-repo-url> grimoire && cd grimoire
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```
Open `backend/.env` and set a real `JWT_SECRET` (generate one with
`python -c "import secrets; print(secrets.token_hex(32))"`) and an
`ADMIN_EMAIL` / `ADMIN_PASSWORD`.

### 2. Start MongoDB
Using Docker (recommended):
```bash
docker compose up -d        # starts MongoDB on localhost:27017
```
Or point `MONGO_URL` in `backend/.env` at a hosted database (e.g. an Atlas
`mongodb+srv://...` connection string). **No schema migration is required** —
collections and indexes are created automatically on first run.

### 3. Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```
The API is now at `http://localhost:8001` (all routes are under `/api`).
On startup it creates indexes and seeds the admin user from your `.env`.

Optionally load a sample deck:
```bash
python ../scripts/seed.py
```

### 4. Frontend
```bash
cd frontend
yarn install
yarn start                  # dev server on http://localhost:3000
```
`frontend/.env` must contain `REACT_APP_BACKEND_URL=http://localhost:8001`.

### 5. Production build (frontend)
```bash
cd frontend
yarn build                  # outputs static files to frontend/build
```

---

## Environment Variables

### `backend/.env`
| Variable | Required | Description |
|----------|----------|-------------|
| `MONGO_URL` | yes | MongoDB connection string (local Docker or hosted Atlas URI). |
| `DB_NAME` | yes | Database name (e.g. `grimoire`). |
| `CORS_ORIGINS` | yes | Comma-separated allowed origins; set to your frontend URL in prod. |
| `JWT_SECRET` | yes | Secret used to sign JWTs. Generate a long random hex. |
| `ADMIN_EMAIL` | yes | Seed admin account email (created on startup). |
| `ADMIN_PASSWORD` | yes | Seed admin account password. |

### `frontend/.env`
| Variable | Required | Description |
|----------|----------|-------------|
| `REACT_APP_BACKEND_URL` | yes | Base URL of the backend (no trailing slash). Frontend calls `${REACT_APP_BACKEND_URL}/api/...`. |
| `WDS_SOCKET_PORT` | no | **Emergent-only**: hosted dev-server websocket port. Omit locally. |
| `ENABLE_HEALTH_CHECK` | no | **Emergent-only**: dev health probe. Omit locally. |

> **External services:** only **Scryfall** (`https://api.scryfall.com`, public, no
> API key) and **MongoDB**. There are no paid or keyed third-party integrations.

---

## Project Structure
```
.
├── backend/
│   ├── server.py            # FastAPI app: auth, Scryfall proxy, deck CRUD
│   ├── requirements.txt
│   ├── .env.example
│   └── tests/               # pytest API tests
├── frontend/
│   ├── src/
│   │   ├── pages/           # Landing, Login, Register, Dashboard, DeckBuilder, PublicDeck
│   │   ├── components/      # CardSearchBar, DeckBoard, DeckStats, Import/Export/Printings dialogs, ui/
│   │   ├── context/AuthContext.js
│   │   └── lib/             # api.js (axios), mtg.js (grouping/analytics helpers)
│   ├── craco.config.js
│   ├── .env.example
│   └── package.json
├── scripts/seed.py          # idempotent DB seed (indexes + admin + sample deck)
├── data/sample_deck.json    # sample deck document (data-model reference)
├── docker-compose.yml       # local MongoDB
├── docs/MIGRATION.md        # Emergent audit + what was removed
└── AGENTS.md                # instructions for AI coding assistants
```

---

## Data Model (MongoDB)

Database: value of `DB_NAME`. Two collections.

### `users`
| Field | Type | Notes |
|-------|------|-------|
| `_id` | ObjectId | Mongo internal id (not used by the API). |
| `id` | string (uuid) | App-level user id; referenced by `decks.user_id`. **unique index** |
| `email` | string | lowercased. **unique index** |
| `password_hash` | string | bcrypt hash. Never returned by the API. |
| `name` | string | Display name. |
| `created_at` | string (ISO 8601) | |

### `decks`
| Field | Type | Notes |
|-------|------|-------|
| `_id` | ObjectId | Mongo internal id. |
| `id` | string (uuid) | App-level deck id. **unique index** |
| `user_id` | string (uuid) | Owner → `users.id`. **index** |
| `share_id` | string (8 chars) | Public link token (`/d/:shareId`). **index** |
| `name` | string | |
| `format` | string | `standard`, `commander`, `modern`, `pioneer`, `pauper`, `legacy`, `vintage`, `kitchen`. |
| `description` | string | |
| `mainboard` / `sideboard` / `commander` | array of **DeckCard** | See below. |
| `created_at` / `updated_at` | string (ISO 8601) | |

### `DeckCard` (embedded sub-document)
`id` (Scryfall card id), `oracle_id`, `name`, `mana_cost`, `cmc`, `type_line`,
`oracle_text`, `colors[]`, `color_identity[]`, `rarity`, `set`, `set_name`,
`collector_number`, `image`, `art_crop`, `quantity`, and
`group_overrides` (object mapping a board grouping dimension → a chosen group,
e.g. `{"cmc": "0"}` to force a card into the "0" mana-value column).

**Relationships:** `decks.user_id` → `users.id`. Deck cards are embedded (no join).

### Recreating the data
`scripts/seed.py` recreates all indexes, the admin user, and loads
`data/sample_deck.json`. Point `MONGO_URL` anywhere (local or hosted) and run it.

---

## Available Scripts
- Frontend: `yarn start` (dev), `yarn build` (prod), `yarn test`.
- Backend: `uvicorn server:app --reload --port 8001`; tests: `pytest backend/tests`.
- DB: `docker compose up -d` / `down`; seed: `python scripts/seed.py`.

---

## What breaks if the old Emergent database is gone?
Nothing in the code — the app only needs *a* MongoDB reachable via `MONGO_URL`.
However, **the actual saved decks/users that lived in the Emergent-hosted
database do not travel with this code export.** Point `MONGO_URL` at your own
MongoDB and run `scripts/seed.py` to recreate the structure (and a sample deck).
To migrate real data, `mongodump` the old database and `mongorestore` into the new one.
