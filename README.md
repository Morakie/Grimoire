# Grimoire

A Magic: The Gathering deck builder and live rotisserie cube-draft app.

- **Deck building:** search the full card catalog (via [Scryfall](https://scryfall.com/docs/api)), build decks with
  drag-and-drop columns, and watch the mana curve, colors and type breakdown update as you go.
  Commander decks get a dedicated Command Zone.
- **Import / export:** paste lists from Moxfield, MTGO, Arena or plain text. Exact printings and commanders are
  detected automatically, and you can export back to any of those formats. Bulk edit lets you rewrite a whole list as text.
- **Sharing:** every deck can be shared as a read-only link, no account needed to view.
- **Rotisserie cube drafts:** import a cube from [CubeCobra](https://cubecobra.com), invite friends to a lobby, and
  draft in snake order with a pick queue, live pick feed, table chat, turn alerts and host undo/reassign tools.
  Cards default-sort by CubeCobra Elo.

## Tech stack

| Layer    | Tech |
|----------|------|
| Frontend | React 19, React Router, Tailwind CSS, shadcn/ui (Radix), dnd-kit, Recharts |
| Backend  | FastAPI, Motor (async MongoDB), PyJWT, bcrypt, httpx |
| Database | MongoDB |
| Card data | Scryfall REST API, proxied through the backend (no API key needed) |

Live draft state is synced by short-interval HTTP polling rather than WebSockets, which keeps hosting simple.

## Running locally

**Prerequisites:** Node 20 + Yarn 1, Python 3.11, and Docker (for a local MongoDB) or any MongoDB URL.

```bash
# 1. Database
docker compose up -d                      # MongoDB on localhost:27017

# 2. Backend  (http://localhost:8001)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                      # then set JWT_SECRET
uvicorn server:app --reload --port 8001

# 3. Frontend  (http://localhost:3000)
cd frontend
yarn install
cp .env.example .env
yarn start
```

Optional: `python scripts/seed.py` creates indexes, the seed account from `ADMIN_EMAIL` / `ADMIN_PASSWORD`,
and a sample deck.

### Tests

The backend tests are API tests that run against a live server:

```bash
cd backend
pytest                                    # targets http://localhost:8001 by default
REACT_APP_BACKEND_URL=https://<staging-api> pytest
```

Tests that log in use the seed account, so set `ADMIN_EMAIL` / `ADMIN_PASSWORD` to the same values as the server.

## Configuration

| Variable | Where | Required | Notes |
|----------|-------|----------|-------|
| `MONGO_URL` | backend | yes | `mongodb://…` or Atlas `mongodb+srv://…` |
| `DB_NAME` | backend | yes | e.g. `grimoire`, or `grimoire_dev` for staging |
| `JWT_SECRET` | backend | yes | long random string, unique per environment |
| `CORS_ORIGINS` | backend | no | comma-separated frontend URLs (defaults to `*`) |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | backend | no | seed account, created only when both are set |
| `REACT_APP_BACKEND_URL` | frontend | yes | backend base URL; no trailing slash, no `/api` |

The backend refuses to start with a clear error if a required variable is missing.

## Project layout

```
backend/
  server.py            API: auth, Scryfall proxy, decks, drafts
  data/card_elo.csv    CubeCobra Elo ratings used for default draft sorting
  tests/               API tests (pytest)
frontend/src/
  pages/               Landing, DeckBuilder, Dashboard, PublicDeck, DraftSetup, DraftRoom, auth
  components/          DeckBoard, CardSearchBar, Import/Export dialogs, stats, ui/ (shadcn)
  lib/                 api client, MTG helpers (mana, grouping, analytics)
docs/DEPLOYMENT.md     Render + MongoDB Atlas setup, staging workflow
design_guidelines.json Visual design reference
render.yaml            Render Blueprint for production
```

## Data model

MongoDB collections: `users`, `decks` and `drafts`. Deck cards are embedded in the deck document as
snapshots of Scryfall data, with `quantity` and optional per-view `group_overrides`. Indexes are created on
startup.

## Deployment

Production and staging both run on Render with MongoDB Atlas. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).
