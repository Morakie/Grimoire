# Engine 2: design (started 2026-10-21)

Engine 1 (`backend/draftbot/engine.py`) scores each card as "rating, then a stack of multipliers and bonuses".
Every fix added a factor (77 weights in `TUNING`), and the factors interact, so fixing one pick moved others.
Engine 2 (`backend/draftbot/engine2.py`) asks the question the way a drafter does:

> Which card would I most regret not taking now?

It runs beside engine 1 (same `BotContext`, same `score_pool` / `choose_pick` / `suggest_picks` shape) and is
switched per draft in Bot Brain. Live tables keep engine 1 until engine 2 wins on the comparisons below.

## Where the bots' knowledge lives

| What | File | Example |
|---|---|---|
| Card facts read from the card | `features.py` | roles, colours, cost, Elo |
| Deck types (keys, core) | `decktypes.py` | `KEYS["tolarian"]` |
| Drafting knowledge from people (LSV videos, VRD sheets, the group) | `knowledge.py` | lane capacity, combo packages and piece priority, roto speed adjustments, human pick-order tiers |
| Drafting principles (behaviour) | `docs/project-notes/bot-principles.md` + `backend/tests/test_principles.py` | one test per principle, citing its source |

To teach the bots something new: add the fact to `knowledge.py` (data) or write the principle down in
`bot-principles.md` with a test in `test_principles.py` (behaviour), then make the test pass. A principle with
no test can be lost by the next change; a principle with a test can't.

## The pick rule

For the seat picking, every available card gets:

    score = value x (keep + (1 - keep) x gone)

- **value**: how much the card improves this seat's likely final deck (below).
- **gone**: the chance the card is taken before this seat's next pick, from what each rival picking in between
  wants (their own value of it, against the best cards they have) and, for people, how early people usually
  take it (`knowledge.PICK_TIERS`). The last piece of a combo we hold is always treated as gone.
- **keep** (about 0.5): how much a card that will come back is still worth now. Late in the draft, with few
  picks left, keep rises to 1 (there's no "later").

This one rule gives LSV's method: take the cards others will take; float the ones only you want. It replaces
engine 1's float risk, contest bonus and land-run logic.

## Value

    value = quality x colour fit x plan fit x need + combo + sideboard

- **quality**: CubeCobra Elo (normalised, Power floor as in engine 1) x the roto speed adjustment for the card
  (`knowledge.ROTO_ADJUST`: cheap interaction up, slow value cards down).
- **colour fit**: engine 1's colour model (flexible early, two colours by ~5 coloured spells, on-plan splash).
- **plan fit**: each seat holds a few deck plans: the deck types it is in (`decktypes.deck_strength`) plus
  "good stuff" (strong cheap cards in its colours, always possible). A plan's weight is its depth, cut when
  the plan is over its lane capacity (`knowledge.LANE_CAPACITY`: storm, reanimator, Academy hold one seat;
  broad lanes two or three) and fading for a plan the seat hasn't started as the draft goes on. Plan fit is
  the weighted fit of the card to those plans: key and member cards fit their deck type (more the deeper the
  seat is), narrow cards fit only decks that use them, strong generic cards fit "good stuff".
- **need** (replaceability): within a job (cheap counters, cantrips, removal, duals for the seat's pair...),
  a card is worth its gap over the best substitute the seat can still expect to get. Balance has no
  substitute; Mana Drain has Counterspell. Also covers saturation (the sixth fatty adds little) and gaps
  (no interaction or no win condition by mid-draft).
- **combo**: combo lines (Commander Spellbook + hand-kept) and packages with piece priority and substitutes
  (`knowledge.COMBO_PACKAGES`: Breach > Brain Freeze > LED, Lotus Petal can replace LED).
- **sideboard**: answers to rivals' decks, late only, from engine 1's hate logic.

## How we'll know it's better

Same seeds in Bot Brain, engine 1 vs engine 2, on the group cube + PowerLSV pool and on the VRD pool:
- seats per deck type (none over capacity), seats with no plan, colours per deck, on-colour share;
- where top cards go (Power first, generic strong cards not slipping, narrow cards late unless contested);
- deck strength (top-23 Elo);
- agreement with people on replayed real drafts (bot-inputs exports, the VRD sheets as mirror replays);
- every test in `test_principles.py` passing.
