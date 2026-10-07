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

## Backlog / Remaining
- P2: Draft pool card-image fallback polish (DONE — now uses art_crop/name); cosmetic pytest return-not-None warning.
- P2: Additional draft formats (standard cube, booster pack).
- P2: PrintingsDialog full integration into visual grid (change displayed art Moxfield-style).
- P2: Brute-force login lockout; format legality validation; card detail view with rulings.
- P2: Collection tracking / ownership; advanced Scryfall filters (set, rarity, cmc range in UI).

## Test Credentials
- Admin: admin@grimoire.gg / grimoire123
- See `/app/memory/test_credentials.md`
