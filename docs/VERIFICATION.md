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

## Current branch adaptation

Inspected main 16ae78b, neryss/viewer a7da34e and recon-osint b718bcc. Added a practice-session lifecycle adapter, explicit replay export and structural profile review without modifying team modules. Full 68-test browser-enabled acceptance passed. Verified a synthetic exported bundle in an isolated copy of Neryss's actual viewer over localhost with no page errors. Main's loop was exercised with fake HTTP/writers, including blocked sends and a local evaluator incident label unsupported as a credential outcome. Export refuses conflicting joins, preserves raw statuses and exposes unmatched evidence rather than guessing. See BRANCH_COMPATIBILITY.md for the integration gaps.

Final refresh also inspected Izen's 91f10d5 strategy/writer branch. Added sender-email mapping, explicit-page-URL checks, call-line checks and provenance preservation adapters. Full 68-test acceptance passed with zero skips; generated model requests and the Node lab's send routes are not exercised or modified by these adapters.

Actual Izen writer.generate_message and make_landing_page were also exercised from branch 91f10d5 with a fake completion and network prohibition; the adapter accepted the resulting shared message/page. HTML page previews now preserve existing form controls without synthesizing duplicate fields. No writer/model network request occurred.

## Identity feasibility iteration

Performed one read-only official scenario lookup and public homepage/about/imprint reads. The API listed Julius Muth, Robert Seilbeck and Tom M?ller; the imprint mentioned Julius Muth. The homepage also mentioned a different Julius, illustrating same-first-name risk. No session, message or touch was created. New identity helpers separate simulator eligibility from public text mentions. Full acceptance passes 76 tests, no skips. Source snapshots stay private and ignored. See QUALITY_ROADMAP.md for implemented scope versus proposed enhancements.
