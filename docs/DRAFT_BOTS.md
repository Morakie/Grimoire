# Draft bots: design

Bots fill seats in a rotisserie cube draft. The host adds them in the lobby, and they pick on their own turns.
The goal is picks that look like a competent human's: strong cards early, two committed colours, real combo
packages, a way to win, and some variety from draft to draft without erratic choices.

A rotisserie draft is one big face-up pack: every remaining card and every player's picks are visible. So bots
score the whole remaining pool each pick and read other drafters' picks as signals. Nothing is tied to a specific
cube: no card names are hard-coded, and custom cards (`is_custom`) are ignored.

## How bots join and pick

- **Adding a bot:** in the lobby, the host clicks **Add bot** to fill an empty player slot. A bot takes seats
  exactly like a human (spread around the snake) and gets a name with no connection to its hidden personality.
- **Taking a turn:** picks run on the server. When a bot is on the clock, the next state poll after a short,
  randomised delay (0.8–1.7 s, scaled by `BOT_DELAY_SCALE`; set it to `0` on staging for instant test drafts)
  makes the pick. A guard on the pick count makes this safe when several clients poll at once.
- Bot picks appear in the pick feed like anyone else's. Host undo / reassign work on bot picks too.

## Card knowledge

Built when the draft starts and stored on the draft:

1. **Features per card** (`features.py`): colours needed to cast (hybrid/Phyrexian are optional), colours a land
   or rock produces, types, mana value, and role tags from rules text (removal, counter, ramp, burn, finisher,
   aggro creature, reanimate, cheat, sac outlet, …).
2. **Power:** CubeCobra Elo normalised to the cube (5th–95th percentile → 0–1, bombs above 1, gently compressed).
   Cards with no Elo get the cube median, except fast mana (0–1 mana non-creature that taps for mana), which is
   rated like the cube's best cards.
3. **CubeCobra card stats** (`cardstats.py`): each card's CubeCobra page gives its current Elo (replaces the CSV
   value) and the cards it is most often **drafted with** and **synergistic** with. These become in-cube
   "package partners". Stats are cached in Mongo (`card_stats`, refreshed monthly), warmed in the background when
   a bot joins the lobby, and turned into per-draft data at start (`bot_stats` on the draft). Missing stats just
   fall back to the CSV.
4. **Combos** (`combos.py`): the cube list is checked against [Commander Spellbook](https://commanderspellbook.com)
   (MIT-licensed). Every combo fully contained in the cube is stored, weighted 0.6–1.0 by popularity.
5. **Role packages:** a few enabler ↔ payoff pairs by role (reanimate/self-mill ↔ fatties, sac outlets ↔ death
   payoffs, …).

## Scoring each pick (`engine.py`)

1. **Power**, weighted a little less late in the draft. Dual/fetch lands count at half power at pick 1 (spells first).
2. **Colours:** flexible for the first few picks (table "openness" signals help choose), committed to two colours
   by about pick 10. After that off-colour cards keep only 10% of their value. A third colour is only a deliberate
   splash: strong owned cards need it, and the bot then values fixing for it.
3. **Combos and packages:** a combo piece is worth more as more of its line is owned (one piece is a nudge, two of
   three makes the third a priority), scaled by how well all pieces fit the bot's colours. CubeCobra partners add
   value for cards that go with what the bot already owns; role packages add a little more.
4. **Fixing:** on-colour duals/fetches gain value from mid-draft, more if the bot has few.
5. **Deck style:** once committed, a light nudge towards what that colour pair usually does.
6. **Win condition:** from about a third of the way in, the bot checks it can win: a live, reasonably popular
   combo line, about 6 threats (creatures/planeswalkers/finishers), or about 10 cheap attackers. The bigger the
   gap, the more on-colour threats are worth. Decks that already have a plan are barely affected.
7. **Late needs:** interaction, creatures and cheap spells if short; a penalty for too many expensive cards.
8. **Float risk:** for the top candidates, each rival who picks before the bot's next turn ranks cards by their own
   colours, combos and packages. Cards unlikely to be taken can wait, so a contested card is taken first.

The final pick is sampled among the top cards within 90% of the best score (low temperature), so bots usually
take their best card and occasionally a close second. Hidden personalities nudge a few weights by about ±5%.

All numbers live in `TUNING` in `engine.py`.

## Code layout

```
backend/draftbot/
  features.py    card features, role tags, power
  cardstats.py   CubeCobra ratings and package partners (fetch + cache)
  combos.py      Commander Spellbook lookup and role packages
  engine.py      scoring and pick selection
  personas.py    hidden personalities and bot names
  simulate.py    bot-only draft simulation and metrics
```

The engine is pure Python with no database access, so it is unit-tested directly (`backend/tests/test_draftbot.py`).

## Validation

`POST /api/bots/simulate` (only when `ENABLE_BOT_SIM=true`; staging only) runs a full bot-only draft of a CubeCobra
cube and reports per seat: colours, share of spells on colour, win plan, creatures, fixing, combos completed and
the pick list. `tuning` overrides any `TUNING` value for that run.
