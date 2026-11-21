# Person 5: integration-first handoff

## Use one branch: theja-person5

The five former PR branches have been consolidated into **theja-person5**.
All their commits are retained in its history. PRs #10, #13, #14, #15 and #16
were closed without merging. No work was merged or pushed into main.

The consolidated branch contains:

1. Actual message/page/call enforcement, explicit eval scenario, practice-only
   bypass, bounded correction and saved QA verdicts.
2. Story/date/time checks, profile-fact warnings/blocks and greeting/signature checks.
3. Offline 700/1200 px craft renders and provisional comparison scores.
4. QA/craft additions to the existing viewer API without another results engine.
5. Architecture, decisions, pitch and synthetic bench backup recording.

The old recent branch names are redundant and have been removed after verifying
that each tip is an ancestor of the consolidated branch. The earlier theja-branch
and theja-person5-main branches remain intact because they contain distinct work.
This is branch consolidation, not deployment: main does not acquire these guards
until someone separately reviews and merges the desired changes.

## Run acceptance locally

```powershell
git fetch origin neryss/profile-replay
py tests/prepare_bench_fixture.py
py -m pip install -r requirements-quality.txt
$env:PERSON5_BROWSER_TESTS='1'
py -m unittest discover -s tests -v
```

Verified: 38 tests pass with browser checks enabled, zero skips. These include
actual loopback HTTP against Neryss's bench, with a deterministic fake persona
engine and external HTTP prohibited. No real revel8 session, scoring contact
or external model request was made. Tests use fictional people and .example domains.

Core acceptance proves that eval uses its 10-touch bench budget; blocked drafts
cost zero; correction receives feedback and sends once; QA stays outside API
payloads; and an already opened call remains one touch if its next line is blocked.
Bare trees round-trip through unchanged shared schemas. Replay bundles carry QA
overlays without adding dataclass fields.

## Where QA is stored

Verdict: `{passed: bool, errors: [text], warnings: [text]}`. Practice bypass adds
`bypassed: true` and a warning. It cannot be selected in eval.

- `kind=sent` API log entry: `qa` beside `message`, never inside its request body.
- Replay `messages[]`: `qa`, plus original node/session IDs.
- Replay `nodes[]`: `qa` overlay; blocked candidates are attempts with no sent message.
- Calls: opening QA describes the actual contact; failed lines are separate
  quality log entries and warnings, not evidence that the call cost zero touches.

Neryss's described QA UI changes are still local/unpublished in the inspected
viewer branch. This work supplies the contract and server fields without
overwriting that UI. `/api/quality/versions` reports QA only; set an explicit
agent_version and select the annotated craft bundle instead of duplicate copies.

## Craft and backup

```powershell
py -m quality.craft runs/RUN_ID.json --output runs/craft/RUN_ID --approved-domain events.example
py tests/record_quality_demo.py
```

Use the run's actual approved domains for rendering. The backup utility creates
two labelled synthetic bench runs, an email render, replay screenshots and
`runs/quality/backup/person5-bench-backup.webm`. Playwright's FFmpeg component and
Chrome must be installed for recording. The produced video is silent and was
visually checked; it does not replace a verified real-thread demo or rehearsal.
All generated runs, screenshots and video remain ignored/local.

## What remains for the team

- Mavis reviews the consolidated branch, tests her real writer and supplies actual
  v1/v2/v3 bench outputs with provenance/version labels. None were invented here.
- Neryss publishes her QA UI and verifies it against the saved verdict contract.
- Izen's separate Node send routes still need their own server-side guard.
- Sherwin supplies target profiles and evidence; heuristics do not prove identity,
  source independence, factual completeness or domain registration availability.
- Theja inserts real Progress/replay screenshots, selects one evidenced official
  practice/scoring thread, performs two timed spoken rehearsals and submits.

See ARCHITECTURE.md, DECISIONS.md and PITCH_3_MIN.md. No human approval is added
inside scoring runs. Active calls, uncertainty reconciliation and process-local
story state still need the runner's resume policy; no crash-safe story guarantee
or automatic model-performance improvement is claimed.

Historical PRs #10, #13, #14, #15 and #16 are closed. The implementation was checked against main 1c68d1f. Event arrays are now keyed by contact node, complete bundles take precedence over bare trees, and the existing Results/Progress implementation remains intact.
