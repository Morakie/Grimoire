# Drafting principles the bots must keep

Each principle has a source, how engine 2 implements it, and a test in `backend/tests/test_principles.py`
(test names start with the principle id). A change that breaks a test breaks a principle: fix the change or
come back here and change the principle on purpose.

Sources: LSV's roto videos (YKe3oPV_Ny0, jZBJeS545TM, suu9P7zsKBU, qFqiUG69rfw, x6HSqjTfStE, VsrFsB2cBnA), his
TCGplayer combo article (Feb 2025), seven VRD roto sheets, and the owner's model in [bots.md](bots.md).
Paraphrased notes on each are in the claude.ai Project ("lsv-roto-principles", "lsv-roto-video-notes",
"combos-article-and-vrd-drafts").

| Id | Principle | Source | Engine 2 mechanism |
|---|---|---|---|
| P1 | Power first: Lotus, then the rest of the Power, Gleemox, Mana Crypt, Sol Ring are early picks | all videos, VRD sheets | quality (Power floor) + people take them early (`PICK_TIERS`) |
| P2 | Take the cards others will take; float the cards only you want | LSV (qFqiUG69rfw, VsrFsB2cBnA) | pick rule: value x (keep + (1-keep) x gone) |
| P3 | The last piece of your own combo is never floated | owner, engine 1 | gone = 1 for it |
| P4 | Narrow lanes hold one drafter; don't join a narrow lane a rival is in | LSV (jZBJeS545TM storm 3-6), VRD | `LANE_CAPACITY`, plan weight cut over capacity |
| P5 | Two seats can share a broad lane; a third backs off | owner, LSV | `LANE_CAPACITY` 2 for broad deck types |
| P6 | Value a card by its gap over the substitutes still available (Balance > Mana Drain) | LSV (VsrFsB2cBnA) | need / replaceability by job |
| P7 | Commit to two colours early; take strong generic cards in them; pick the win condition late | LSV (x6HSqjTfStE 7-1), owner | colour model + "good stuff" plan |
| P8 | A card that only goes in some decks waits until the bot is in one (Karakas, Top, Baubles) | owner | plan fit for narrow cards |
| P9 | Strong generic cards don't slip for marginal plan cards (Ragavan over Plateau) | LSV (YKe3oPV_Ny0) | quality x plan fit, "good stuff" plan always present |
| P10 | Combo pieces have a priority (Breach > Brain Freeze > LED) and substitutes (Lotus Petal for LED) | LSV article | `COMBO_PACKAGES` |
| P11 | Cheap interaction beats expensive interaction in roto; Ragavan up, Remand/Bowmasters/Skullclamp down | LSV (suu9P7zsKBU, x6HSqjTfStE) | `ROTO_ADJUST` |
| P12 | Every deck wants interaction; a deck with none by mid-draft looks for it | LSV, VRD results | need: interaction gap |
| P13 | Fixing: duals for your own pair are worth taking once committed, more so when a neighbour shares the pair | LSV (suu9P7zsKBU) | need (duals by pair) + gone |
| P14 | Sideboard answers late, low weight, never hate-drafting as a goal | owner, group rule (LSV) | sideboard term (from engine 1) |
| P15 | Starting a deck type late that a rival has established isn't worth it | owner | plan weight fades for unstarted plans; capacity |
| P16 | Pivot to an under-drafted colour when your pair is crowded | LSV (suu9P7zsKBU, tied 1st) | colour openness (from engine 1) |
