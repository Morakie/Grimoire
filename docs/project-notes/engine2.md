# Engine 2

Engine 1 (`engine.py`, live tables) scores a card as a rating times a stack of multipliers (77 weights in `TUNING`).
Engine 2 (`engine2.py`, Bot Brain's "Bot logic" switch) asks: which card would I most regret not taking now? Same
`BotContext` and `score_pool` / `choose_pick` / `suggest_picks` shape. Live tables, suggestions and the bot report
still use engine 1. History of how it got here: git log.

## Where the knowledge lives

| What | File |
|---|---|
| Card facts (roles, colours, cost, Elo) | `features.py` |
| Deck types (key and member cards) | `decktypes.py` |
| Lane capacity, combo packages and piece priority, roto speed adjustments, hand pick tiers, deck mix per deck type | `knowledge.py` |
| People's pick order: VRD sheets (`PICK_ORDER`), the owner's group (`GROUP_ORDER`), LSV's drafts (`combined_order`) | `pick_order.py`, `lsv_drafts.py` |
| LSV's "when X, do Y" rules (R1, R2...) | `rules.py` |
| Principles and rules, each with a test | `bot-principles.md`, `backend/tests/test_principles.py` |

To teach the bots something: data goes in `knowledge.py`; behaviour gets a principle or rule in
`bot-principles.md` and a test, then the change that makes it pass.

## The pick rule

    score = value x (keep + (1 - keep) x gone)

- **gone**: chance the card is taken before this seat picks again: each rival picking in between ranks it by its
  own value, plus people's pick order for human seats. The last piece of a combo we hold counts as gone.
- **keep** (0.5): what a card that comes back is worth now; rises to 1 near the end.

This gives LSV's method: take what others will take, float what only you want.

## Value

    value = (quality x colour fit x plan fit + partners + combo) x deck budget

- **quality**: people's pick order (70%) blended with CubeCobra Elo, times the roto speed adjustment. Pick order
  weights LSV's tables 24 per draft that took the card, VRD sheets 1, the owner's group 0.2 (owner, 2026-10-21).
- **colour fit**: flexible early, two colours by about five coloured spells; Moxen lean their colour, fetches fit
  most decks; cheat targets fit any seat holding their enabler (R1).
- **plan fit**: the deck types the seat is in plus "good stuff", cut over lane capacity; narrow and key cards are
  discounted only once the seat is committed elsewhere.
- **combo**: packages with piece priority and substitutes, plus Commander Spellbook lines.
- **deck budget** (R2): past pick 10, a kind of card the seat already has more of than its deck type usually holds
  is worth less; lands short of the usual count are worth more.

## Benchmark and checks

- `benchmark.replay(index, combos, "engine2")`: replays LSV's five drafts and ranks every real pick; each draft is
  scored with a pick order built without it. Group cube + PowerLSV pool, 2026-10-22: all picks top 10 52%, median
  rank 10; LSV's picks top 3 29%, median 8 (engine 1: median 17 and 14).
- `compare.run_metrics(...)`: all-bot drafts: lanes over capacity, colours, deck Elo, where watched cards go.
- `compare.human_rows` / `bot_rows` / `mix_table`: what each deck type's first 40 picks hold, people vs bots.
- Run them in the browser (Bot Brain's Python worker); see `bot-brain.md`.

## Known gaps

- Cheat decks still take about 4 enablers and 4 big creatures (people: 2.5 each); Academy and tempo bots take
  more creatures than people; bots still take fewer nonbasic lands than people (4-7 vs 7-12 in 40 picks).
- LSV's drafts are reconstructed only for their first 6-18 rounds; 12+ weights are tuned on about 530 picks.
- The Bot Lab legend text still describes engine 1.
