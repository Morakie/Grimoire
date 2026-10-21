# Draft bots: intent, history and findings (as of 2026-10-20)

How the engine works is in [docs/DRAFT_BOTS.md](../DRAFT_BOTS.md); every weight lives in `TUNING` in
`backend/draftbot/engine.py`. This file is about what the bots are supposed to do and why the engine looks the
way it does.

## Goal

Draft well, not imitate the playgroup: optimise what should be taken. The owner thinks the group makes a few
mistakes, and that learning from all CubeCobra decks (not winning ones) pulls towards "average". The bots fill
empty seats in rotisserie cube drafts and power the pick suggestions.

Main cube: PowerLSV (https://cubecobra.com/cube/list/PowerLSV). The owner would also run the bots on the group
cube (CubeCobra `43fd5f2a-942e-40c3-a563-bf3a7ce0cc22`) or both combined with duplicates removed.

## How a good drafter in this group drafts (the owner's model)

- Power is almost always taken first. Pick 1: take Power and stay open, or lean (Mox Sapphire -> blue,
  Mox Jet -> artifacts; Sol Ring / Mana Vault mostly open).
- Seat position and what's available drive the early picks. Commit gradually, sometimes from pick 1-2. Some
  cards are strong commits: Tolarian Academy says "artifacts, early"; Mana Vault wants Keys and blue, not green.
- Lanes are deck types, not colours (Tolarian, Workshop, Artifacts, Storm, Reanimator, Cheat, Lands, Aggro...).
  Sneak/Flash (Cheat) is distinct from Reanimator even with overlap.
- Seeing a rival take a key card (Mana Vault) means that lane is contested: take that deck's cards (Keys, Top,
  Bauble, counterspells), not random generically good cards.
- Pivot (e.g. Boros -> mono-white or WB) when a lane is taken, weighing the cost. The deeper in a deck type, the
  more contested picks matter over floating cards. Too contested: pivot or splash (splashing usually hurts).
- Two seats in a lane is fine if it doesn't wreck either deck, and a contesting bot should prioritise the
  contested cards; four or five in one lane is not. Moving late into a deck type another seat has established
  isn't smart.
- Utility cards (Karakas, Top, Skullclamp) only go in some decks and must fit the deck's goal. No Skullclamp at
  pick 3-4 when contested cards matter more.
- Two colours confidently first; any number of colours later is fine. A splash (black for tutors) must not pull
  in every strong card of that colour (Sheoldred doesn't fit a storm deck).
- Synergy should outweigh raw Elo once a bot knows its deck.
- Sideboard/hate cards (Null Rod, Soul-Guide Lantern...): low weight, late only (around the bot's 20th pick),
  escalating slowly; a few for the sideboard, never hate-drafting as a goal.
- Committing to a colour too early with Power still around (Orcish Bowmasters at pick 16 over Timetwister) is a
  mistake.

## What the engine does about it (main changes, in order)

- PR #11 (2026-10-16): colour commitment counts coloured spells owned, not picks; combo stacking limited (best
  line in full, others a small share; no 4+ card lines, no life-only loops); land runs; fewer extra mana rocks
  without an artifact plan; hand-kept cube combos beside Commander Spellbook; bot report.
- PR #12-13: mirror tables singleton by name; a land-based third-colour splash was tried and reverted (fetches
  count as both colours, so 7 of 8 seats "splashed"). Splash cards need a single pip of the splash colour.
- PR #14: sideboard answers (`hate_*` roles) from rivals' decks, late only.
- PR #17 (2026-10-19): deck types (`decktypes.py`) from key cards and CubeCobra partner shares; deck outlook
  (crowded lanes: shallow bots pivot, deep ones fight), deck focus, contested-lane bonus, entry window (starting
  a new deck type gets less appealing as the draft goes on), Power Nine taken on sight.
- Later on 2026-10-19/20: aggro deck type; flicker regex fix; rating weight drops as a bot commits; partner weight
  up; hate weight down; fixing bonuses; reanimate/cheat spells need targets; 7+ mana fatties need a way in.
- PR #18 (2026-10-20): role-tag fixes (reminder text ignored, `ROLE_OVERRIDES` for hand-checked cards), role
  saturation (`ROLE_SATURATION`), utility-artifact limit, Bot Lab in the draft room.

## Deck types (2026-10-20 expansion)

22 deck types in `backend/draftbot/decktypes.py`: tolarian, workshop (stax), artifacts, welder (red artifacts),
wildfire, painter, storm, reanimator, cheat (Sneak/Show/Breach/Flash/Channel), twin, nadu, recursion (Nightmare/
Pod/Survival), blink, control, tempo (UR), white_aggro (white weenie / D&T), red_aggro (red aggro / burn), gruul
(RG beats), pox, domain, ramp (green), lands. Boros is both aggro types.

- KEYS are signature cards only. A key card is worth less (55%) to a bot outside its deck type, so generically
  strong cards must never be keys.
- CORE lists strong coloured cards that belong to a deck type without defining it (Lightning Bolt in red aggro,
  Force of Will in control): membership 0.6, no penalty for anyone else. No colourless spells in CORE (they
  would turn narrow).
- Everything else gets its membership from CubeCobra partners (the "web"), so the lists stay short.
- Check a card's deck types in Bot Brain's Cards tab.

## Power floor (2026-10-20)

CubeCobra rates Timetwister far below the rest of the Power Nine (1810 against 2225+ in the group cube +
PowerLSV), so with only a 98th-percentile floor, Orcish Bowmasters, Ragavan and Mana Drain outranked it and a bot
holding Time Walk + Ancestral took Bowmasters over Timetwister. Power is now rated at least at the lower quartile
of the cube's own Power cards (Timetwister -> 2237).

## Findings from reviews of real drafts

- Replays use the bot-inputs export of a draft and the bot report (`GET /api/drafts/{id}/bot-report`), which
  re-scores every pick with today's engine.
- Typical early problems found: bots hammering one artifact drafter (4-5 bots taking every artifact), utility
  cards suggested at picks 4-5 with Ragavan/Bolt available, fetchland "runs" set off by bots copying each other
  (now only people's picks start a run), reanimation spells with no targets, payoffs with no support.
- The group passes removal and threats long and drafts with strong archetype vision; late hate picks aim at
  specific opponents.
- Still open: in-colour power cards that don't fit the deck's plan (Sheoldred in storm, Emrakul in aggro) need a
  soft plan-fit factor (floor ~0.3-0.4, only once committed); the engine disagrees with people on duals/fetches
  and on black discard in artifact decks (colour/splash topic).

## Ideas from playtesters (2026-10-20, discussion, not decisions)

- Colours hold different numbers of drafters: blue ~5 decks, red 4, green as a main colour 2, artifacts 2. The
  engine treats all colours alike when judging openness.
- An empty strong lane (no Boros drafter by pick 5-6) should gain value for an uncommitted bot, not fade.
- Some deck types flag early (Storm, Tolarian, Boros, Titania lands); Reanimator works better as a package.
- Signature cards missing from deck-type lists (Ragavan, Nadu) get read as generic colour cards.
- Give each bot a small nudge towards one core card or deck type (not a colour) so bots don't all draft the same
  way. Bot Brain simulations currently give every bot the same "steady" persona.
