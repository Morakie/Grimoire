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
- **Taking a turn:** picks run on the server. When a bot is on the clock, the next state poll makes the pick: bots
  pick instantly by default (`BOT_DELAY_SCALE=1` adds a 0.8–1.7 s pause). A guard on the pick count makes this safe when several clients poll at once.
- Bot picks appear in the pick feed like anyone else's. Host undo / reassign work on bot picks too.

## Card knowledge

Built when the draft starts and stored on the draft:

1. **Features per card** (`features.py`): colours needed to cast (hybrid/Phyrexian are optional), colours a land
   or rock produces, types, mana value, and role tags from rules text (removal, counter, ramp, burn, finisher,
   aggro creature, reanimate, cheat, sac outlet, …). Reminder text in parentheses is ignored (Treasure's "add one
   mana" doesn't make a mana dork), rituals are instants and sorceries only, and `ROLE_OVERRIDES` fixes the odd
   card the patterns get wrong (add a line when `?explain=1` shows a misfire).
2. **Power:** CubeCobra Elo normalised to the cube (5th–95th percentile → 0–1, bombs above 1, gently compressed).
   Cards with no Elo get the cube median, except fast mana (0–1 mana non-creature that taps for mana), which is
   rated like the cube's best cards.
3. **CubeCobra card stats** (`cardstats.py`): each card's CubeCobra page gives its current Elo (replaces the CSV
   value) and the cards it is most often **drafted with** and **synergistic** with. These become in-cube
   "package partners". Stats are cached in Mongo (`card_stats`, refreshed monthly), warmed in the background when
   a bot joins the lobby, and turned into per-draft data at start (`bot_stats` on the draft). Missing stats just
   fall back to the CSV.
4. **Combos** (`combos.py`): the cube list is checked against [Commander Spellbook](https://commanderspellbook.com)
   (MIT-licensed). Every combo fully contained in the cube is stored, weighted 0.6–1.0 by popularity. Loops that only
   gain life are skipped. A short hand-kept list (`CUBE_COMBOS`: Thassa's Oracle + Tainted Pact, Time Vault + Keys, …)
   adds cube staples Spellbook misses.
5. **Role packages:** a few enabler ↔ payoff pairs by role (reanimate/self-mill ↔ fatties, sac outlets ↔ death
   payoffs, …).

## Scoring each pick (`engine.py`)

1. **Power**, weighted a little less late in the draft. Dual/fetch lands count at half power at pick 1 (spells first).
2. **Colours:** commitment follows **coloured spells owned**, not the pick number, because early picks in a powered
   cube are often Moxen, rocks and lands. The bot starts leaning at 2 coloured spells (table "openness" signals help
   choose) and is committed to two colours at 7. After that off-colour cards keep only 10% of their value. A third colour is only a deliberate
   splash: strong owned cards need it (lands don't count; a fetch taken for its other colour says nothing). Only
   cards with a single pip of the splash colour are castable on a splash, never {B}{B} cards. The bot then values
   fixing for it.
3. **Combos and packages:** a combo piece is worth more as more of its line is owned (one piece is a nudge, two of
   three makes the third a priority), scaled by how well all pieces fit the bot's colours. A card's best line counts in
   full and its other lines only 25%, so a card in many half-relevant lines doesn't outscore real cards; lines of four
   or more cards are ignored. CubeCobra partners add
   value for cards that go with what the bot already owns; role packages add a little more.
4. **Mana rocks:** once a deck owns three mana artifacts and has no artifact plan, further rocks costing 2 or more
   lose 35% of their rating. The same goes for colourless utility artifacts (Top, Baubles, Skullclamp): past two,
   a deck with no artifact plan values another one 40% less.
   **Role saturation:** past a deck's fill of one job (5 fatties, 5 reanimation spells, 3 cheat spells, 3 sweepers,
   3 equipment, 5 tutors, 6 planeswalkers) another card doing it loses 25%, then 50% (`ROLE_SATURATION`).
   **Enablers and payoffs:** reanimation and cheat spells lose up to 60% with no fatty owned or still likely to come;
   7+ mana fatties lose up to 60% with no reanimation or cheat spell owned or likely to come.
5. **Fixing:** on-colour duals/fetches gain value from mid-draft, more if the bot has few.
6. **Deck style:** once committed, a light nudge towards what that colour pair usually does.
7. **Win condition:** from about a third of the way in, the bot checks it can win: a live, reasonably popular
   combo line, about 6 threats (creatures/planeswalkers/finishers), or about 10 cheap attackers. The bigger the
   gap, the more on-colour threats are worth. Decks that already have a plan are barely affected.
8. **Late needs:** interaction, creatures and cheap spells if short; a penalty for too many expensive cards.
9. **Sideboard answers:** from the bot's own 20th pick (fully by its 26th), cards that answer one kind of deck
   (`hate_*` roles from rules text: Null Rod / Collector Ouphe for artifacts, Tormod's Crypt / Soul-Guide Lantern for
   graveyards, Defense Grid for counterspells, Ensnaring Bridge for creature decks, Archon of Emeria for storm) gain
   up to 0.4 when a rival is building that deck. Never against the bot's own plan, less for each answer it already
   has, and none past four. In bot-only drafts a bot ends up with about one such card.
10. **Float risk:** for the top candidates, each rival who picks before the bot's next turn ranks cards by their own
   colours, combos and packages. Cards unlikely to be taken can wait, so a contested card is taken first. A rival
   counts as flexible about colours until it owns a few coloured spells (like the bot itself), and a rival holding
   all but one piece of a combo is likely to take the last one. The bot never waits on the last piece of its own
   combo. Fetchland "runs" start only from people's picks, so bots don't set one off by following each other.
11. **Deck types** (`decktypes.py`): Tolarian (Academy, Urza, Time Vault + Keys, Tinker), Workshop, artifact
   synergy (Saga, Opal, Plating, Thopter-Sword, Retrofitter), storm, reanimator, cheat and lands, each defined by
   **key cards** (plus role tags). Similar deck types are separate: a Tolarian deck and an artifact-synergy deck
   compete only for the cards both use. Other cards belong to a deck type by the share of their CubeCobra
   partners that are its key cards (Baubles and Top are artifact cards; Dismember is drafted with everything).
   - **Commitment:** key cards count fully (two make a full deck type), member cards 30%. Open picks lean:
     Mana Vault counts as half a Tolarian key, a Mox as a small nudge, Sol Ring as nearly nothing. Leans add up
     to at most a little more than one Mana Vault, so a pile of mana rocks doesn't make a deck type.
   - **Narrow cards** (colourless spells tied to a deck type, colourless key cards like Mox Opal and Lion's Eye
     Diamond, one-colour utility lands like Karakas) keep 40% of their rating until the bot is in a deck that
     uses them. A key card of a deck type nobody is in is worth taking to start it.
   - **Fight or pivot:** once two other seats are in a deck type, a bot behind the deepest of them values its
     cards up to 60% less, the further behind the more (so it moves to something open). A bot as deep as them
     keeps fighting, and contested cards don't wait.
   - **Focus:** from half-committed, cards outside the bot's deck type lose up to 30%, so it takes what its
     deck needs over generically good cards. Removal and counterspells are always needed.
12. **Power first:** the Power Nine (`TAKE_ON_SIGHT` in `features.py`) are rated at least at the cube's 98th
   percentile Elo whatever CubeCobra says (Timetwister sits below Orcish Bowmasters there). Colourless non-mana
   cards get a "home" from their partners' colours (Phyrexian-mana cards like Dismember don't).

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
  decktypes.py   deck types, key cards and narrow cards
  personas.py    hidden personalities and bot names
  simulate.py    bot-only draft simulation and metrics
```

The engine is pure Python with no database access, so it is unit-tested directly (`backend/tests/test_draftbot.py`).

## Validation

`POST /api/bots/simulate` (only when `ENABLE_BOT_SIM=true`; staging only) runs a full bot-only draft of a CubeCobra
cube and reports per seat: colours, share of spells on colour, win plan, creatures, fixing, combos completed and
the pick list. `tuning` overrides any `TUNING` value for that run.

To replay a real draft offline, save `GET /api/drafts/{id}/bot-inputs` (cards, CubeCobra stats, combos, order and
picks) and run the engine on it; `GET /api/drafts/{id}/suggestions?seat=N&explain=1` shows the live score parts.

**Bot Lab** (draft room → "Bot Lab", rotisserie cube tables): `POST /api/drafts/{id}/bot-lab {seat, pick_no | slot, tuning}`
rebuilds the table just before a pick and returns the engine's top cards with every score part, the card actually
taken and its rank, and the seat's colours and deck types. `tuning` overrides any weight listed in `draftbot/lab.py`
`KNOBS` for that view only (each card also gets its rank under the current weights); the live bots never see it.
The page keeps tried weights in the browser and "Copy" gives them as JSON to bake into `TUNING`.
