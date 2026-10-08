# Working on Grimoire

Notes for anyone (human or AI) changing this codebase. Start with the [README](README.md).

## Architecture

- **Frontend** (`frontend/`): React 19 + CRACO + Tailwind + shadcn/ui. Routes are in `src/App.js`, and auth
  state is in `src/context/AuthContext.js` (JWT in `localStorage`). All HTTP goes through `src/lib/api.js`,
  which prefixes `${REACT_APP_BACKEND_URL}/api` and attaches the token.
- **Backend** (`backend/server.py`): FastAPI, every route under `/api`. It handles auth, the Scryfall
  proxy, deck CRUD and the rotisserie draft engine. Mongo access is through Motor.
- **Card data** always comes from Scryfall via the backend proxy, never from the browser directly.

### Key files

| File | Purpose |
|------|---------|
| `frontend/src/pages/DeckBuilder.jsx` | Deck state, autosave, import / bulk edit / export / share dialogs |
| `frontend/src/components/DeckBoard.jsx` | View / group / sort toolbar, grouped columns, Command Zone, drag and drop |
| `frontend/src/components/CardSearchBar.jsx` | Search, autocomplete and add-to-deck |
| `frontend/src/components/ImportDialog.jsx` | Decklist parsing (Moxfield, MTGO, Arena, plain), commander detection |
| `frontend/src/components/ExportDialog.jsx` | Per-site export formats |
| `frontend/src/pages/DraftSetup.jsx`, `DraftRoom.jsx` | Cube import, lobby and live draft UI |
| `frontend/src/lib/mtg.js` | Mana parsing, grouping and sorting, analytics, format list |
| `frontend/src/components/CommanderCheck.jsx` | Commander legality + bracket panel and toolbar badge |
| `backend/commander.py` | Commander legality rules and bracket estimate (`POST /api/commander/check`) |
| `frontend/src/components/MyCubes.jsx`, `src/lib/cube.js` | Saved cubes (dashboard Cubes tab), cube list parsing and resolving (`/api/cubes`) |
| `backend/packdraft.py`, `backend/draftbot/packbot.py`, `frontend/src/components/PackDraftView.jsx` | Pack drafts: dealing/passing/timer logic, pack bots, picking UI |
| `backend/vrd.py` | VRD (every Vintage-legal card): legality rules and the bots' top-rated card pool (`vrd_pool` collection) |

## Conventions

- **API contract:** routes stay under `/api`. Responses are JSON objects (`{cards: [...]}`, `{drafts: [...]}`),
  never bare lists. Never return Mongo's `_id`.
- **Dates** are `datetime.now(timezone.utc).isoformat()` strings.
- **Config** comes only from environment variables. Never hard-code URLs, secrets or database names.
- **UI:** dark slate surfaces, amber primary actions, Outfit for headings and Inter for card data, and
  `lucide-react` icons (no emoji). Follow `design_guidelines.json`. Give interactive elements a kebab-case
  `data-testid`, and keep existing ones stable.
- **Scryfall:** send the `HEADERS` defined in `server.py`, batch `/cards/collection` calls at 75 identifiers,
  and pause about 100 ms between bursts.
- **Realtime:** drafts sync by polling `/api/drafts/{id}/state`. Moving to WebSockets is an architectural
  decision, not a quick fix.

## Workflow

- Branch `dev` deploys to staging and `main` deploys to production (see `docs/DEPLOYMENT.md`).
  Ship to `dev`, verify on staging, then promote.
- Keep `backend/requirements.txt` lean, since it is what the production image installs. Test tools go in
  `requirements-dev.txt`.
- The Docker image pins Python 3.11.9. Bumping Python or the pinned Mongo/bcrypt packages needs a staging
  deploy first.
- Discuss database schema or auth model changes before making them.
