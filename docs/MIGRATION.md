# MIGRATION.md — Emergent → Standalone Export

This document records the audit of Emergent-platform dependencies and everything
removed or changed to make Grimoire run anywhere.

## 1. Audit (what depended on Emergent)

| Area | Finding | Platform-dependent? |
|------|---------|---------------------|
| Database | Standard **MongoDB** via `MONGO_URL` (Motor). Not an Emergent-managed DB. | No (just needs any MongoDB) |
| Auth | **Custom JWT** (email/password, bcrypt). No Emergent/managed auth, no OAuth. | No |
| Integrations / LLM keys | **None.** No Emergent LLM key, no `emergentintegrations` usage in app code. | No |
| Preview URL | `frontend/.env` `REACT_APP_BACKEND_URL` pointed at a `*.preview.emergentagent.com` host. | Yes — now env-driven; `.env.example` uses `http://localhost:8001`. |
| Frontend branding | `public/index.html` had `<title>Emergent | Fullstack App</title>`, `description "A product of emergent.sh"`, an `assets.emergent.sh/scripts/emergent-main.js` script, and a **PostHog** analytics snippet pointing at `ap.emergent.sh`. | Yes — removed. |
| Build tooling | `@emergentbase/overlay` and `@emergentbase/visual-edits` dev packages, wired in `craco.config.js` (dev-only error overlay + visual editor). | Yes — removed. |
| Dev env vars | `WDS_SOCKET_PORT=443`, `ENABLE_HEALTH_CHECK=false` in `frontend/.env`. | Yes — Emergent-only; documented as optional, omitted from `.env.example`. |
| Test id constant | `home.js` exported `home-emergent-link` (old splash link, unused). A comment in `auth.js` referenced an `emergent(...)` lint rule. | Cosmetic — cleaned. |
| Backend test default | `backend/tests/test_grimoire_api.py` defaulted `REACT_APP_BACKEND_URL` to the preview URL. | Changed default to `http://localhost:8001`. |
| Runtime infra | App is normally run by **supervisor** behind a **Kubernetes ingress** that routes `/api` to the backend. | Platform infra — replaced by the documented `uvicorn` + CRA/CRACO dev servers and `docker-compose` for Mongo. |

### Environment variables & external services
- Backend: `MONGO_URL`, `DB_NAME`, `CORS_ORIGINS`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`.
- Frontend: `REACT_APP_BACKEND_URL` (+ optional Emergent-only `WDS_SOCKET_PORT`, `ENABLE_HEALTH_CHECK`).
- External services: **Scryfall API** (public, no key) and **MongoDB**. Nothing else.

## 2. What was removed / changed

| File | Change |
|------|--------|
| `frontend/public/index.html` | Removed Emergent title/description meta, the `emergent-main.js` script tag, and the entire PostHog analytics block. Rebranded title/description to Grimoire. (The stock Emergent splash screen in `App.js` was already replaced by the real app during development.) |
| `frontend/package.json` | Removed `@emergentbase/overlay` and `@emergentbase/visual-edits` from `devDependencies`; lockfile regenerated via `yarn`. |
| `frontend/craco.config.js` | Removed the `@emergentbase/overlay` loader and the `@emergentbase/visual-edits` wrapper and their dev-server wiring. Kept the `@`→`src` alias, eslint config, watch options, optional health-check hook, and the webpack-dev-server v5 compatibility shim. Builds with no Emergent packages present. |
| `frontend/src/constants/testIds/home.js` | Removed the unused `home-emergent-link` test id (now `export const HOME = {}`). |
| `frontend/src/constants/testIds/auth.js` | Reworded a comment that named an `emergent(...)` lint rule. |
| `backend/tests/test_grimoire_api.py` | Default base URL changed from the `*.preview.emergentagent.com` host to `http://localhost:8001`. |
| `frontend/.env.example`, `backend/.env.example` | Added, documenting every variable with placeholders; Emergent-only vars flagged as optional. |
| `.gitignore` (root) | Added explicit `.env` / `**/.env` exclusions (keeping `.env.example`) so secrets are never committed. |
| `docker-compose.yml`, `scripts/seed.py`, `data/sample_deck.json` | Added for portable local DB + reproducible seed data. |
| `README.md`, `AGENTS.md`, `docs/MIGRATION.md` | Added documentation. |

> Note: `backend/requirements.txt` still lists `emergentintegrations`. It is a
> leftover from the base template and is **not imported anywhere** in the app. It
> is left untouched to avoid changing the backend dependency set; it can be
> removed safely if desired (the app does not use it).

## 3. Still needs attention (priority order)
1. **Fill in secrets** in `backend/.env` (`JWT_SECRET`, admin creds) and point
   `MONGO_URL` at your database. Set `REACT_APP_BACKEND_URL` in `frontend/.env`.
2. **Migrate real data** (optional): `mongodump` from the old Emergent DB and
   `mongorestore` into your new MongoDB. The code export does not carry data.
3. **Optional cleanup**: drop the unused `emergentintegrations` line from
   `backend/requirements.txt`.
4. **Feature gaps** (see `AGENTS.md` TODO): surface estimated USD deck value,
   add set/mana-cost search filters, and harden DFC import dedupe.

## 4. `TODO(emergent-removal)` markers
None outstanding. Every Emergent-specific item was removed cleanly without
guessing at replacements (auth and database were already standard, so nothing had
to be stubbed).
