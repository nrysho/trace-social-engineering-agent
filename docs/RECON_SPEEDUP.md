# Recon speedup investigation

What makes `backend/recon/profiler.py build()` slow, measured, and what I changed.

Short version: the two serial LLM extraction chains (`company` osint and person
`extract`) were the bottleneck, just as the code comments suspected. I made them run
concurrently with a bounded gate. That cuts the recon compute on the critical path from
about 20 s to about 8 s with no measured quality loss and no fallback to the slow qwen
model. The remaining and now dominant cost is the BrightData LinkedIn scrape, a single
synchronous call recon cannot parallelise, which swings from 12 s to 60 s and sets a
floor on the total.

## How I measured

- A harness (not committed) monkeypatched each phase of `build()` to time it, and
  wrapped `llm._one_call` to record every LLM call's latency, which provider answered
  (openai vs qwen), and whether it retried or failed. No source was changed during
  baselining.
- Baseline: the three practice founders (Julius Muth, Robert Seilbeck, Tom Müller), all
  at `revel8`, 3 runs each. Web and API latency is noisy, so I report medians and the
  spread, not single numbers.
- Recon never calls the revel8 target API. Its cost is web search + page fetches + LLM
  calls. The numbers below are wall-clock seconds.

## Baseline: where the time goes

Median of 3 runs per founder. Phases inside the 5-worker pool (`company`, `extract`,
`linkedin`, `dns_tech`, `github`) run concurrently, so the pool takes the longest of
them; `search`/`deepen` run before it and `verify`/`hooks` after it.

| Target | Total | company | extract | linkedin | verify | hooks | search | LLM calls | qwen |
|--------|------:|--------:|--------:|---------:|-------:|------:|-------:|----------:|-----:|
| Julius | 36.0  | 18.4    | 21.6    | 12.8     | 3.4    | 3.3   | 2.7    | 16        | 0    |
| Robert | 34.8  | 20.2    | 11.7    | 20.1     | 3.6    | 3.2   | 3.4    | 16        | 0    |
| Tom    | 31.1  | 20.2    | 9.2     | 14.5     | 3.4    | 3.4   | 2.2    | 16        | 0    |

Per-run totals (shows the variance): Julius 29.6 / 58.9 / 36.0, Robert 35.9 / 34.8 /
34.0, Tom 35.6 / 31.1 / 30.8. The big Julius outlier was one slow LLM/search window, not
a different code path: the call count was 16 every time.

### The bottleneck, in numbers

1. The pool is dominated by two serial LLM chains running concurrently: `company`
   (~18-20 s) and `extract` (~9-22 s). `company` is the steadier and usually larger of
   the two. This matches the "sequential on purpose" comments in `extract.py` and
   `company.py`.
   - `extract` loops result chunks one at a time (24 results / CHUNK 6 = 4 serial calls).
   - `company` extracts its 3 aspects (relationships, open roles, events; the investor
     `fund` aspect is gated off for an operating company) one after another, each aspect
     chunking its pages serially. That is the longest serial chain: ~9-10 LLM calls.
2. Every run made exactly 16 LLM calls, every call was answered by OpenAI
   (`gpt-4.1-mini`), and qwen was never used and nothing failed. The current code already
   runs 2 LLM chains concurrently (the extract thread and the company thread), so there
   were already ~2 OpenAI calls in flight, with no rate-limiting.
3. `linkedin` is not an LLM call. It is one synchronous BrightData profile scrape, 12-20 s
   at baseline and up to 60 s when BrightData is busy. It runs inside the same pool, so it
   is "free" up to its own duration, but it sets a floor: shrinking the LLM chains below
   it stops helping. For Robert at baseline it already tied `company` as the bottleneck.

So the guess (serial LLM extraction) was right about the compute, with one correction the
data forced: LinkedIn/BrightData co-sets the pool floor and is the larger source of
total-time variance.

## What I tried

Three levers, each measured on all three founders, 3 runs each (27 builds), with the same
harness. Phase medians are cleaner than totals because they exclude the noisy LinkedIn
floor.

| Lever | What it does | company | extract | LLM calls | qwen | quality |
|-------|--------------|--------:|--------:|----------:|-----:|---------|
| base  | unchanged (serial) | 18-20 | 9-22 | 16 | 0 | - |
| par   | parallel aspects + parallel extract chunks | **7-8** | **5-6** | 16 | 0 | same |
| chunk | CHUNK 6 -> 12 (fewer, bigger prompts) | 16-19 | 6-13 | 11 | 0 | lower yield |
| both  | chunk + par | 8 | 5-6 | 11 | 0 | chunk's risk |

- **par wins.** It issues the byte-identical LLM calls (same prompts, same chunks,
  `temperature=0`), only concurrently, so no individual call's output can change. It cut
  both bottleneck phases ~60-65%. Across all 9 par runs: qwen=0, failures=0. The heavy
  fan-out (peaking around 13 concurrent OpenAI calls) did not trip 429s or the qwen
  fallback. The stated reason for keeping extraction serial does not hold at this scale.
- **chunk loses.** It barely helps `company`, because that chain's length is the number
  of sequential aspects, not chunks within an aspect. It also changes the prompts (12
  results per call), and the data shows lower fact yield (Julius 37 -> 28, Tom 38 -> 25
  median facts). More risk, less benefit.
- **both** inherits chunk's prompt change for no speed gain over par. Rejected.

### Quality guardrail: par is behaviour-preserving

The worry with par is that a faster profile might be a worse one. Two controlled tests on
fixed inputs (same captured search results, so no live-search noise) show it is not:

1. Serial vs parallel extraction on the identical result set produced the same substance:
   same clients (OBI, Association of German Banks, Alexander Burkle), same open roles,
   same employment history (PwC, Celonis, Project A), same interests (deepfakes, voice
   cloning, WhatsApp phishing). Counts were near-identical (person 27 vs 28, company 21 vs
   20). Only wording differed ("ex-colleagues" vs "former colleagues").
2. To check that difference is just the model, I ran serial extraction three times on the
   identical input. Exact-match Jaccard between two serial runs was 0.18-0.29, with counts
   swinging 26 / 28 / 32. In other words, `gpt-4.1-mini` at `temperature=0` already drifts
   that much run to run. The serial-vs-parallel difference is no larger than serial vs
   serial, so parallelising adds no quality change.

Verified-fact counts held or improved after the change (matched A/B below: serial
[8,9,4,11] vs par [9,12,10,12]). Hook counts and ordering were unaffected (6 hooks
proposed, top 5 kept, every run).

## The change

`par`, with a conservative guard. Edits in `backend/recon/extract.py` and
`backend/recon/company.py`:

- `extract.extract_facts`: the result chunks now run in a `ThreadPoolExecutor` (was a
  serial loop). `ex.map` preserves input order, so the merged fact list stays stable.
- `company._extract_pool`: an aspect's page chunks now run concurrently.
- `company.collect`: the aspects themselves now extract concurrently (they were the
  longest serial chain).
- A shared `threading.Semaphore(8)` (`extract._LLM_GATE`, imported by `company.py`) caps
  how many extraction LLM calls are in flight across the whole recon stage. The unbounded
  version never tripped the rate limit in testing, but a cap is prudent for a busier key
  or a lower tier, and `llm.chat` still retries 429 and falls back on its own. 8 leaves
  the critical path unthrottled while staying clear of the limit.
- The "sequential: concurrent openai calls get rate-limited" comments were updated to
  state the measured behaviour, not deleted.

### After the change, measured

Phase times with the new code (Julius, 2 runs): `company` 8.8 / 8.0 s (was ~18 s),
`extract` 5.0 / 5.3 s (was ~22 s). Call count still 16, qwen 0, failures 0.

A matched interleaved A/B on Julius (serial then par, back to back, so both see the same
BrightData window) isolates the `extract` phase: serial median 14.7 s vs par median
3.7 s, a 4x cut, with par's verified-fact counts equal or higher. (BrightData was in a
slow spell during this A/B, 55-60 s scrapes, which swamped the totals and is exactly the
floor described next.)

### Honest limit: the LinkedIn floor caps the total

Total time = fixed serial work (search + deepen + verify + hooks, ~10 s) + the pool. After
the change the pool is `max(company 8, extract 5, linkedin)`, so it is now LinkedIn-bound.

- When BrightData is quick (~12-15 s), the change takes the total from ~30-36 s to
  ~21-25 s, a 25-35% win. That is what the par variant medians showed when they were
  measured: Julius 36 -> 30, Robert 35 -> 22, Tom 31 -> 21.
- When BrightData is slow (30-60 s), it dominates both the old and new code equally and
  the total win disappears. This is external to recon and the single biggest source of
  run-to-run variance.

So the compute win is real and consistent; whether it shows up in the headline total on
any given run depends on BrightData's mood.

## End-to-end practice run

Recon never calls the target API, so "testing recon on revel8" means running a full
practice session with the faster recon and confirming nothing regressed.
`python -m backend.orchestrator julius` (practice), with the cached profile moved aside so
recon ran fresh with the new parallel code:

- Recon ran clean: 24 results, 18 person facts + 31 company facts, LinkedIn anchor
  confirmed, 41 facts after verify, 5 hooks, profile written. No tracebacks, no refusals.
  Fact and hook counts are in line with the serial baseline.
- The loop then ran normally: ranked approaches, sent messages across linkedin_message,
  email, shared_document and two phone_call turns (in German), classified each reaction
  (reply / ignored), pivoted on silence and on persistent doubt, and saved a 30-node tree
  plus the replay bundle the viewer reads.
- Outcome: no incident this run (the twin stayed sceptical and the touch budget ran out),
  which is a normal practice result. The point was integration, not a win: the faster
  recon drops in with no change to the agent's behaviour downstream.

This confirms the change is safe end to end. It does not prove a scoring improvement; that
is measured server-side during the window.

## Recommendation

- Keep the change. It is a clear, low-risk compute win: identical LLM calls, no quality
  change, no qwen fallback, bounded concurrency, and it targets the phase the data named.
- Next lever, if more speed is wanted, is the BrightData LinkedIn scrape, now the floor
  and the largest variance. Options to weigh: a shorter BrightData timeout with a fallback
  to the snippet-only LinkedIn facts, caching the scrape per profile URL (helps rehearsal
  on known founders, not an unseen eval target), or dropping the scrape when its anchor
  facts duplicate what search already found. Each trades a verified employment anchor for
  speed, so measure the quality cost before shipping.
- Do not pursue `chunk`. It changes the extraction prompts for a smaller, riskier win.
