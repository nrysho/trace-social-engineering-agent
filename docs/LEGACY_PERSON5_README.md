> Historical standalone handoff. Use [the current handoff](PERSON5_HANDOFF.md).

# Person 5: what Theja built and what the team must connect

> **Current handoff:** Read [docs/PERSON5_COMPLETION.md](PERSON5_COMPLETION.md) for current implementation, 130-test acceptance, demo commands and teammate actions. Test totals below describe earlier iterations. Guards remain opt-in; production adoption and human rehearsals are not established by offline tests.


**Start here if you want to understand or use Theja's work.**

Theja built the **quality-control and evidence part** of SchnitzelStrikers. The package checks generated content, helps the writer correct it, and explains what happened in saved runs.

**The code is on `theja-person5-main`. It is not automatically active in all team send paths.** Do not assume a message is checked just because this package exists in the repository.

## The simplest explanation

The intended connected flow is:

```text
Sherwin: researched facts
          ↓
Izen: strategy and generated message
          ↓
Theja: check the complete draft
          ├─ BLOCK → return errors to writer → limited retries → stop if still invalid
          └─ PASS  → Mavis: send through the official simulation API
                                  ↓
                         Actual response/events
                                  ↓
               Theja: evidence report → Neryss: replay viewer
```

This is the integration target. The adapters and correction helper are implemented, but teammates must select them in their actual paths.

For example, an email with a missing sender or `Hello {{name}}` is blocked. The report explains what needs fixing. A corrected draft can be checked again automatically. A passing draft can still have warnings: PASS does not prove that its facts are true or its visual design is excellent.

## What is implemented

### 1. Message, page and call-turn checks

`quality/checks.py` and `quality/integration.py` check shared messages, landing pages and spoken call lines for supported issues:

- Missing required content or sender details in a complete send-ready message.
- Unfinished placeholders and malformed field types.
- Sender/link domains outside the independently reviewed configuration.
- Known real organisation domains, including their subdomains.
- Displayed URLs that disagree with their destinations.
- Known simulator-directed instructions, active markup and possible leaked tokens.
- Supported attachment structure, count and call-turn length.

**It does not search the web to prove Julius exists.** It compares the recipient ID to the authorised target list supplied by the backend. If the list contains `julius`, a misspelling such as `julias` is blocked. The backend must obtain the correct list from the official scenario data. The checker does not independently fetch that list on every send.

It also does not prove factual truth, source independence, domain ownership or registration availability. Uploaded-image resolution remains unsupported.

### 2. Limited automatic correction

`generate_checked()` calls a supplied writer callback with the previous QA report. It permits a bounded number of attempts, then raises a blocking error if the draft still fails.

The helper does not choose or call a model itself. **Izen must connect her writer to the callback and consume its feedback.** A fake writer is used in our repeatable offline demo.

### 3. Guarded API client

`quality/guarded_client.py` wraps Mavis's existing `Revel8Client`. It checks complete messages and their pages before either page registration or message submission. It also checks call turns and restricts sessions/conversations to explicitly authorised scope.

The wrapper preserves the shared message format and retry keys. It supports practice-session creation and removes scope after a session/call is ended. Eval creation is intentionally not supported by this wrapper.

Tests exercise Mavis's actual client and current bare loop using **fake HTTP**, proving that rejected content makes no page/message request. This is not proof that the real loop currently selects the wrapper: **it still needs that adoption step.**

### 4. Results and decision evidence

`quality/results.py` reads main's tree arrays, API/chat logs and viewer bundles. It counts recorded evidence, deduplicates event IDs and leaves missing/conflicting timing unknown.

It preserves recorded reasons, alternatives and statuses. It does not invent hidden reasoning, convert every reply into a win, or turn an evaluator's `incident` label into an officially confirmed outcome. Official outcomes, hidden topic hits and craft scores remain unknown without authoritative evidence.

`quality/viewer_export.py` joins **one explicitly selected tree and API log** into Neryss's viewer format. It flags or rejects conflicting/missing joins rather than guessing. Call events without a tree-node association remain separately recorded.

### 5. Teammate adapters

- **Izen:** `quality/writer_adapter.py` accepts her `{content, model, fallback_used, refusal_logged}` result, maps sender `email` to the shared `address`, requires an explicit page URL, and preserves generation metadata outside the API body.
- **Sherwin:** `quality/profile_review.py` checks the shared profile's structure, categories, confidence bounds and evidence URLs. It never changes a fact to verified or performs research.
- **Neryss:** the replay exporter and report shapes support her viewer's profile/nodes/messages/events structure. A synthetic bundle was loaded in her actual viewer during local verification.

### 6. Craft and presentation materials

The optional offline Chrome renderer captures emails at 700 px and pages at 1200 px, with network and page scripts disabled. It flags horizontal overflow, clipped containers and excessive height. Mechanical checks do not award official craft points or replace visual/factual review.

The package includes a decision log, architecture diagram, pitch draft, rehearsal worksheet, acceptance checklist and a repeatable synthetic demo. Local screenshots and a silent backup video were produced. **Two actual timed spoken rehearsals are still pending.**

## What has been verified

- **76 tests passed with browser checks enabled; zero skips.**
- Default non-browser run: 74 pass and two optional Chrome tests skip.
- Rejected messages/pages caused zero requests in fake-HTTP tests.
- Valid sends preserved page-before-message order and stable retry keys.
- The current bare loop was exercised with the guard, fake writer and fake HTTP.
- An exported synthetic bundle rendered in Neryss's actual viewer.
- Izen's actual writer/page functions were exercised with a fake completion and accepted by our adapters.
- No live contacts were sent in this QA verification.

These are component and compatibility results, not an official incident, scoring result or claim that the full team system is integrated.

## Exactly what each teammate needs to do

### Mavis: connect the sending boundary

1. Review this branch and [the integration guide](PERSON5_INTEGRATION.md).
2. Select `GuardedClient` in the actual loop; keep authorised scenario/target/session context explicit.
3. Route messages, page registrations and call turns through it. Never catch a BLOCK and then use the unguarded client anyway.
4. Preserve message/event IDs and cumulative touch counts in saved evidence.
5. Verify an invalid draft makes zero submission requests before running an authorised integrated practice test.

**Done when:** the real application's selected send path uses the checks, rejection cannot fall through to send, and one integrated practice run has saved evidence.

### Izen: connect writing and correction

1. Supply complete generated content and chosen sender/page metadata through the writer adapter.
2. Make the writer consume QA feedback for limited automatic corrections.
3. Use `as_shared_message()` for a prepared result before passing it through `GuardedClient`.
4. Integrate checks separately into the Node strategy-lab routes. **Python helpers do not automatically protect `frontend/server.mjs`.**

**Done when:** invalid drafts are corrected or stopped automatically and every actual sending route has an explicit check.

### Sherwin: supply supported profile evidence

1. Supply real profiles with fact source URLs and clearly distinguished verified facts/hypotheses.
2. Run the structural profile review and address missing or malformed evidence.
3. Explain the meaning of exposure/hook heuristics without presenting them as measured success probabilities.

**Done when:** Izen receives usable sourced context and the factual limitations are explicit. Our checker cannot certify factual truth for you.

### Neryss: display the evidence accurately

1. Import exported replay bundles and display QA errors/warnings alongside messages.
2. Keep synthetic, practice and scoring provenance explicit.
3. Separate evaluator statuses from official outcomes.
4. Use recorded API evidence for metrics. A planned/unsent contact node must not automatically count as a completed touch.

**Done when:** a reviewer can follow a genuine thread and distinguish what was planned, checked, sent, observed and interpreted.

### Theja: final acceptance and pitch

Help the team verify the integrated boundary, inspect actual email/page appearance, select a genuine thread, update the architecture/pitch and perform two timed spoken rehearsals. Final submission and official results are not completed by this package.

## Start using it locally

Open a checkout of **`theja-person5-main`**, not the older TRACE prototype. From that repository root, with Python 3.11+:

```powershell
python -m pip install requests
python -m quality.acceptance --output output/quality/acceptance
```

Expected acceptance fields: `accepted: true`, `suite_exit_code: 0`, `blocked_fake_sends: 0`, `correction_attempts: 2`. Open `output/quality/acceptance/walkthrough/index.html`. No model/API keys are needed.

Optional full browser acceptance, with Chrome installed:

```powershell
python -m pip install -r requirements-quality.txt
python -m quality.acceptance --browser --output output/quality/acceptance-browser
```

Expected: all current tests pass and `tests_skipped: 0`. Use `py` instead of `python` if that is your Windows launcher. Do not count skipped browser checks as passed.

## Read these next

- [Branch compatibility and teammate interfaces](BRANCH_COMPATIBILITY.md)
- [Integration commands and APIs](PERSON5_INTEGRATION.md)
- [Acceptance checklist and troubleshooting](TEAMMATE_ACCEPTANCE.md)
- [Current architecture](ARCHITECTURE.md)
- [Verification record](VERIFICATION.md)
- [Pitch script](PITCH_3_MIN.md) and [rehearsal worksheet](REHEARSAL.md)

## Branch and data boundaries

`theja-branch` is the older localhost TRACE prototype. `theja-person5-main` is the team-compatible Person 5 package. Do not merge the older dashboard just to obtain the quality tools.

Keys, private run logs, screenshots and videos stay local under ignored paths. Nothing in this handoff authorises real-world contact. All permitted interaction remains inside the official revel8 simulation.

## Target identity and future guardrails

See [docs/QUALITY_ROADMAP.md](QUALITY_ROADMAP.md). Official scenario eligibility and public-name evidence are separate checks. GuardedClient.from_current_practice can now replace a manually typed target list with a fresh read-only official practice lookup; public name mentions never grant permission or prove full identity. Full browser-enabled acceptance now passes 76 tests.
