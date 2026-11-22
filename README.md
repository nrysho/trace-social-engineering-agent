# START Hack Munich 2026 
## revel8: Agentic Social Engineer

> **Person 5 / team integration: [Start with PERSON5_README.md](PERSON5_README.md).** It explains what is implemented, what is not connected yet, how to test it, and exactly what Mavis, Izen, Sherwin, Neryss and Theja need to do.

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

## Practice chat

`chat.py` lets you talk to the practice twins (Julius, Robert, Tom) by hand from the
terminal. It needs only `REVEL8_API_KEY` in `.env` and the `requests` package.

```bash
pip install requests     # once, if it is missing
python3 chat.py          # Windows: python chat.py
```

1. Pick a twin.
2. Pick **New session** (they remember nothing) or continue an open one. The list shows
   the whole team's open sessions with who was contacted and the last message.
3. Confirm or change the sender name and address.
4. Pick a channel.
5. Type a message and press **Enter** to send. The twin's reaction (reply, opened link,
   submitted page, opened file, or silence) appears below.

| Command | What it does |
|---|---|
| `/edit` | Write a longer message in a text editor; it sends when you save and close |
| `/to` | Switch twin |
| `/channel` | Switch channel |
| `/from` | Change sender name and address |
| `/attach NAME` | Attach a file name to the next message |
| `/page` | Register a landing page; put its exact URL in your message |
| `/call` | Start a live call or chat, one line per turn; `/hangup` ends it |
| `/history` | Show the whole session again |
| `/new` | Start a fresh session |
| `/quit` | Leave; the session stays open |

Every message costs one touch (30 per practice session); a whole call costs one touch.
Your side of each session is also saved in `runs/chat/<session>.jsonl`. Writing by hand
is for practice only: scoring runs must be fully autonomous.

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

## Judging materials

- [Architecture page](docs/architecture.html) and [implementation explanation](docs/ARCHITECTURE.md).
- [Rubric readiness and priorities](docs/RUBRIC_READINESS.md).
- [Three-minute core](docs/PITCH_3_MIN.md) and [five-minute version](docs/PITCH_5_MIN.md); confirm the stage slot.

## Deliverables

- An architecture page: how the system goes from research to contact to reading a
  reaction and adapting.
- A five-minute pitch with one real thread from our runs.
- The scoring runs themselves (revel8 records and renders every turn).

## Person 5 quality and evidence package

Use the consolidated **theja-person5** branch. Start with
[PERSON5_README.md](PERSON5_README.md) and [the team handoff](docs/PERSON5_HANDOFF.md).
The actual Python orchestrator uses the baseline guard on this branch. Advanced
identity/evidence review and SQLite state are available as explicit opt-in layers;
other send paths do not acquire protection automatically.

Run `py -m quality.acceptance --browser --output runs/quality/consolidated-acceptance`
for the combined component, local-bench and rendering checks. No official
simulator/model call is made by acceptance. See the generated acceptance.json
for the actual test result; skipped browser tests are not full acceptance.
