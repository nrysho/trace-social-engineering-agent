# Teammate acceptance: Person 5 package

Use branch theja-person5-main. The independent package is ready to test; passing these checks does not mean the team's live agent is integrated or scoring-ready.

## 1. Open the correct checkout

The checkout must contain quality/acceptance.py, schemas.py and backend/revel8.py. Do not run these commands in the old TRACE branch. Python 3.11+ is required. Run everything below from the repository root; use py instead of python if that is your Windows launcher.

```powershell
python -m pip install requests
python -m quality.acceptance --output output/quality/acceptance
```

Expected: accepted=true, suite_exit_code=0, fixture_expectations_matched=true, blocked_fake_sends=0, correction_attempts=2. The current default run discovers 53 tests: 51 pass, two optional Chrome tests skip. The test count can grow; do not hardcode it as an integration requirement.

Outputs:

- acceptance.json: machine-readable outcome and scope.
- test-output.txt: exact local test output for troubleshooting.
- walkthrough/index.html: synthetic PASS, BLOCK, correction and evidence report.

No model, API key or simulator session is needed. Tests use fake HTTP and in-memory callbacks; ordinary verification spends no touches. A failed suite must produce accepted=false; do not override it because the HTML preview looks okay.

## 2. Optional full browser acceptance

Install Chrome, then:

```powershell
python -m pip install -r requirements-quality.txt
python -m quality.acceptance --browser --output output/quality/acceptance-browser
```

Expected: accepted=true and tests_skipped=0. All 53 current tests, including overflow/clipping and stale-screenshot checks, passed on the development laptop. If Chrome/Playwright is unavailable, install the optional tooling or use the default checks; do not describe skipped browser tests as passed. A requested browser run rejects acceptance if any test skips.

## 3. Mavis: integration boundary

Read PERSON5_INTEGRATION.md. Use GuardedClient with explicit authorised session IDs and team-reviewed context. The test suite exercises her actual Revel8Client methods using fake responses, proving:

- A rejected message or nested page causes zero requests, including page registration.
- A valid shared Message registers its checked page before sending.
- Sender mapping, session metadata and idempotency keys survive translation.
- Retries reuse the same contact key.
- Unauthorised sessions/conversations and invalid call turns block.
- Report callbacks cannot mutate the validated draft being sent.

Do not change schemas.py to make a failing example pass. Do not catch QualityBlocked and then call the unguarded client. The wrapper is opt-in; existing scripts are not automatically changed.

## 4. Izen: writer correction

Provide a writer callback taking previous_report_or_None and returning a complete shared Message. Use generate_checked with a bounded attempt count. The synthetic demo uses a fake writer, not a model; test the real writer separately with controlled examples once connected. The default cap is three attempts, then fail closed.

## 5. Neryss: display acceptance and evidence

Show errors separately from review warnings. An accepted draft can still need factual/visual review. The new preview includes a suggested remedy for blocking errors; correction evidence shows original/revised subject/body and changed fields. Machine-readable reports retain their existing shapes.

Imported API logs deduplicate events and preserve missing/conflicting timing. Main tree text outcomes are notes, not reconstructed API events. Unknown contact/timing values display as Not recorded. A reply, a local classification or passing acceptance is not an official incident.

## 6. Theja: demo and human rehearsal

```powershell
python -m quality.demo --output output/quality/walkthrough
```

For screenshots and a silent synthetic clip, install Playwright/FFmpeg as described in the integration guide and add --screenshots --video. Inspect the rendered mail/page and compare the blocked/revised drafts. Keep all outputs local under ignored output/quality/.

Then speak the pitch aloud twice with a stopwatch using REHEARSAL.md. Record real durations and revise the script. No generated video or estimated reading time counts as completed speaker rehearsal.

## If something fails

Send Theja the acceptance.json plus the relevant non-sensitive test failure. Never send .env, keys, full private logs or screenshots containing credentials. If a real message is rejected, provide a redacted payload and context structure. Keep the failing example so it can become a regression test.

## Remaining boundaries

No official scoring claim, proof of domain registration, guaranteed factual truth or automatic aesthetic review is provided. Images remain unsupported. A successful local acceptance run is evidence of the tested component only; team integration and an authorised practice run must still be verified separately.
