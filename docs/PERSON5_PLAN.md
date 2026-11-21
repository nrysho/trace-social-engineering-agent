# Person 5 execution plan and status

Baseline: main at 1b764bc, inspected 21 November 2026. Branch: theja-person5-main. The old theja-branch TRACE prototype remains separate; this package targets the team's current shared dataclasses.

1. Inspect main's schemas, model/config and actual send/log paths: complete.
2. Build an independent quality package accepting shared Message/LandingPage and call turns: complete. No schemas or teammate modules changed.
3. Add bounded automatic correction and separate API payload/page/session metadata: complete and tested with local callbacks. No model requests are made by this package.
4. Support main tree JSON and chat JSONL reporting without inferred official outcomes: complete. Metrics not present in source stay unknown.
5. Validate offline email/page screenshots and prepare local evidence: complete: email/page screenshots visually verified, PASS/BLOCK inspectors generated, and a silent local backup clip recorded. See docs/VERIFICATION.md.
6. Prepare implemented architecture, real decision log, pitch script and rehearsal instructions: included.
7. Give Mavis and Neryss stable import/JSON contracts: docs/PERSON5_INTEGRATION.md.

## Still dependent on integration or humans

The package does not alter chat.py or smoke_test.py. Its checks are NOT automatically active in those paths. Mavis must invoke the adapters before message sends, page registration and call turns, preserving the returned session/idempotency values. The shared autonomous orchestrator is not yet on this main snapshot.

Uploaded images remain blocked pending local asset resolution. Domain approval is team-reviewed exact-host configuration, not proof of domain availability. Tone, authenticity and factual accuracy are not established by regex checks. No official craft score is generated.

Two actual timed speaker rehearsals, organiser-confirmed logistics, final scoring-thread selection and submission remain human tasks. A recorded local demo is not a rehearsal or a scoring run. No new practice contacts are needed for this work.
