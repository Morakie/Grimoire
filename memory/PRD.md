# Grimoire — MTG Deck Builder & Analyzer

## Original Problem Statement
Full-stack web app "Grimoire": a fast, modern Magic: The Gathering deck-builder and analyzer with real-time Scryfall card data, mana curve visualizations, collection analytics, JWT auth, saved decks, and public share links.

## User Choices
- Auth: JWT email/password (custom)
- Formats: Standard, Commander/EDH, Modern, Pioneer, Pauper, Legacy, Vintage, + "Kitchen Magic" (no rules). (Drafting systems — cube/booster/rotisserie — are a future consideration.)
- Public share links: anyone with the link can view
- Card art switching across printings (Moxfield-style)
- Design: sleek/minimal modern dark theme (slate-900, neon mana accents, gold/amber actions)
- Market value: NOT displayed

## Architecture
- Backend: FastAPI (`/app/backend/server.py`), MongoDB (motor), JWT Bearer auth (bcrypt + pyjwt), Scryfall proxy via httpx.
- Frontend: React 19, react-router, Tailwind + shadcn/ui, recharts (charts), @dnd-kit (drag-reorder), sonner (toasts). Fonts: Outfit (display) + Inter (body).
- Auth token in localStorage key `grimoire_token`, sent via Authorization header.

## Core Requirements (static)
1. Scryfall card search (name/color/type) with high-res art grid + mana symbols.
2. Split-screen deck builder: Mainboard / Sideboard / Commander, quick-add, drag-to-reorder, quantity rules (max 4, basics unlimited, commander singleton, kitchen unlimited).
3. Analytics: mana curve bar chart, color distribution donut, stats (total cards, avg CMC, type breakdown).
4. JWT auth, My Decks dashboard (create/edit/clone/delete), public share at `/d/:shareId`, printing/art switcher.

## Deployment (2026-06-09)
- Render deploy prepared: `render.yaml` (Blueprint) + `docs/RENDER_DEPLOYMENT.md` guide.
- Slimmed `backend/requirements.txt` from ~100 base-env packages to 14 essentials (kept `dnspython`+`certifi` for Atlas `mongodb+srv://`). Backend verified healthy post-change.
- Fixed Render status-3 start crash: pinned Python 3.11.9 via `.python-version` + `runtime.txt` (root + backend) + `PYTHON_VERSION` env in render.yaml (Render was defaulting to 3.14 → no wheels for pinned pymongo/pydantic).
- Hardened `server.py` startup: bare `os.environ[...]` replaced with `_require_env()` → human-readable RuntimeError listing required keys (MONGO_URL, DB_NAME, JWT_SECRET) instead of silent KeyError.
- Emergent-reference audit: `.env` files are git-ignored (NOT shipped) so the Emergent preview URL never reaches GitHub; frontend reads `process.env.REACT_APP_BACKEND_URL`; `.env.example` files are Render-ready; cleaned the lone test fallback URL. Only `docs/MIGRATION.md` mentions Emergent (intentional migration notes).
- Regression: 76/76 backend tests pass (iteration_13). Python pinning + env fail-fast can only be validated on Render itself.

## Implemented (2026-06-06)
- JWT auth: register/login/me; admin seeding; MongoDB indexes.
- Scryfall proxy: `/api/cards/search`, `/api/cards/printings`.
- Deck CRUD: create/list/get/update/delete/clone + public share endpoint.
- Frontend: Landing, Login, Register, Dashboard, DeckBuilder (split-screen, target switcher, autosave + manual save, share dialog, printings/art dialog, drag-reorder, live stats sidebar + mobile stats sheet), PublicDeck (read-only).
- Tested: 18/18 backend pytest pass; full frontend e2e pass (100%).

## Implemented (2026-06-15) — Rotisserie Cube Draft + Render prep
- Rotisserie Cube Draft module: `POST /api/drafts` (even-seat validation), `/claim` (name/token, even seat split), `/start` (gated until all seats claimed, snake order + double-draft boundary), `/pick` (server-authoritative turn/seat/card checks), `/state` (light poll), `/cube/cubecobra` import.
- DraftSetup page (host: name/players/seats/picks/double, CubeCobra link or paste/upload list) → creates draft → shareable `/draft/:shareId` link.
- DraftRoom (2s HTTP polling, no WebSockets): lobby claim, live seat grid, drafting pool with filter, complete view with export + "Edit in builder".
- **P0 FIX (iter 6, verified 2-browser)**: lobby live-sync — seat grid + Start gate now read from polled `state.seats` (was stale `draft.seats`). Players now see each other join without refresh.
- Landing page: "Start drafting" CTA (`hero-draft-cta`) + live "Open draft lobbies" browser polling `GET /api/drafts/open` every 5s with join buttons.
- `GET /api/health` → {status:ok}. Render deploy: `/app/render.yaml` (Blueprint: Python web service + static site) + `/app/docs/RENDER_DEPLOYMENT.md` (MongoDB Atlas setup, env vars, CORS).
- Tested: 38/38 backend pytest; frontend P0 live-sync + landing draft flows 100%.

## Implemented (2026-06-16) — Draft UX deepening + deck-builder fixes
- Landing: open-lobby browser removed; "Start drafting" CTA kept. Lobby browser + "Host your own" now live on /draft (DraftSetup); host close/cancel table (`host_token`); stale lobbies (>12h) & started/cancelled drafts excluded from `/drafts/open`.
- Draft room: sticky header + visible lobby invite link/table-code; seat spread fix (join-index modulo → no player holds both snake-end seats); seat tiles show each seat's last pick; turn notification beep (WebAudio) + mute toggle; default pool sort = CubeCobra ELO ("Rank", from backend `data/card_elo.csv`); Pick/Draft Table/Decks view switcher; hover card preview; confirm-pick dialog; sort (Rank/Name/Color/Type/CMC) + hide-picked (picked stays greyed); visual pick feed w/ seat labels; multi-seat "Name (Seat N)"; Draft Table grid (color-coded, snake arrows) + mini-table popout; per-seat Decks viewer w/ selector.
- Pick QUEUE: bookmark cards → bottom-left collapsible/expandable widget; reorder/remove; auto-picks top still-available queued card on every turn (continuous effect — fixes multi-round/wheel-back), skips cards taken by others.
- Deck builder: Back button → navigate(-1); Mana Value grouping separates Lands + always renders 0..7+ columns as drop targets; Custom/Manual = 8 header-less columns; Color grouping sub-sorts by type→CMC; card search & printings use earliest-print ordering (printings), search reverted to relevance.
- Render deploy: render.yaml + docs/RENDER_DEPLOYMENT.md (MongoDB Atlas); GET /api/health.
- Tested: backend pytest 36/36; frontend iter6–10 all green (incl. multi-round auto-pick).

## Implemented (2026-06-16b) — Queue polish, draft-table peek, host admin tools
- Pick queue: left-hand column (non-expanding, grows with list) + per-card bookmark; auto-pick now a continuous effect (fixes multi-round/wheel-back), skips taken cards.
- Draft-pool Color sort now sub-sorts by card type → mana value within each color.
- "Table peek": large popout overlay of the full Draft Table that covers the pick screen (closeable via button or backdrop) for quick glances while picking.
- Host-only ADMIN tools (gated by host_token): `POST /drafts/{id}/undo` (removes last pick, returns card to pool, status→drafting, repeatable) with header "Undo pick" button; `POST /drafts/{id}/reassign` (swap any pick to a still-available card) via click-a-cell reassign dialog in the Draft Table. Non-hosts cannot see/use them. 403/404/400/409 validation.
- Tested: backend pytest 68/68; frontend iter11–12 all green.

## Backlog / Remaining
- P2: Draft pool card-image fallback polish (DONE — now uses art_crop/name); cosmetic pytest return-not-None warning.
- P2: Additional draft formats (standard cube, booster pack).
- P2: PrintingsDialog full integration into visual grid (change displayed art Moxfield-style).
- P2: Brute-force login lockout; format legality validation; card detail view with rulings.
- P2: Collection tracking / ownership; advanced Scryfall filters (set, rarity, cmc range in UI).

## Test Credentials
- Admin: admin@grimoire.gg / grimoire123
- See `/app/memory/test_credentials.md`
