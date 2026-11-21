# Person 5 integration against current main

## Setup and local checks

Python 3.11+; the checker and reports use only the standard library. Client-integration tests also need the team client's existing requests dependency (python -m pip install requests). From this branch's repository root:

```powershell
python -m unittest discover -s tests -v
python -m quality.cli validate quality/samples/valid_message.json --context quality/samples/context.json --output output/quality/pass
python -m quality.cli validate quality/samples/invalid_message.json --context quality/samples/context.json --output output/quality/block
python -m quality.cli report mock/tree.json --output output/quality/tree
```

Invalid input deliberately exits 2. Operational errors exit 1. Output folders contain JSON and escaped offline HTML. Use py instead of python on Windows if appropriate. The sample context is synthetic: review.example is a reserved documentation domain, never a competition sender or an availability claim.

Screenshots require optional Playwright and installed Chrome:

```powershell
python -m pip install -r requirements-quality.txt
python -m quality.cli render quality/samples/valid_message.json --context quality/samples/context.json --output output/quality/render
```

Emails render at 700 px and pages at 1200 px, offline with scripts and service workers disabled. Images are blocked until an explicit local asset resolver exists. This is an offline evidence tool, not an integrated automatic visual critic. Open screenshots and inspect the four rubric criteria: sender fit, occasion/format fit, cleanliness, and consistent details. No automatic craft points are awarded.

## Mavis: final message preparation

```python
from quality.integration import checked_message, generate_checked, checked_turn, prepare_page

# Accepts a shared schemas.Message dataclass or its to_dict() representation.
prepared = checked_message(message, context)
# Register prepared['page'] in prepared['session_id'] first if present.
# Send only prepared['payload']; keep session_id and idempotency_key outside body.
# Reuse prepared['idempotency_key'] on retries of this contact.
```

Message.sender becomes API `from`. LandingPage is separate registration data. session_id, node_id and idempotency_key are metadata, never message-body fields. Unknown shared fields fail closed so future schema changes need a deliberate adapter update. No edits to schemas.py were required.

`checked_message` raises QualityBlocked with a structured report on failure. Never catch and then continue to send. `prepare_message` returns a report without raising for content violations and is suitable for local previews. For automatic correction:

```python
prepared = generate_checked(writer_callback, context, max_attempts=3, audit=save_qa_attempt)
```

writer_callback(previous_report_or_None) returns a shared Message. It gets the previous errors and warnings, up to the configured 1-5 attempts. Exhaustion raises; no human approval or send occurs in this helper. Audit receives attempt number and report only, not message content or keys. It does not choose or call a model itself; Izen uses backend.llm inside her writer as appropriate.

`prepare_page(page, context)` returns (API page dictionary, report). Check report.passed before registration. `checked_turn({'say': text, 'attachments': [...]}, context)` blocks invalid future conversation turns. Caller owns the authorized session/conversation ID, target and idempotency header; a call costs one touch even across turns.

Context requires simulation_only=True and authorized_targets from scenario metadata. Lists approved_sender_domains and approved_link_hosts are exact, independent allowlists. known_organisation_domains overrides approvals and includes subdomain blocks. Non-email channel handles/phone IDs must be explicitly listed in approved_sender_addresses. None of this proves registration availability or expands permitted real-world contact.

## Neryss: reports and decisions

`quality.results.summarize_run(record)` accepts a current main tree array, chat.py JSONL entries, or an older TRACE run object. `decision_records(record)` reads main's decision/reasoning/rejected fields and preserves statuses; text outcomes remain notes. These are read-only adapters, not a new results database or frontend.

Raw tree text cannot establish touch counts or API events. Chat logs count unique message IDs and conversation IDs as recorded local contacts; turns cost no additional contact and incomplete local logs are explicitly not session totals. Events deduplicate by ID; conflicts retain the first with a warning. ID-less events remain uncertain. Never label a local JSON export as authenticated.

Mavis: for reliable first-signal timing, log cumulative touches_used alongside each returned event batch. The existing chat.py log omits it. Official confirmed incidents, topic hits and craft scores stay null until a separate authoritative integration exists. A reply/link open is not a win; page submission alone is not evidence of credential submission without explicit field names.

## Files and boundaries

Output, screenshots, video and private thread exports belong under ignored output/quality/ or runs/. No keys enter examples or reports. Never put full provider errors, keys or credential values in screenshots. These helpers never call revel8, a model, email, or a real person. Existing manual practice scripts and teammates' shared modules are unchanged.

## Opt-in wrapper for Mavis's actual client (tested offline)

```python
from backend.revel8 import Revel8Client
from quality.guarded_client import GuardedClient

client = Revel8Client()
guarded = GuardedClient(client, context, session_ids=[session_id], audit=save_report)
response = guarded.send_message(shared_message)
```

Explicit session IDs must come from the caller's authorised session setup. This wrapper validates the entire message and its page before Mavis can register the page or send. It passes a copied shared Message to the existing client, preserving its page-before-message behavior and retry keys. It does not alter Mavis's implementation or automatically wrap other code. Do not also register a message's page separately: client.send_message already handles it.

For separate pages: guarded.register_page(session_id, page). For calls: guarded.start_conversation(session_id, target, channel, sender, idem_key=key), then guarded.say(conversation_id, line, sid=session_id, idem_key=turn_key). Resumed calls must be explicitly supplied as conversation_sessions={conversation_id: session_id} when constructing the wrapper. Unknown sessions/conversations fail before a request. Keys must be stable per contact/turn across retries.

Tests run Mavis's real methods against fake HTTP responses and prohibit real requests. They verify zero requests on blocked content/pages, page-before-message ordering, copied payloads, key reuse on timeout and guarded calls. Context and payloads are copied; report callbacks receive no message text or credential material. Scope failures and malformed runtime inputs fail closed but not every operational failure is a retryable writer error.

Reporting now recognises backend/revel8.py call.start entries, scenario labels and touches_used on sent records. Event message IDs join to those cumulative touch counts. Conflicting timing is withheld. Calls with no recorded touch count remain unknown; local event counts still do not authenticate results.

## One-command offline acceptance demo

```powershell
python -m quality.demo --output output/quality/walkthrough
```

Open index.html: PASS, BLOCK (zero fake sends), automatic correction on attempt two, then synthetic evidence report with duplicate removal. Ten versioned fixture cases cover emails/pages/turns. No keys or network needed. The demo uses an in-memory fake sender; the separate client tests exercise Mavis's real transport methods with fake HTTP.

Optional screenshots and silent video:

```powershell
python -m pip install requests -r requirements-quality.txt
python -m playwright install ffmpeg
python -m quality.demo --output output/quality/walkthrough --screenshots --video
```

Chrome must be installed. Rendering aborts all network requests and disables page JavaScript/service workers. Images remain unsupported. The video is a synthetic QA walkthrough, not a real scoring result or a speaker rehearsal.

## Browser acceptance tests

```powershell
$env:PERSON5_BROWSER_TESTS = '1'
python -m unittest discover -s tests -v
```

Without that variable, two optional Chrome tests skip. With Chrome/Playwright installed and enabled, the full 38-test suite includes real overflow/clipping detection and stale-screenshot cleanup. Visual flags identify horizontal overflow, clipped containers and excessive page height; they do not establish visual perfection or factual correctness. A render command exits nonzero on these defects.

## Teammate acceptance update

Use `python -m quality.acceptance --output output/quality/acceptance` for a single local acceptance run; add --browser for Chrome checks. See TEAMMATE_ACCEPTANCE.md. The current full suite has 68 passing tests; the default run skips two browser tests. New edge cases cover multilingual text, long valid mail, header newlines, malformed types, uppercase links and credential-free human-readable correction reports. Reports now show Not recorded for missing metrics.

## Current-main / branch adaptation

Read BRANCH_COMPATIBILITY.md. GuardedClient supports the new loop's practice-session lifecycle. quality.viewer_export joins selected tree/API logs into Neryss's bundle format. quality.cli profile checks source structure without performing research. Full acceptance now has 68 passing tests with --browser; default skips two.

Izen's new writer result adapter is documented in BRANCH_COMPATIBILITY.md. Use as_shared_message on a prepared result before GuardedClient.send_message. The Node strategy-lab routes remain a separate integration boundary, not automatically protected by Python helpers.
