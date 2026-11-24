# TRACE: an autonomous social-engineering agent for security-awareness simulations

**🥈 2nd place and best pitch, revel8 challenge, START Hack Munich 2026** · team SchnitzelStrikers

[revel8](https://revel8.ai) trains employees against AI-powered social engineering. Their challenge:
build an agent that researches a person and, **fully autonomously**, gets that person's **AI twin**
to give something away (a password, internal information, or an action done for the attacker) in as
few contacts as possible.

> **Scope.** This agent only talks to AI twins inside revel8's authorised simulation, through
> revel8's API (it needs a team key that revel8 issues for the event). It never contacts real people
> or real channels, sends no malware (attachments are file names only), and every sender domain is
> checked to be unregistered, never a real organisation's own. It was built for a security-awareness
> exercise and is published as a portfolio piece.

## What it does

```
public research  →  sourced profile  →  ranked stories  →  calls and mails  →  read the reaction  →  adapt
```

1. **Recon** (`backend/recon/`). Web search (Tavily + Serper, DuckDuckGo as fallback), the public
   LinkedIn profile (Bright Data), GitHub and the company's DNS records. An LLM extracts short, dated
   facts; every fact keeps its source URL, facts found by two sources are marked verified, and
   contradicted ones are dropped. It also proposes what the person is open to right now ("hooks").
2. **Strategy** (`strategy.py`). Scores every story × channel against the profile in plain code, so
   every choice can be traced. A need the person stated publicly ("looking for…", an open role) wins:
   the strongest story is one they started. Stories that don't fit the person (a fake request from
   "your CEO" to a founder) are penalised.
3. **Sender** (`writer.py`). Invents a believable sender for the story: name, role, organisation,
   an unregistered domain (checked by DNS), a fixed phone number. A real colleague keeps their real
   role; one sender never mixes brands.
4. **Conversation** (`backend/orchestrator.py`). Phone calls first (one contact, up to 10 turns),
   then the mail the call promised: it delivers what the person asked for before asking anything.
   Internal questions are closed ("Jira or ServiceNow?") so answers are concrete. A call-back follows
   an unanswered mail.
5. **Quality gate** (`quality/`, `writer.quality_gate`). Every mail and every call line is checked
   in code before it is sent: no real or misspelt domains, no placeholders or URLs in text, no dates
   in the past, no AI-directed wording. A failing draft is rewritten (at most twice) or not sent.
6. **Reading the reaction.** An LLM judge rates scepticism and spots disclosures or acts; code
   double-checks it (a "disclosure" that repeats our own words is discarded, an "action" must be a
   completed act in their own words, a polite boundary with a commitment is not hostility).
   Opened files and links are *steps*; only a typed secret, internal information or a completed act
   counts as an objective.
7. **Adapting.** Doubt is answered once or twice, silence gets one follow-up, a refusal switches to a
   different story. In practice every story gets a fresh session; across scoring runs on the same
   person, stories that already failed are tried last.
8. **Replay** (`viewer/`). Every decision is saved with its reasoning, score and rejected
   alternatives, so a whole run can be replayed turn by turn in the browser.

Models: DeepSeek-V4-Flash writes and judges (Qwen3.8-27B as fallback); recon extraction uses
GPT-4.1-mini when an OpenAI key is set, otherwise Qwen3.8-27B (as in our runs). All are called
through OpenAI-compatible endpoints.

The architecture diagram is in [`docs/architecture.pdf`](docs/architecture.pdf).

## Results, honestly

- On the hidden scoring targets, one of three (a VC partner) volunteered the same internal detail
  about his firm on the **first contact in all four sessions**, each time to a different invented
  sender. The other two engaged in long threads but gave nothing internal.
- Between scoring runs the agent adapted on its own: on one target, the run after a failed one led
  with a different story on his own topic and got a firm commitment to reply by a set date.
- No target typed a credential or approved anything for us.

What we learned: careful people don't fall for clever messages, they fall for **relevant** ones; and
every mistake the agent made (a typo domain, a reused phone number, a claimed shared event) is a
red flag employees can learn to spot.

## Running it

Python 3.11+.

```bash
uv sync                       # creates .venv and installs deps (add --extra quality for the screenshot tools)
cp .env.example .env          # add the keys you have; see below
uv run python -m pytest -q    # offline tests, no API calls
```

Run the commands below with `uv run` (e.g. `uv run python -m backend.orchestrator julius`), or
activate the venv once with `source .venv/bin/activate` and drop the prefix.

The agent needs `REVEL8_API_KEY` (from revel8, for their simulation API) and `RADEON_API_KEY` (the
model endpoint); recon also uses `OPENAI_API_KEY`, `TAVILY_API_KEY`, `SERPER_API_KEY` and
`BRIGHTDATA_API_KEY` when set.
Keys are read from `.env` only and never committed.

```bash
python -m backend.recon "Full Name" "Company" "Role"     # research a target → runs/profiles/
python -m backend.orchestrator <target_id>               # practice run
python -m backend.orchestrator <target_id> --eval        # scoring run: one session, 10 contacts
python viewer/serve.py 8766                              # replay viewer → http://127.0.0.1:8766
```

Without revel8's API, the **local test bench** plays 14 fictional personas behind a copy of the API,
with hidden ground truth (topic hits, suspicion, what they disclosed):

```bash
python -m bench.server                                   # http://127.0.0.1:8770/v1
python -m backend.recon --bench lukas
REVEL8_API_URL=http://127.0.0.1:8770/v1 python -m backend.orchestrator lukas --eval
```

More commands and flags: [`RUNNING.md`](RUNNING.md).

## Repository layout

| Path | What |
|---|---|
| `backend/orchestrator.py` | The agent loop: sessions, approaches, calls, mails, judging, adapting |
| `backend/recon/` | Research pipeline: search, LinkedIn, GitHub, DNS, extraction, verification, hooks |
| `backend/revel8.py` | API client with idempotency keys, retries and per-session logs |
| `backend/outcomes.py` | What counts as an objective versus a step |
| `strategy.py` | Story library, ranking, stated needs, next-move rules |
| `writer.py` | Sender invention, message and call-line writing, landing pages |
| `quality/` | Checks before sending, checked API client, research gate |
| `bench/` | Local test bench with fictional personas and ground truth |
| `viewer/` | Read-only replay viewer |
| `scripts/chat.py` | Manual practice console (practice only, never for scoring) |
| `legacy/` | Earlier code superseded during the hackathon, kept for reference |

## Team

Built in 24 hours by the SchnitzelStrikers: Chye Yu En (agent loop, API client, schemas),
Sherwin (recon), Izen (strategy, writing), Theja (quality gate, architecture, pitch) and Neryss
(test bench, replay viewer, strategy and conversation engine).
