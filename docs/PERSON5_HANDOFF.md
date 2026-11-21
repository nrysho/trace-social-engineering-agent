# Person 5: integration-first handoff

Based on main 1c68d1f and the supplied teammate brief. Use this small PR stack
instead of merging the older full theja-person5-main package into main.

## Review order

1. theja-gate-integration -> main: actual message/page/call enforcement, selected
   eval scenario, practice-only bypass, bounded correction and saved QA verdicts.
2. theja-story-checks -> theja-gate-integration: date/time contradictions block;
   count/name/organisation changes warn; known unverified factual assertions block.
3. theja-craft-checks -> theja-story-checks: offline 700/1200 px renders and
   provisional four-question craft comparison. This never blocks sending.
4. theja-qa-metrics -> theja-craft-checks: QA/craft fields in the existing viewer
   API, with no duplicate incident-rate, hook or touch calculations.
5. theja-qa-handoff -> theja-qa-metrics: architecture, decisions, pitch and
   reproducible local-bench backup recording.

Each PR targets its predecessor so its diff stays small. Retarget subsequent
PRs to main after their dependencies land. These branches are published, not
automatically merged; main is not protected by them until the integration lands.
The tip of theja-qa-handoff contains the combined implementation for testing.

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

- Mavis reviews/merges the first PR, tests her real writer and supplies actual
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

Current PRs in order: #10, #13, #14, #15, #16. Refreshed after main merged recon and profile replay (1c68d1f). Event arrays are now keyed by contact node, complete bundles take precedence over bare trees, and the existing Results/Progress implementation remains intact.
