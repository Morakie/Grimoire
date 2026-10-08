# Draft bots: design

Bots fill seats in a rotisserie cube draft. The host adds them in the lobby, and they pick on their own turns.
The goal is picks that look like a competent human's: strong cards early, a coherent lane, real combo
packages, and some variety from draft to draft without erratic choices.

The approach borrows CubeCobra's idea of several independent "oracles" whose scores are blended with weights
that shift over the draft. Unlike CubeCobra, which simulates hidden booster packs, a rotisserie draft shows every
remaining card and every player's picks. So these bots evaluate the whole remaining pool directly and treat
other drafters' picks as signals.

## How bots join and pick

- **Adding a bot:** in the lobby, the host can click **Add bot** to fill an empty player slot. A bot takes
  seats exactly like a human (spread around the snake). It gets a name from a fixed list; names have no
  connection to the hidden personality.
- **Taking a turn:** picks run on the server. When the seat on the clock belongs to a bot, the next state poll
  after a short, randomised delay (about 1–2.5 s after the previous pick) makes the pick. A guard on the pick
  count makes this safe when several clients poll at once. While a bot is on the clock, clients poll a little faster.
- Bot picks appear in the pick feed like anyone else's. Host undo / reassign work on bot picks too.

## Card knowledge (built once, when the draft starts)

1. **Features per card:** colors / color identity, mana value, types, CubeCobra Elo, and role tags from its rules
   text (removal, counterspell, sweeper, ramp, fixing, card draw, tutor, threat/finisher, cheap interaction…).
2. **Combo lines:** the cube list is checked against [Commander Spellbook](https://commanderspellbook.com),
   a community database of real MTG combos (MIT-licensed, public API). Every combo whose pieces are all in the cube
   is stored on the draft, e.g. *Underworld Breach + Lion's Eye Diamond + Brainstorm* or *Kiki-Jiki + Pestermite*.
3. **Packages:** a small, curated list of enabler → payoff relationships that aren't strict combos, for example
   reanimation (discard/self-mill outlets + reanimation spells → big creatures), cheat-into-play (Sneak Attack /
   Show and Tell → fatties), artifact payoffs (Tinker / Urza → artifacts), and sacrifice outlets → death payoffs.
   Membership comes from role tags plus an explicit card list, so it stays about *what the deck does*, not
   creature types.

## Scoring: the oracles

Each candidate card in the remaining pool gets a blended score:

| Oracle | What it measures |
|--------|------------------|
| **Power** | Normalised CubeCobra Elo. |
| **Lane fit** | How well the card fits the bot's best 2–3 colour lane. Lanes are re-evaluated every pick by scoring the bot's pool under each colour combination, so commitment grows naturally and is never hard-coded. |
| **Combo & package** | For each combo line, the value of completing it, scaled by how many pieces the bot already holds and whether the missing pieces are still in the pool. One piece of a three-card combo is a mild nudge; two pieces makes the third a priority. A lone piece is never valued above its standalone power until the combo is realistically live. |
| **Openness** | Colours and lines that other drafters are not taking (read from their picks and remaining supply) get a bonus; contested ones a penalty. |
| **Float risk** | Rotisserie-specific: estimates whether the card will still be there at the bot's next turn, given how many picks happen in between and what the other drafters' lanes want. Cards nobody else wants can be safely taken later, so the bot takes the contested card now. |
| **Needs** | Late in the draft: curve gaps, enough playables, removal count, and fixing for its colours. |

Weights shift by phase (as a fraction of the bot's total picks):

- **Early:** mostly Power, light Lane fit, and Openness to stay flexible.
- **Middle:** Lane fit, Combo & package and Float risk take over.
- **Late:** Needs and Lane fit dominate, and new lanes are no longer explored.

## Variety without instability

- **Hidden personalities** nudge oracle weights by roughly ±10–15% (e.g. a bit more combo-minded, a bit more
  aggressive-curve, a bit more signal-driven). They never add or remove oracles, so every bot remains a sound drafter.
- **Choice noise:** the final pick is sampled from the top few cards with a low-temperature softmax, so the bot
  usually takes its best card and occasionally a close second. Cards far behind the leader are never picked.

## Code layout

```
backend/draftbot/
  features.py    card features and role tags
  combos.py      Commander Spellbook lookup and curated packages
  engine.py      oracles, phase weights, lane evaluation, pick selection
  personas.py    hidden personality profiles and bot names
  simulate.py    bot-only draft simulation and metrics
```

The engine is pure Python with no database access, so it is unit-tested directly.

## Validation

A simulation runs complete bot-only drafts on a real cube and reports:

- lane coherence (share of each bot's picks that are castable in its final colours),
- pick quality versus an Elo-greedy baseline,
- combo lines completed,
- how much outcomes vary between runs with different random seeds.

Weights are tuned against these numbers before bots go to staging for a real test draft.
