# Person 5 verification record

Baseline main: 1b764bc. No live API/model requests were made by this implementation. Shared schemas, model/config, chat.py and smoke_test.py are unchanged.

## Automated

22 tests pass in the current-main package. This is a separate suite from the older TRACE branch tests.

Run python -m unittest discover -s tests -v from this branch. The suite uses local dataclasses, fixtures, temporary files and fake writer callbacks. It covers the actual main mock Message/TreeNode contract, sender and target authority, domain separation, organisation blocks, subject/body directives, placeholders, malformed content, pages, call turns, correction success/exhaustion, event deduplication and provenance limits.

## Manual offline checks

- Valid synthetic fixture: PASS; invalid synthetic fixture: BLOCK, exit 2.
- Chrome mail screenshot: 700 px; page screenshot: 1200 px. Both visually inspected with scripts/network disabled. Synthetic fixture uses no images or external resources.
- Current main mock/tree.json report: no structured reply events inferred, contacts and official outcomes unknown.
- Earlier local TRACE practice replay: saved run practice-e8a0ff5a16; one previously verified contact and reply, no incident. Explicitly labeled earlier practice, not current-main autonomy or scoring.
- Twelve-second silent backup clip: synthetic PASS, synthetic BLOCK, earlier practice replay. Local only; no narration and not a human rehearsal.

Artifacts remain under ignored output/quality/. On the original development laptop a convenient copy is in the parent TRACE workspace at output/quality/person5-main/. Other teammates must generate their own synthetic previews or arrange an authorised private replay export.

## Not verified or completed

No automatic gate invocation in actual chat/smoke sends, no full autonomous orchestrator, no official score or incident, no image asset resolver, no automatic visual rewrite, no domain registration/availability validation. Two actual timed human pitch rehearsals and Hack League submission are outstanding. The pitch script and decision/architecture docs must be updated when the team's integrated system changes.
