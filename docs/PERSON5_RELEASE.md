# Person 5 release readiness

Prepared on 21 November 2026 on **theja-person5**, incorporating main **29fa0fc**.
Main has not been changed. Review and merge this branch separately.

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

1. Review the diff and exercise the actual final writer/recon in an authorised
   practice run. Offline fake responses do not certify model availability or
   the official service's behaviour. Do not spend an eval run as a smoke test.
2. Supply genuine versioned bench outputs and one official thread with receipts,
   cumulative touches and raw events. Pick the evidenced thread for the pitch.
3. Insert final results/screenshots into the pitch and architecture handoff;
   report evaluator labels separately from official adjudication.
4. Perform two timed spoken rehearsals, prepare the backup locally and submit
   through Hack League. These actions cannot be certified by automated tests.

Read PERSON5_HANDOFF.md and PITCH_3_MIN.md for role-specific actions and script.
