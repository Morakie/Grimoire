# AGENTS.md — Guide for AI Coding Assistants

This file orients any AI coding tool working on **Grimoire**. Read it fully
before making changes.

## 1. Project summary & goals
Grimoire is a fast, modern web app for Magic: The Gathering players to build,
optimize, and organize decks. Target feature set:
- **Scryfall card search** by name, color, card type, set, and mana cost, shown
  in a responsive grid with card art, oracle text, mana symbols, and (where
  surfaced) price.
- **Split deck builder**: a find-&-add search bar at the top, deck board below
  with **Mainboard**, **Sideboard** (15 max), and **Commander** sections,
  quantity controls (max 4 copies except basic lands), and quick-add buttons.
- **Analytics**: mana curve (CMC 0→7+), color distribution, and stats (card
  count, average CMC, estimated USD value, card-type breakdown).
- **Accounts**: sign-up/login, a **My Decks** dashboard (view, create, edit,
  clone, delete), and **public shareable deck links**.

## 2. Design rules
- Deep dark **slate-900** theme; **neon mana-color** accents; subtle 1px borders.
- **Gold/amber** primary buttons (`bg-amber-400`, hover `bg-amber-500`, text `stone-900`).
- Smooth hover and drag states; fully mobile-friendly; left-aligned dense data.
- Headings use `Outfit`, body uses `Inter`. Avoid emoji icons — use `lucide-react`.
- Every interactive element gets a `data-testid` (kebab-case).

## 3. Architecture overview
- **Frontend** (`frontend/`): React 19 + CRACO + Tailwind + shadcn/ui. Routing in
  `src/App.js`. Auth state in `src/context/AuthContext.js` (JWT in `localStorage`
  key `grimoire_token`). Axios instance in `src/lib/api.js` injects the bearer token.
- **Backend** (`backend/server.py`): FastAPI, all routes under `/api`. Responsibilities:
  JWT auth, a **Scryfall proxy**, and deck CRUD. Mongo access via Motor.
- **Database**: MongoDB, collections `users` and `decks` (see README "Data Model").

### Key files
| File | Purpose |
|------|---------|
| `backend/server.py` | Auth (`/api/auth/*`), Scryfall proxy (`/api/cards/search|autocomplete|printings|collection`), deck CRUD (`/api/decks*`), startup seeding + indexes. |
| `frontend/src/pages/DeckBuilder.jsx` | Core builder; owns deck state, add/qty/remove, autosave, import/export/share dialogs, guest-save gate. |
| `frontend/src/components/CardSearchBar.jsx` | Top find-&-add bar: autocomplete, search results dropdown, add-to target. |
| `frontend/src/components/DeckBoard.jsx` | View/Group/Sort toolbar + grouped columns + @dnd-kit drag/drop (incl. `group_overrides`). |
| `frontend/src/components/DeckStats.jsx` | Recharts mana curve, color donut, type breakdown. |
| `frontend/src/lib/mtg.js` | Mana parsing, grouping/sorting, analytics helpers, format list. |

### Data flow
UI → `src/lib/api.js` (axios, adds JWT) → FastAPI `/api/...` → Motor → MongoDB.
Card data comes from Scryfall via the backend proxy (never called directly from
the browser), so headers/caching stay server-side.

## 4. Coding conventions
- Frontend: functional components; named exports for components, default export for
  pages. Reuse `src/components/ui/*` (shadcn). Toasts via `sonner`.
- Backend: keep all routes under `/api`; use Pydantic models; `datetime.now(timezone.utc)`
  and store ISO strings; never return raw Mongo `_id`.
- Config comes only from environment variables — never hardcode URLs, secrets, or DB names.

## 5. Scryfall usage rules
- Always send `User-Agent: GrimoireDeckBuilder/1.0` and `Accept: application/json`
  (see `HEADERS` in `server.py`).
- Add a short delay (~50–100 ms) between bursts of requests; the bulk
  `/api/cards/collection` endpoint already chunks identifiers at 75 (Scryfall's limit).
- Cache results where sensible. Do not call Scryfall from the browser — proxy via the backend.

## 6. How to run / build / lint / test
```bash
# Database
docker compose up -d

# Backend
cd backend && pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
pytest backend/tests                      # API tests (set REACT_APP_BACKEND_URL or default localhost)

# Frontend
cd frontend && yarn install
yarn start                                # dev
yarn build                                # production build (run this after changes)
```

## 7. Working rules for the AI
- Make **small, incremental** changes. **Do not rewrite** working code wholesale.
- **Run `yarn build`** (and relevant tests) after changes; fix what you break.
- **Never commit secrets.** `.env` is gitignored; use `.env.example` for new vars.
- **Ask before** changing the database schema or the auth model.
- Preserve existing `data-testid`s (automated tests depend on them).

## 8. Known issues & prioritized TODO
1. **Estimated USD value** is intentionally not displayed yet. Scryfall `prices`
   are fetched and stored on each card (`DeckCard.prices` via `map_card`), so
   surfacing a deck total in `DeckStats.jsx` is a small addition.
2. **Set / collector / mana-cost filters** exist in search only as color + type;
   the problem statement also mentions set and mana-cost filters — extend
   `CardSearchBar` + `/api/cards/search`.
3. **DFC name collision on import**: a double-faced card whose back face shares a
   name with a standalone card can collapse during bulk resolve in
   `ImportDialog`/`/api/cards/collection`. Edge case; dedupe by Scryfall `id`.
4. **No automated frontend tests** checked in (backend has pytest). Consider
   Playwright for the builder flows.
5. **No rate-limit/backoff** around Scryfall beyond chunking — add a small delay
   and simple caching if usage grows.
6. `TODO(emergent-removal)`: none outstanding — all Emergent-specific code was
   removed cleanly (see `docs/MIGRATION.md`). If any reappears, mark it with this tag.
