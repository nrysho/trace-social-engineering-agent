# Person 5 integration against current main

## Setup and local checks

Python 3.11+; the checker and reports use only the standard library. From this branch's repository root:

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
