# Project notes

Working knowledge about Grimoire that isn't obvious from the code: how it's hosted and shipped, decisions the
owner has made, how the draft bots are meant to draft, what has been tried, and what's next. Written for anyone
joining the project, human or AI. Start with the [README](../../README.md) and [AGENTS.md](../../AGENTS.md), then:

| File | What's in it |
|------|--------------|
| [status.md](status.md) | Environments, how to ship, staging rules, what's live, owner decisions |
| [bots.md](bots.md) | How the draft bots should draft (the owner's model), engine design, what reviews of real drafts found |
| [bot-brain.md](bot-brain.md) | The Bot Brain / Bot Lab tuning tools: how they work, how to test bot changes |
| [roadmap.md](roadmap.md) | Open work and ideas, roughly in priority order |

The engine itself is documented in [docs/DRAFT_BOTS.md](../DRAFT_BOTS.md) and deployment in
[docs/DEPLOYMENT.md](../DEPLOYMENT.md).

## Keeping these notes useful

- Update them in the same commit as the change they describe (a shipped feature, a new decision, a finding).
- Record decisions with the reason, so a later change doesn't undo them by accident.
- This repository is public: no secrets, connection strings, personal details or private conversations here.
- Dates are written out (2026-10-20) so it's clear how current a note is.
