# Person 5 acceptance verification

Based on main 58d6dac, including Mavis's backend/revel8.py. Her schemas, model client, API implementation and practice scripts are unchanged.

## Executed checks

- Full 38-test suite passed with PERSON5_BROWSER_TESTS=1. Default run has 36 passing tests and two optional Chrome skips. No test spends a live touch.
- Mavis's actual Revel8Client methods were exercised with a fake HTTP session and a network prohibition. Blocked message/page: zero requests. Accepted message: page then message, correct sender mapping and metadata separation. Timeout: same idempotency key on retry. Unknown sessions/conversations and invalid call turns block.
- Ten versioned message/page/turn fixture expectations passed.
- Real offline Chrome detects deliberately wide and clipped content; a clean fixture passes. Rerunning blocked input removes its stale screenshot.
- Main API logs count call.start once, associate message event IDs with recorded cumulative touches, deduplicate events and withhold conflicting/missing timing. No official outcome is inferred.
- Repeatable synthetic demo: valid PASS, invalid BLOCK with zero fake sends, automatic correction on attempt two, one fake contact/reply and one ignored duplicate. Screenshots and a silent backup video generated locally.

## Artifact locations

Run python -m quality.demo --output output/quality/walkthrough. Optional --screenshots --video adds browser evidence. Outputs remain ignored. The original development laptop also has a convenient parent-workspace copy under output/quality/person5-main/walkthrough/.

## Remaining limits

The wrapper is opt-in and not automatically installed in team send paths. No new live API/model requests, real incidents or scoring results were generated. Images/local asset resolution, automatic aesthetic/factual critique and production orchestration remain outside this verified package. Exact-domain approval is configuration, not registration proof. First-signal timing follows recorded event order, not reconstructed hidden timing.

Two actual timed speaker rehearsals and final submission remain human tasks; docs/REHEARSAL.md provides the worksheet. Generated silent video is not a rehearsal.

## Teammate acceptance iteration

Executed python -m quality.acceptance --browser: accepted=true, 53 tests, zero skips, suite exit 0, all fixture expectations matched, zero sends after BLOCK and two correction attempts. No live contacts. The default non-browser run has 51 passing tests and two skips.

Added regression coverage for valid multilingual content, long valid emails, legitimate AI-related role descriptions, uppercase HTTPS, malformed field types, oversized content, subject newlines, unfinished angle placeholders, unclosed empty anchors and attachment limits. Correction pages now show the original rejected draft, suggested fixes and accepted revision; result pages display readable unknowns and alternatives.

Human rehearsals remain unperformed. Acceptance does not install the wrapper in team scripts or establish real outcomes.
