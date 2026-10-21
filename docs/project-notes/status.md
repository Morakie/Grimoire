# Status and how things run (as of 2026-10-20)

## Environments

| | Production | Staging |
|---|---|---|
| Branch | `main` | `dev` |
| Web | https://mtg-grimoire.dev | https://grimoire-web-dev.onrender.com |
| API | https://api.mtg-grimoire.dev | https://grimoire-api-dev.onrender.com |
| Render plan | Starter (paid, always on) | Free (sleeps when idle, slow CPU) |
| MongoDB Atlas | its own cluster | its own free cluster (separate since 2026-10-14) |

- Production services are a Render Blueprint (`render.yaml`). A sync resets each service to the file, so change
  plans and settings in the file, not only in the dashboard (the API once kept dropping back to the free plan
  because the file said so).
- DNS is on Cloudflare. The `api` record is proxied; going straight to Render is ~200 ms faster per request.
  Ask the owner before changing it.
- Staging-only environment variables: `ENABLE_BOT_SIM=true`, `BOT_DELAY_SCALE=0`. Never set them on production.
- The first VRD table on production builds the VRD card pool in the background (~30 s), cached in Mongo
  `vrd_pool` for a month.

## Shipping

- Work goes to `dev` first (deploys staging), gets checked there, then a PR from `dev` to `main`.
- Merge to `main` only when the owner says so explicitly. A production deploy restarts the live API for about a
  minute, which pauses live drafts: ship when nobody is drafting.
- Every push to `dev` restarts the staging API for about a minute; warn whoever is testing there first.
- A Render redeploy takes about 60 s (120 s at most).
- Staging test data is named "Test …" (cubes, decks, drafts). Don't put AI tool names in anything users can see
  (test data, UI text); commit attribution is fine.

## What's live

- Production (2026-10-20, PR #18): rotisserie cube drafts with bots, pack drafts, VRD, mirror tables, bot
  report, Bot Lab in the draft room, commander tools, deck builder, saved cubes.
- On `dev` / staging only: Bot Brain page (`/bots`) with saved pools, the bots running in the browser, live
  re-drafts, lanes table and synergy web; combined cubes ("A + B"); cube lists over 800 cards; Commander
  Spellbook combos for big cubes in batches. See [bot-brain.md](bot-brain.md).

## Owner decisions (keep unless the owner changes them)

- Hobby project for a playgroup, free, no paid services for users.
- Responsiveness is a top priority: load big data sets only when a format needs them, never repeatedly.
- The group plays LSV-style cube rotisserie ("Kitchen Magic"): ~40-card decks, nothing enforced, basic lands
  come from outside the draft. VRD uses Vintage-legal paper cards.
- Pick suggestions are off by default, only shown when the lightbulb is clicked, always three picks.
- Bots pick instantly. Pick timers only for pack drafts.
- Pack drafts: shrinking timer by default, picks hidden, no draft table or pick feed.
- Deck price: small, at the bottom of the deck builder. Saved cubes are private to each user.
- Mirror tables copy a draft running elsewhere, pick by pick, for analysis only (nobody drafts live there), so
  production merges don't need to wait for them. The host picks for every seat; suggestions only for their own.
- Hosting may move to DigitalOcean or similar later if online play (XMage) goes ahead.

## Limits of an AI working in a cloud sandbox

Cloud sessions often can't reach staging, production, CubeCobra or Scryfall from their shell. Pure-Python bot
tests run without dependencies (`backend/tests/test_draftbot.py`); frontend syntax can be checked with esbuild.
End-to-end checks happen in a browser on the owner's computer.
