# Deployment

Grimoire runs on [Render](https://render.com) with [MongoDB Atlas](https://www.mongodb.com/atlas):

| Environment | Branch | Backend (Docker web service) | Frontend (static site) | Database |
|-------------|--------|------------------------------|------------------------|----------|
| Production  | `main` | `grimoire-api`               | `grimoire-web`         | `grimoire` |
| Staging     | `dev`  | `grimoire-api-dev`           | `grimoire-web-dev`     | `grimoire_dev` |

Both environments share one Atlas cluster but use separate databases (`DB_NAME`), so staging never
touches production data. Render auto-deploys each service when its branch changes.

## Release workflow

1. Work lands on `dev`, and staging rebuilds automatically (about 5 minutes).
2. Check the change on the staging site.
3. Fast-forward `main` to `dev` (or merge a `dev` → `main` pull request), and production rebuilds.

## Database (MongoDB Atlas)

1. Create a cluster (the free M0 tier is fine) and a database user.
2. **Network Access:** allow `0.0.0.0/0`. Render's outbound IPs are dynamic.
3. Copy the SRV connection string (`mongodb+srv://user:password@cluster…/?retryWrites=true&w=majority`)
   as `MONGO_URL`. URL-encode the password if it contains `@ : / # %`. The database name comes from
   `DB_NAME`, not the URL.

## Backend web service

- **Runtime:** Docker, built from the repo-root `Dockerfile` (`python:3.11.9-slim`).
  Don't use Render's native Python runtime: the pinned `pymongo` / `motor` / `bcrypt` versions have no
  wheels for its default Python, and the service exits before uvicorn starts.
- **Health check path:** `/api/health` (returns `{"status":"ok"}`)
- **Environment:** `MONGO_URL`, `DB_NAME`, `JWT_SECRET` (unique per environment), and `CORS_ORIGINS`
  set to the matching frontend URL. `ADMIN_EMAIL` / `ADMIN_PASSWORD` are optional.

## Frontend static site

- **Root directory:** `frontend`
- **Build command:** `yarn install && yarn build`
- **Publish directory:** `build`
- **Environment:** `REACT_APP_BACKEND_URL` set to the matching backend URL (no trailing slash, no `/api`),
  `NODE_VERSION=20.18.0`, `NPM_CONFIG_LEGACY_PEER_DEPS=true`
- **Redirects/Rewrites:** `/*` → `/index.html` (Rewrite), so deep links like `/draft/abc123` work.

`REACT_APP_BACKEND_URL` is baked in at build time, so changing it needs a redeploy.

Production is defined as a Render Blueprint in [`render.yaml`](../render.yaml). Staging was created by hand
with the same settings.

## Notes

- Free Render services sleep when idle. The first request after a break takes 30–60 seconds, and an active
  draft keeps the backend awake through polling.
- Secrets live only in the Render dashboard. Nothing secret belongs in the repo.
