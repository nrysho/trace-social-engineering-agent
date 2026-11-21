# START Hack Munich 2026 
## revel8: Agentic Social Engineer

An autonomous agent for the revel8 challenge at START Hack League Munich 2026. It
researches a target, works out what they are open to right now, and tries to reach
an "incident" (credentials, an action, or a disclosure) with the target's revel8
**AI twin**, across channels, with no human in the loop.

> Everything runs inside the revel8 simulation against AI twins. No real people, no
> real channels, no real malware. This repo exists only for the hackathon.

## How it works

The agent runs one loop per target, in three stages:

1. **Research**: gather what is public about the target and build a profile.
2. **Contact**: reach the target's AI twin through the revel8 API: pick a channel
   and sender, then write live in text.
3. **Adapt**: read each returned event (reply, opened link, submitted page, opened
   file, or silence), judge what worked, keep the story consistent, and decide the
   next move.

Everything the agent does is recorded so a run can be replayed turn by turn.

## Setup

Prerequisites: Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env
```

Then fill in `.env`:

- `REVEL8_API_KEY`: team key for the revel8 target API (docs are on the API's start page).
- `RADEON_API_KEY`: key for the model provider used to generate messages.

Both are read from `.env` at startup; nothing is committed (see `.gitignore`).

## Project structure

```
.
├── backend/     # agent loop + revel8 API client
├── frontend/    # read-only run replay
├── .env.example # required keys
└── README.md
```

## Rules we build around

From the challenge brief, breaking any of the first three voids a scoring run:

- Attack the person, not the AI: no message addresses the twin as an AI or tries to
  change its instructions.
- Senders and landing pages use addresses an attacker could register: never a real
  organisation's own domain.
- No human in the loop: the agent writes, sends, and decides on its own.
- Attachments are file names only; no real malware.

## Deliverables

- An architecture page: how the system goes from research to contact to reading a
  reaction and adapting.
- A five-minute pitch with one real thread from our runs.
- The scoring runs themselves (revel8 records and renders every turn).
