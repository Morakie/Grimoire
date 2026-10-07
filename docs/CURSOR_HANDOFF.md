# Grimoire — Handoff for Cursor AI

> **Context for you (Cursor):** You have write access to this GitHub repo. The app
> is code-complete and was built/tested in a sandbox. The immediate goal is a
> **successful production deploy to Render + MongoDB Atlas**. This doc gives you
> everything: architecture, env vars, deploy steps, gotchas, and the current
> backlog. Read it top to bottom before touching code.

---

## 1. What Grimoire is
A full-stack **Magic: The Gathering (MTG) deck-builder, analyzer, and live cube-draft** app.

- **Card search/discovery** via the Scryfall API (no key needed).
- **Deck builder**: split-screen Mainboard / Sideboard / Commander, drag-to-reorder (`@dnd-kit`), printing/art switcher, quantity rules per format.
- **Analytics**: mana curve bar chart, color distribution, type breakdown (`recharts`).
- **JWT auth** + public deck share links (`/d/:shareId`).
- **Rotisserie Cube Draft**: live multiplayer via HTTP polling (~2s, no WebSockets), snake draft, multi-seat players, CubeCobra import, pick feed, table chat, host admin tools (undo/reassign), ELO-based default card sort.

## 2. Tech stack
| Layer | Tech |
|---|---|
| Frontend | React 19, CRACO, React Router, TailwindCSS, shadcn/ui, recharts, @dnd-kit, sonner, axios |
| Backend | FastAPI, Motor (async MongoDB), PyJWT, bcrypt, httpx |
| DB | MongoDB (Atlas in prod) |
| External | Scryfall REST API (card metadata/images) — **no API key** |
| Realtime | HTTP interval polling (deliberately no WebSockets, for simple hosting) |

## 3. Repo layout
```
/
├── backend/
│   ├── server.py            # ENTIRE backend: JWT auth, Scryfall proxy, deck CRUD, draft API, admin tools
│   ├── requirements.txt      # SLIM (14 deps) — do not re-bloat
│   ├── .python-version       # 3.11.9  (critical — see §6)
│   ├── runtime.txt           # python-3.11.9
│   ├── .env.example          # template for required env vars
│   ├── data/card_elo.csv     # CubeCobra ELO rankings for default draft sort
│   └── tests/                # pytest suite (76 tests, all pass)
├── frontend/
│   ├── src/
│   │   ├── lib/api.js        # axios instance; API = `${REACT_APP_BACKEND_URL}/api`
│   │   ├── lib/mtg.js        # MTG helpers (mana, colors, formats)
│   │   ├── components/       # DeckBoard, CardSearchBar, Draft Setup/Room UI
│   │   └── pages/            # Landing, DeckBuilder, DraftSetup, DraftRoom, PublicDeck, Login/Register, Dashboard
│   └── .env.example
├── .python-version           # 3.11.9 (root copy)
├── runtime.txt               # python-3.11.9 (root copy)
├── render.yaml               # Render Blueprint (2 services)
└── docs/RENDER_DEPLOYMENT.md  # full deploy guide
```

## 4. Environment variables (THE source of truth)
`.env` files are **git-ignored and NOT in the repo** — set these in the Render dashboard.

**Backend (`grimoire-api`)** — all read via `os.environ`; app fails fast with a clear message if a required one is missing:
| Key | Required | Notes |
|---|---|---|
| `MONGO_URL` | ✅ | Atlas SRV string: `mongodb+srv://user:pass@cluster0.xxx.mongodb.net/?retryWrites=true&w=majority` |
| `DB_NAME` | ✅ | e.g. `grimoire` |
| `JWT_SECRET` | ✅ | 64-char random hex (`python -c "import secrets;print(secrets.token_hex(32))"`) |
| `CORS_ORIGINS` | ⬜ (defaults `*`) | Comma-separated. Set to the frontend URL in prod. |
| `ADMIN_EMAIL` | ⬜ | Seed admin, default `admin@grimoire.gg` |
| `ADMIN_PASSWORD` | ⬜ | Seed admin, default `grimoire123` |
| `PYTHON_VERSION` | (set in render.yaml) | `3.11.9` |

**Frontend (`grimoire-web`)**:
| Key | Required | Notes |
|---|---|---|
| `REACT_APP_BACKEND_URL` | ✅ | Backend base URL, **no trailing slash, no `/api`**. Frontend appends `/api` itself. |

> `WDS_SOCKET_PORT` / `ENABLE_HEALTH_CHECK` seen in examples are Emergent-preview-only — ignore for Render.

## 5. Deploy to Render (Blueprint path — easiest)
1. **MongoDB Atlas**: create free M0 cluster → DB user+password → Network Access `0.0.0.0/0` (Render IPs are dynamic) → copy SRV connection string = `MONGO_URL`.
2. **Render → New → Blueprint** → connect this repo. It reads `render.yaml` and creates `grimoire-api` (web) + `grimoire-web` (static).
3. Fill the `sync: false` env vars (table above) → **Apply**.
4. **CORS ordering gotcha**: first deploy won't know final URLs. After both are live, set backend `CORS_ORIGINS` = real frontend URL and frontend `REACT_APP_BACKEND_URL` = real backend URL, then redeploy both.
5. **Verify**: `GET https://<api>.onrender.com/api/health` → `{"status":"ok"}`; frontend landing loads; admin login works.

Manual (non-Blueprint) settings are in `docs/RENDER_DEPLOYMENT.md` §3.

## 6. CRITICAL GOTCHAS (these already bit us once)
1. **Python version** — Render defaults to **3.14**, which has no wheels for the pinned `pymongo==4.6.3` / `pydantic==2.13.5` → backend exits with **status 3** on start. Fixed by pinning **3.11.9** in `.python-version` + `runtime.txt` + `render.yaml` `PYTHON_VERSION`. **Do not remove these.** If you bump deps, either keep 3.11 or move to versions with 3.13/3.14 wheels and test.
2. **`mongodb+srv://` needs `dnspython` + `certifi`** — both are in `requirements.txt`. Removing them breaks Atlas connections.
3. **requirements.txt is intentionally slim (14 pkgs).** It was trimmed from ~100 sandbox packages to speed up Render builds. Only `server.py` imports: fastapi, uvicorn, starlette, motor/pymongo, bcrypt, PyJWT, httpx, pydantic, email-validator, python-dotenv, python-multipart (+ dnspython, certifi). Don't re-add unused heavy deps (litellm/openai/pandas/etc.).
4. **All routes are prefixed `/api`** (via `APIRouter(prefix="/api")`). The frontend always calls `${REACT_APP_BACKEND_URL}/api/...`. Keep this contract.
5. **Free Render web services sleep after inactivity** → first request ~30–60s cold start. Draft polling (2s) keeps active sessions warm.
6. **Env vars fail fast**: `server.py` has a `_require_env()` helper (top of file) that raises a readable `RuntimeError` if MONGO_URL/DB_NAME/JWT_SECRET are missing. If the service won't boot, check the logs for that message first.

## 7. Key API endpoints
- Auth: `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`
- Cards: `GET /api/cards/search`, `GET /api/cards/printings`
- Decks: `POST /api/decks`, `GET /api/decks`, `GET /api/decks/{id}`, `PUT /api/decks/{id}`, `DELETE /api/decks/{id}`, clone, public share (`/d/:shareId`)
- Drafts: `POST /api/drafts`, `GET /api/drafts/open`, `GET /api/drafts/{id}/state`, `POST /api/drafts/{id}/pick`, `POST /api/drafts/{id}/chat`, `POST /api/drafts/{id}/undo`, `POST /api/drafts/{id}/reassign`
- Health: `GET /api/health`

**Payload quirks (from tests):** deck cards use field `id` (not `card_id`); draft create uses `num_players`/`num_seats` (not `players`/`seats`); `/api/cards/search` returns `{cards:[]}`; `/api/drafts/open` returns `{drafts:[]}`.

## 8. DB schema (MongoDB)
- `users`: `{ id, email, password_hash, name, created_at }` — unique index on `email` and `id`.
- `decks`: `{ id, user_id, name, cards[], is_public, share_id, ... }` — indexes on `id` (unique), `share_id`, `user_id`.
- `drafts`: `{ id, host_id, share_id (unique), status, seats_per_player, players[], cube[], picks[], messages[] }`.
Indexes + admin seeding run in the FastAPI `startup` event in `server.py`.

## 9. Tests & local dev
```bash
# Backend
cd backend && pip install -r requirements.txt
cp .env.example .env   # fill MONGO_URL/DB_NAME/JWT_SECRET
uvicorn server:app --host 0.0.0.0 --port 8001
pytest                 # 76 tests; they hit REACT_APP_BACKEND_URL or default http://localhost:8001

# Frontend
cd frontend && yarn install
cp .env.example .env    # set REACT_APP_BACKEND_URL=http://localhost:8001
yarn start              # CRACO dev server on :3000
yarn build              # production build -> build/
```
Test admin: `admin@grimoire.gg` / `grimoire123` (override via ADMIN_EMAIL/ADMIN_PASSWORD).

## 10. Current state & backlog
**Done & verified in sandbox (76/76 backend tests, full frontend e2e earlier):** auth, deck CRUD + share, Scryfall search, analytics, full rotisserie draft (chat, pick feed, queue, table peek, multi-seat, ELO sort, host undo/reassign), Render config + Python pinning + Emergent-reference scrub.

**What was NOT verifiable in the sandbox (needs you to confirm on Render):**
- The Python-3.11 pin actually resolving the status-3 crash on Render.
- Atlas connectivity end-to-end from Render.
- CORS between the two deployed URLs.

**Backlog (priority order):**
- **P1** Format legality validation (flag illegal/over-limit cards per format).
- **P2** Card details pane with Scryfall rulings/oracle text.
- **P2** Brute-force login lockout; richer deck text import/export validation.
- **P2** Collection/ownership tracking; advanced Scryfall filters in UI (set, rarity, cmc range).
- **P3** Additional draft formats (standard cube, booster pack).
- **Tech-debt** `server.py` is ~733 lines; consider splitting into `routers/` (auth, cards, decks, drafts) — optional, not blocking.

## 11. First tasks for you (Cursor), in order
1. Confirm the repo has: `backend/.python-version`, `backend/runtime.txt`, root `.python-version`, root `runtime.txt`, `render.yaml` with `PYTHON_VERSION=3.11.9`, slim `backend/requirements.txt`. (All committed by the previous agent.)
2. Deploy via Render Blueprint, set env vars (§4), fix CORS ordering (§5.4).
3. Hit `/api/health`, log in as admin, create a deck, open a draft lobby — smoke test.
4. If the backend still exits status 3, read the start log for the `_require_env` message (missing var) vs a wheel/build error (Python version) and act per §6.
5. Then pick up the P1 backlog item (format legality).
