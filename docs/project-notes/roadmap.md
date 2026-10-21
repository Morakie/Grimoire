# Roadmap and ideas (as of 2026-10-20)

Roughly in priority order. Nothing here is committed to a date.

## Bots
1. Ship Bot Brain (on `dev`) to production when the owner says.
2. Bot Brain simulations with random personas per seed, so they behave like real tables.
3. Multi-seed summary in Bot Brain: seats per deck type, seats with no deck type, crowding, to measure tuning.
4. Soft plan-fit factor for in-colour cards that don't fit the deck (Sheoldred in storm, Emrakul in aggro).
5. Per-colour lane capacity; open strong lanes gaining value; early-flagging deck types; missing signature cards
   in deck-type lists (see [bots.md](bots.md)).
6. Host setting next to the ignore list: "pick earlier / pick later" per card.
7. Engine speed: cache rival desires across picks further; custom-card images are data URLs inside the cube.

## Drafting
- Click through a mirror table end to end on staging.
- Set / mixed / chaos packs: pack contents from MTGJSON booster data, card data/images from Scryfall; load a
  set's data only when a table uses it. Bots: 17lands data for Arena-era sets, rarity/stats for older sets.
- Pack art and a 2D opening animation.

## Online play
- XMage is MIT-licensed. Render can't host an XMage server for the desktop client (raw TCP); a 2-4 GB VPS can.
  Small first step: "Export to XMage (.dck)".
