# Bot Brain and Bot Lab: tuning the bots (as of 2026-10-20)

## The tools

- **Bot Lab** (production): in a rotisserie draft room, "Bot Lab" shows any pick as the engine scores it, each
  score split into parts, with sliders to try other weights on that view only.
- **Bot report** (production): `GET /api/drafts/{id}/bot-report` ranks every real pick by today's engine.
- **Bot Brain** (`/bots`, staging only so far): load a cube or the VRD pool, look up any card (roles, deck types,
  partners, combos, link graph), or simulate an all-bot draft and tune it.

## How Bot Brain works

- Pools: building one reads CubeCobra stats for every card and asks Commander Spellbook for combos, then saves the
  pool as one gzip'd document in Mongo `lab_pools` (`GET /api/lab/pools` lists them). Rebuild only on request.
- The bots run in the browser: `frontend/src/lib/labEngine.js` starts a Web Worker with Pyodide (Python in
  WebAssembly) and loads the server's own `backend/draftbot/*.py` from `GET /api/lab/engine`, so the browser runs
  exactly the live bots' code. The pool comes from `GET /api/lab/pool-export?key=...` once and is kept in
  IndexedDB until it's rebuilt. `backend/draftbot/browser.py` is the worker's entry point. If the worker can't
  start, the page uses the server endpoints (`/api/lab/source|card|simulate|view`).
- Drafts are deterministic: each pick has its own random stream from the seed (`lab._pick_rng`), so the same
  seed and weights give the same draft, and a re-draft from pick N reproduces every earlier pick.
- The page drafts with the current weights first ("base"), then re-drafts the same seed with the Lab's weights
  from a chosen pick, live as sliders settle. Changed picks are outlined; seat summaries compare with base; a
  lanes table shows each seat's deck types at the pick shown (3+ seats in a lane flagged); the synergy web shows
  the picking seat's cards, the cards it's weighing and the CubeCobra links between them.
- "Copy" in the weights panel gives the changed weights as JSON to bake into `TUNING`.

## Speed

- Simulations and the bot report share a `memo` through `BotContext` (each seat's deck types and each rival's
  view for float risk, reused until that seat picks again). Picks are identical with or without it
  (`test_shared_memo_never_changes_a_pick`). Live drafts don't use it (host undo can shrink picks).
- Measured 2026-10-20: 8 bots x 45 picks on the 903-card group cube + PowerLSV pool takes under 8 s in the
  browser; a live re-draft from pick 101 about 6 s. Browser picks matched the server's exactly (same seed).

## Testing a bot change

1. `backend/tests/test_draftbot.py` (pure Python; runs without the server's dependencies).
2. Same seed before/after in Bot Brain: count changed picks, seat deck types, crowded lanes, seats with no
   deck type.
3. Replay a real draft from its bot-inputs export and compare agreement with people's picks and per-bot deck
   strength.
4. Watch real drafts' bot reports after shipping.
