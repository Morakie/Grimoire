# Deployment

Grimoire runs on [Render](https://render.com) with [MongoDB Atlas](https://www.mongodb.com/atlas):

| Environment | Branch | Backend (Docker web service) | Frontend (static site) | Database |
|-------------|--------|------------------------------|------------------------|----------|
| Production  | `main` | `grimoire-api`               | `grimoire-web`         | `grimoire` |
| Staging     | `dev`  | `grimoire-api-dev`           | `grimoire-web-dev`     | `grimoire_dev` |

Both environments share one Atlas cluster but use separate databases (`DB_NAME`), so staging never
touches production data. Render auto-deploys each service when its branch changes.

## Run your own copy

To stand up an independent instance (for testing, or a fork), you need a GitHub fork, a free MongoDB Atlas
cluster and a free Render account. Nothing is shared with the original deployment. About 20 minutes,
most of it waiting on the first build.

1. **Fork** the repo on GitHub.
2. **Database:** create an Atlas cluster and user as described under [Database](#database-mongodb-atlas) below,
   and copy the SRV connection string.
3. **Deploy the Blueprint:** in Render, *New → Blueprint*, pick your fork and branch. Render reads
   [`render.yaml`](../render.yaml) and creates two services, `grimoire-api` and `grimoire-web`
   (rename them in the dashboard if you like). `JWT_SECRET` is generated for you.
4. **Fill in the prompted variables** (Render asks for the `sync: false` ones):
   - `MONGO_URL`: your Atlas SRV string.
   - `REACT_APP_BACKEND_URL` on the frontend: the backend's `https://….onrender.com` URL
     (no trailing slash, no `/api`).
   - `CORS_ORIGINS` on the backend: the frontend's `https://….onrender.com` URL.
   - `ADMIN_EMAIL` / `ADMIN_PASSWORD`: optional seed login. Leave blank and just register in the app.

   The two URLs aren't known until the services exist, so it's fine to set them after the first deploy.
   Then redeploy the frontend, because `REACT_APP_BACKEND_URL` is baked in at build time.
5. **Check it:** `https://<your-api>/api/health` should return `{"status":"ok"}`, and the frontend should
   let you register, build a deck and start a draft.

Optional, for a throwaway test instance only:

| Variable | Effect |
|----------|--------|
| `ENABLE_BOT_SIM=true` | Turns on `POST /api/bots/simulate`, a bot-only draft for tuning (see [DRAFT_BOTS.md](DRAFT_BOTS.md)). |
| `BOT_DELAY_SCALE=1` | Draft bots pause 0.8–1.7 s before each pick (default `0`: instant). |

Don't set either on a site real people draft on.

**Troubleshooting**

- *Frontend loads but every request fails:* `REACT_APP_BACKEND_URL` is wrong or the frontend wasn't
  redeployed after setting it, or `CORS_ORIGINS` doesn't match the frontend URL exactly (scheme included).
- *Backend exits on boot:* the log names the missing variable. A Mongo timeout means Atlas Network Access
  doesn't allow `0.0.0.0/0`.
- *Deep links 404:* the static site is missing the `/*` → `/index.html` rewrite.
- *First request hangs ~a minute:* free Render services sleep when idle. That's normal.

To run everything on your own machine instead, see [Running locally](../README.md#running-locally).

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
