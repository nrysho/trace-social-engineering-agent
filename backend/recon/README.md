# recon

Turn a **name + company (+ role)** into a **sourced profile**: verified facts (each
with a source url and a date), ranked hook hypotheses, an exposure score, and the
company's tech stack. Everything the agent needs before it makes contact. Nothing
here touches the revel8 API; it only produces a `Profile`.

```bash
uv run python -m backend.recon "Julius Muth" "revel8" "Co-Founder and CEO"
# role is optional but sharpens matching for low-profile people
# -> runs/profiles/julius-muth.json  (dense, for agents and the frontend)
# -> runs/profiles/julius-muth.md    (readable, for humans and the pitch)
```

## Why it is built this way

The jury deducts up to **-5 for wrong facts**, and the twins can look things up
before reacting, so a confident-but-wrong claim is worse than no claim. Every fact
carries the url it came from; a fact is only **verified** when two independent
domains agree; and the pipeline refuses to attribute a colleague's or founder's
facts to the target. Accuracy beats completeness - a sparse true profile wins.

## Pipeline

```
  name + company [+ role]
       |
       v
  queries.py ---- ~9 search queries: name+company, talks, podcasts,
       |          github, news, events, jobs, social
       v
  search/ ------- tavily + serper (keyed)  |  ddg lite (free fallback)
       |          merge results, dedup by normalised url
       |
       |--> domains.resolve(company) --> the company's web domain
       |            |
       |            v
       |       dns.py + tech.py -- what the COMPANY runs: mail provider, spf
       |                           vendors, dns txt verification tokens, a
       |                           microsoft 365 realm check, website fingerprint
       |                           -> vendors_and_tools facts (pretext leads)
       v
  fetch.py ------ read full page text for results that only had a snippet
       v
  extract.py ---- llm pulls facts about ONLY the target (name + role + company);
       |          facts about colleagues, the founder or a namesake are dropped,
       |          each kept fact tagged with a source url, a date and a confidence
       |
       |--> linkedin.py (ANCHOR) -- bright data scrapes the name-matched profile;
       |        match.py confirms the full name (via the url slug) plus company or
       |        role before trusting it, so the wrong person never contaminates
       v
  verify.py ----- group facts making the SAME claim (llm), verify on >=2 domains,
       |          annotate [disputed: ...] when sources contradict
       v
  hooks.py ------ ranked hooks (topic, p, evidence, angle), recency-weighted
       v
  exposure.py --- deterministic 0-100 surface score
       v
  profiler.py --- assemble, sort facts newest-first -> json + md
```

## Key ideas

- **Sourced facts.** `extract.py` keeps a fact only if its `source_url` was one of
  the urls passed to the model, so nothing is invented.
- **High-confidence, role-aware identity.** `match.py` requires the target's full
  name (matched against the LinkedIn url slug, which survives display quirks like
  "Julius M.") plus a company or job-title corroboration. Extraction is told who
  the target is and ignores everyone else on a shared company page. This is what
  keeps a low-profile person's profile from filling up with their founder's data.
- **Verification by meaning.** `verify.py` asks the model to group facts that make
  the same claim, then **domains decide**: a group across two or more distinct
  domains is `verified`. Contradictions are left unverified and tagged `[disputed]`.
- **Time matters.** Each fact carries a date; `recency.py` weights fresh facts
  higher, the current role is picked by the anchor company, facts sort newest-first,
  and hooks lean on recent activity. LinkedIn post dates are decoded from the
  activity id in the url, beating the model's guess.
- **Company tech stack.** `domains.py` resolves the company domain; `dns.py` and
  `tech.py` then fingerprint what the company runs - the mail provider (MX), SPF
  vendors, DNS TXT verification tokens (DocuSign, Atlassian, Zoom, Slack, Adobe,
  Okta, Stripe and ~40 more), a definitive Microsoft 365 realm check, and homepage
  scripts (HubSpot, Intercom, Segment, Stripe, analytics...). Each is a pretext lead.

## Hooks and the `p` value

A **hook** is a topic the target is likely open to right now (a speaking invite, a
vendor renewal, an investor intro, ...). Each has:

- `p` (`probability`, 0-1): the model's estimate of how open they are to this topic
  now. It ranks the hooks and feeds the exposure score. It is a judgment from the
  evidence, not a calibrated probability - read it as relative priority.
- `evidence`: the facts the hook rests on.
- `angle`: `their_topic` (a likely planted interest, 6 pts of targeting) or
  `own_angle` (a topic they were not set up for, the 4-pt bonus).

## Exposure score

A deterministic 0-100 heuristic (no llm, reproducible) for the pitch: verified-fact
count, category breadth, source diversity, recency, contactability, and the top
hook's `p`, with a per-metric breakdown. It measures attackable surface, not a
calibrated chance of success; the constants are a first cut.

## Output

The `Profile` (root `schemas.py`, shared with the team) carries `facts` (each with
`source_url`, `date`, `verified`, `supporting_urls`), ranked `hooks`,
`exposure_score` + `exposure_breakdown`, and `sources`. Written as both dense json
(agents, frontend) and markdown (humans, pitch).

## Keys (`.env`)

- `OPENAI_API_KEY` - extraction, verification, hooks (gpt-4.1-mini). Falls back to
  Qwen on the AMD endpoint via `RADEON_API_KEY`.
- `TAVILY_API_KEY`, `SERPER_API_KEY` - search. Without them, search falls back to
  the free ddg lite scrape.
- `BRIGHTDATA_API_KEY` - the LinkedIn anchor. Without it, the anchor step is skipped.
- Domain resolution and the tech-stack probe use public DNS, a Microsoft endpoint
  and the company website - no key.

## Limitations

- Fact counts vary a little run to run (the grouping and extraction models are not
  fully deterministic even at temperature 0); verified facts are always genuinely
  multi-domain, so correctness holds.
- A role listed on LinkedIn without an end date reads as current even if the person
  has left; the anchor company still wins the "current role" slot.
- GitHub, podcasts and news are not yet wired in as collectors - they slot behind
  the same `match.py` gate when added.
