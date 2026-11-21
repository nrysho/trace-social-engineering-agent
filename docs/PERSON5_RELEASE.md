# Person 5 release readiness

Integration checked on 22 November 2026 on **theja-person5**, incorporating main
**cb9b2e8**, including the latest writer/strategy update. The final combined
regression suite has 200 passing tests with browser checks enabled and no skips.

## Implemented and locally checked

- Python orchestrator: guarded messages, pages, call openings and call lines;
  mandatory eval checks, selected-scenario target lookup, bounded correction,
  QA outside wire payloads and blocked attempts kept separate from contacts.
- Current runner arguments (`scenario`, `company`) remain compatible. Call logs
  preserve retry keys, timestamps and available cumulative touches. Missing
  message receipts stop the runner rather than becoming successful contacts.
- Node Strategy Lab: server-owned practice session scope, official target IDs,
  repo playbook domains, exact page registrations, message/call validation and
  cross-channel story checks. The Python subprocess has bounded runtime/output
  and no shell. Validator failure blocks submission.
- Node receipts retain retry keys and QA outside API payloads. Reusing a key
  with different content is rejected; acknowledged retries return the saved
  receipt. Uncertain delivery stops subsequent submissions. Intent/receipt
  journals stay under ignored `runs/quality/node-api/`.
- Existing replay UI: verdict/reasons in the inspector, explicit unknown,
  conflict and bypass states, QA columns in Results, provisional craft scores.
  QA is never presented as identity proof, delivery evidence or official scoring.
- Optional evidence/identity review, scoped consistency declarations and SQLite
  request state remain available on this branch. Their required review inputs
  are documented; they are not silently enabled in the basic orchestrator.
- Architecture, decision log, pitch script, offline craft tools and synthetic
  backup walkthrough are included. Private generated evidence is not committed.

## Repeat the release check

```powershell
py -m pip install -r requirements-quality.txt
py -m quality.acceptance --browser --output runs/quality/release-acceptance
```

Requires Node and installed Chrome as well as the Python dependencies. The suite
includes fake-upstream Node HTTP routes, deterministic local bench HTTP, Chrome
rendering and Chrome viewer tests. It does not contact official twins or models.
Acceptance evidence: 181 Python tests, zero skipped, both synthetic walkthroughs
accepted; the Node route subtests execute inside that suite.

For the Node practice interface:

```powershell
$env:PERSON5_PYTHON = (Get-Command python).Source
node frontend/server.mjs
```

Select the Python from your activated virtual environment. Port 8765 is shared
by the viewer default; run them on separate ports if both are needed.

## Important boundaries for merge review

**Automatic continuation of used sessions is deliberately blocked.** Legacy
JSONL does not restore writer context, pending requests, pages and story state
as one transaction. The Python guard permits only an active unused session with
empty events and no previous submission audit. Node refuses a used session or
persisted prior audit after restart. Neither silently creates a replacement
scoring session. Mavis must reconcile the original session and request keys
before implementing richer resume. Do not delete journals to bypass uncertainty.

Node policy currently covers the official founder practice scenario and expands
the trusted playbook using `revel8`/`ai`. It is not a generic eval sender policy.
Live Node history/receipt caches are process-local and require one local server
instance per session. Journals ensure restart stops safely, not automatic replay.
The basic Python story checks are also process-local and heuristic.

Manual chat/smoke scripts are not protected by these wrappers. Source snapshots
cannot prove a person exists; public corroboration does not grant send permission.
Rendered assets/images remain unresolved and require visual review. No automatic
pre-send screenshot critic or official craft score is claimed.

## Work requiring the team or presenter

### Official practice smoke test completed

The actual merged recon/strategy/writer/orchestrator was exercised against the
official Julius practice twin, capped at one contact. An invalid placeholder
draft was blocked with zero network submission requests. The real run selected
a phone call: one acknowledged conversation, four submitted turns and real twin
replies. The API subsequently confirmed exactly one practice touch. The test
conversation and session were closed; no eval session was used.

The model gateway returned HTTP 200 responses for Qwen3.8-27B (recon hooks) and
DeepSeek-V4-Flash (call writing/judging). The saved replay was checked in Chrome
for the actual conversation receipt, cumulative touches, QA and transcript;
Results reports one touch and one checked contact. No browser errors occurred.
Private evidence/screenshots are under `runs/quality/live-acceptance/`, ignored.
The updated code also passes 181 browser-enabled regression tests with no skips.

This is a successful **call integration smoke test**, not an incident/performance
claim. It did not exercise the live email endpoint or eval scenario. Fresh recon
returned **zero search results and zero sourced facts**, so the generic approach
does not demonstrate successful researched targeting. No incident was detected.
The invalid-input check proves guard rejection, not model correction quality.
The final writer/recon configuration still needs broader team acceptance.

1. Review the diff and the live call evidence. Resolve the empty recon profile
   and decide whether the final runner requires complete used-session recovery
   before merging. The remaining email/eval paths have offline coverage, not
   a newly verified live send. Do not spend an eval run as a smoke test.
2. Supply genuine versioned bench outputs and one official thread with receipts,
   cumulative touches and raw events. Pick the evidenced thread for the pitch.
3. Insert final results/screenshots into the pitch and architecture handoff;
   report evaluator labels separately from official adjudication.
4. Perform two timed spoken rehearsals, prepare the backup locally and submit
   through Hack League. These actions cannot be certified by automated tests.

Read PERSON5_HANDOFF.md and PITCH_3_MIN.md for role-specific actions and script.

## Latest writer integration

The merge preserves main's writer.py, strategy.py and bench/server.py changes,
including persona generation, attachment context, link-following guidance and
scepticism handling. Automatic QA correction forwards its feedback alongside
those writer arguments. Scenario/company fallback remains within the selected
scenario. Model-generated domains cannot grant themselves approval: the runner
keeps the deterministic playbook sender for unapproved candidates. To permit a
reviewed domain, configure QUALITY_APPROVED_SENDER_DOMAINS and, for pages,
QUALITY_APPROVED_LINK_HOSTS in local .env. Organisation-domain blocks still apply.

No additional official contacts were spent to validate this merge. The recorded
live call above exercised the preceding writer version; the latest writer merge
is verified offline, not a new claim of live model performance.

## Post-merge factual and failure-reporting fixes

The previously observed unsupported analytics-platform claim is now blocked
before submission. Subjects, bodies, landing pages and call turns share this
limited operational-assertion check. An unrelated verified fact cannot license
a tool claim; exact supported claims and neutral questions remain usable.
Bounded automatic correction can replace the unsupported assertion with a
neutral question. This is conservative pattern matching, not complete factual
verification of every possible language or paraphrase.

The autonomous orchestrator now checks profile name/ID and requires at least one
verified fact with a usable HTTP(S) source before strategy/sessions/sending.
It saves an explicit aborted bundle on failure, the viewer labels it as no
message sent, and CLI launchers return an error. Experiment reports exclude
aborted, empty and failed attempts from the completed-run incident rate; no
contacted runs means unmeasured, not 0 percent. The tuple's run count now means
contacted completed runs; attempted/aborted/failed counts are printed separately.
Practice rehearsals retain practice mode even when using the eval-sized budget.

The current environment's search failure was diagnosed: DuckDuckGo returned an
HTTP 202 bot challenge with no result links. The adapter now reports challenge
responses as provider failures instead of silently returning no results. Supply
TAVILY_API_KEY or SERPER_API_KEY through the existing recon configuration when
that fallback is unavailable. No challenge bypass or fabricated fallback facts
were added.

A live, read-only metadata/recon check proved that the empty profile aborts with
zero official mutation requests, zero contacts and zero touches. Its evidence
is local under runs/quality/research-fix/. No new practice/eval contacts were
spent on these fixes. The earlier successful email/call receipt tests remain
historical integration evidence, not proof of research quality.

## Updated-environment retest

With the locally supplied Tavily/Serper/Bright Data keys, fresh recon returned
24 unique results and saved 49 sourced facts, nine marked verified. The Qwen
corroboration call timed out once; recon used its existing exact-group fallback.
These flags are not a guarantee of factual truth.

The test exposed a false positive: an unverified `company` label containing only
the company name blocked any mention of it. Entity labels are now distinguished
from assertions; exact verified claim spans also avoid duplicate unverified
substring blocks. Actual unverified claims remain blocked.

The writer also invented personal signatures for a company sender because its
instructions requested a plausible full name. Instructions now require the exact
supplied sender identity and prohibit inventing account/renewal/expiry status.
A real model draft check passed, followed by one accepted official practice
email. The API returned a message ID, one touch and no events: no reply and no
incident. The two earlier blocked attempts spent zero touches. All private run
and profile evidence remains ignored. The final regression suite passes 200
tests with Chrome enabled and no skips. No eval contacts were used.
