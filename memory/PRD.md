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

## Backlog / Remaining
- P1: Draft systems (cube, booster pack, rotisserie drafting).
- P2: Brute-force login lockout; format legality validation; deck import/export (text); card detail view with rulings.
- P2: Collection tracking / ownership; advanced Scryfall filters (set, rarity, cmc range in UI).

## Test Credentials
- Admin: admin@grimoire.gg / grimoire123
- See `/app/memory/test_credentials.md`
