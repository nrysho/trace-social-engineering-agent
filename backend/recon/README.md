# recon

Turn a **name + company** into a **sourced profile**: verified facts (each with a
source url), ranked hook hypotheses, and an exposure score. This is everything the
agent needs before it makes contact. Nothing here touches the revel8 API; it only
produces a `Profile`.

```bash
uv run python -m backend.recon "Julius Muth" "revel8"
# -> runs/profiles/julius-muth.json  (dense, for agents and the frontend)
# -> runs/profiles/julius-muth.md    (readable, for humans and the pitch)
```

## Why it is built this way

The jury deducts up to **-5 for wrong facts**, and the twins can look things up
before reacting, so a confident-but-wrong claim is worse than no claim. Every fact
therefore carries the url it came from, and a fact is only marked **verified** when
two independent domains agree. Noisy sources are allowed in, but only through a
match gate, so the wrong person's data never lands in the profile.

## Pipeline

```
  name + company
       |
       v
  queries.py ---- ~9 search queries: name+company, talks, podcasts,
       |          github, news, events, jobs, social
       v
  search/ ------- tavily + serper (keyed)  |  ddg lite (free fallback)
       |          merge results, dedup by normalised url
       v
  fetch.py ------ read full page text for results that only had a snippet
       |          (linkedin is skipped here; handled below)
       |
       +-------------------------+--------------------------+
       v                         v                          v
  extract.py                 dns.py                    linkedin.py
  llm pulls sourced          mail provider +           bright data scrapes
  facts, each tagged         saas vendors from         the profile url; its
  with a source url          the company domain        name+company is the
       |                         |                     ANCHOR
       |                         |                          |
       |                         |                     match.py gate:
       |                         |                     keep it only if name
       |                         |                     and company match
       +------------+------------+--------------------------+
                    v
               verify.py ---- group facts that make the SAME claim (llm),
                    |         mark verified when >=2 distinct domains agree,
                    |         annotate [disputed: ...] when sources contradict
                    v
               hooks.py ----- llm proposes ranked hooks
                    |         (topic, p, evidence, their_topic | own_angle)
                    v
             exposure.py ---- deterministic 0-100 surface score
                    v
              profiler.py --- assemble the Profile, write json + md
```

## Key ideas

- **Sourced facts.** `extract.py` only keeps a fact if its `source_url` was one of
  the urls actually passed to the model, so nothing is invented.
- **Verification by meaning.** `verify.py` asks the model to group facts that make
  the same claim (wording varies across sources), then **domains decide**: a group
  spanning two or more distinct domains is `verified`. The model groups; it never
  asserts truth on its own.
- **Dispute flagging.** When sources contradict (e.g. two different cities), the
  claim is left unverified and tagged `[disputed: ...]` inside the fact value, so
  the annotation survives into the json the agent reads.
- **LinkedIn anchor + match gate.** `linkedin.py` (Bright Data) scrapes the profile
  url that search found; `match.py` accepts it only if its name and company match
  the target. That confirmed name+company is the anchor every other noisy source
  (github, podcasts, ...) is then checked against.
- **Structured signals.** `dns.py` reads MX and SPF records to name the mail
  provider and the saas vendors a company uses - each one a pretext lead, for free.

## Hooks and the `p` value

A **hook** is a topic the target is likely open to right now (a speaking invite, a
vendor renewal, an investor intro, ...). Each has:

- `p` (`probability`, 0-1): the model's estimate of how open they are to this topic
  now. It ranks the hooks and feeds the exposure score. It is a judgment from the
  evidence, not a calibrated probability - read it as relative priority.
- `evidence`: the facts the hook rests on.
- `angle`: `their_topic` (a likely planted interest, worth 6 pts of targeting) or
  `own_angle` (a topic they were not set up for, worth the 4-pt bonus).

## Exposure score

A deterministic 0-100 heuristic (no llm, so it is reproducible) for the pitch. It
mixes verified-fact count, category breadth, source diversity, recency,
contactability, and the top hook's `p`, and returns a per-metric breakdown. It
measures attackable surface, not a calibrated chance of success; the constants are
a first cut.

## Output

The `Profile` (see root `schemas.py`, shared with the rest of the team) carries
`facts`, ranked `hooks`, `exposure_score` + `exposure_breakdown`, and `sources`.
Written as both dense json (agents, frontend) and markdown (humans, pitch).

## Keys (`.env`)

- `OPENAI_API_KEY` - extraction, verification and hooks (gpt-4.1-mini). Falls back
  to Qwen on the AMD endpoint via `RADEON_API_KEY`.
- `TAVILY_API_KEY`, `SERPER_API_KEY` - search. Without them, search falls back to
  the free ddg lite scrape.
- `BRIGHTDATA_API_KEY` - the LinkedIn anchor. Without it, the anchor step is
  skipped and search snippets carry the LinkedIn signal instead.

## Limitations

- Fact counts vary a little run to run (the grouping model is not fully
  deterministic even at temperature 0); verified facts are always genuinely
  multi-domain, so correctness holds.
- Recency scoring is coarse until facts carry parsed dates.
- GitHub, podcasts and news are not yet wired in as collectors - they slot behind
  the same `match.py` gate when added.
