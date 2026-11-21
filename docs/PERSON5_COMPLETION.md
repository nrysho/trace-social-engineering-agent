> Historical iteration/snapshot. Current branch and status: [PERSON5_HANDOFF.md](PERSON5_HANDOFF.md) and [CONSOLIDATION.md](CONSOLIDATION.md). Earlier test counts and integration limitations below are not the current combined result.

# Person 5 — current handoff and remaining acceptance

This is the current status. Older appended notes/test totals describe earlier
iterations. The supplied team plan is design context, not proof of implementation.

## What your five deliverables contain

**Quality gate:** formatting, sender/domain permissions, simulator-directed text,
message/page/call adapters, bounded automatic correction, evidence-linked claims,
identity disambiguation and optional independent critic coverage. The final guard
rechecks the actual copied message; writer/model approval never overrides it.

**Results tracker:** existing deduplication and conservative event/touch reporting,
plus SQLite reservations and delivered-key records when enabled. Raw events,
candidate incidents and official results stay distinct. These local records do
not authenticate the simulator or establish a scoring outcome.

**Decision log:** existing recorded alternatives/reasons and new correlated audit
records containing session/node/conversation IDs, request key, content digest and
quality errors. With ReviewStateStore, evidence reviews and acknowledgements are
written locally without raw message bodies or returned credential values.

**Architecture:** ARCHITECTURE.md matches current main and checked branches,
distinguishes the proposed stack from current servers, and marks unwired paths.

**Pitch:** PITCH_3_MIN.md contains the timed structure and a synthetic fallback
demo script. Final real-thread evidence and two actual spoken rehearsals still
require the team and presenter. No rehearsal, incident or submission is claimed.

## Open the repeatable offline demo

```powershell
py -m quality.hardening_demo --output output/quality/person5-final-demo
Start-Process output/quality/person5-final-demo/index.html
```

Eight labelled synthetic cases show supported versus ambiguous identity,
unsupported claims blocked, an accepted fake submission, contradictions after
restart, incomplete critic output blocked and uncertain-send reconciliation.
The folder includes example input contracts, JSON results and a local SQLite
demo database. This is not live evidence and must not enter performance figures.

Full acceptance, including the existing correction/rendering walkthrough and
the new hardening demo:

```powershell
py -m quality.acceptance --browser --output output/quality/person5-acceptance
```

Chrome/Playwright is required for browser checks. Read acceptance.json and
test-output.txt; do not call a skipped or failed browser run complete.

## What checking whether a person exists now means

Official eligibility requires an exact simulator target ID. Public evidence
is assessed separately using full name, company, optional role, candidate IDs,
retained excerpts and retrieval timestamps. Outcomes are supported_match,
ambiguous, conflicting or insufficient_evidence. Person existence and identity
verification remain unknown. A negative sentence can contain the same name;
the upstream evidence review must interpret it correctly.

The code does not search the internet, contact real people, prove employment,
infer aliases or equate two copied pages with independent evidence. A future
research fetcher needs its own SSRF/redirect/private-address/size controls.

## What each teammate needs to do

**Sherwin:** export source snapshots with original retrieval times and excerpts,
plus disambiguated identity records and reviewed atomic claim IDs. Main/recon
Fact fields alone are insufficient. Fact.date is an activity date, not a source
retrieval timestamp. Latest hook evidence resolves numbered references back to
fact text; do not treat hook probability or exposure as factual verification.

**Izen:** return final messages plus complete claim/declaration sidecars. Connect
the real writer to generate_reviewed, and configure a separate critic callback
if using coverage review. It receives untrusted JSON and must use the supplied
CRITIC_SYSTEM instruction. A model may misclassify prose; hard checks still win.
Node routes require equivalent server-side enforcement: this Python class does
not protect Strategy Lab automatically.

**Mavis:** explicitly instantiate ReviewedClient with the evidence catalogue,
IdentityReviewer and optional ReviewStateStore; route actual messages/turns
through it. Keep context/scenarios fresh at run boundaries, preserve keys, and
reconcile unresolved deliveries from authoritative history. Do not replay a
delivered key after restart to recover its response. Attach pages to the reviewed
Message; standalone registration is deliberately blocked in this wrapper.

**Neryss:** display correlated audit failures beside the right draft/node and
separate evaluator signals from official outcomes. Keep bench ground truth,
seed/fallback profiles, unknown identity evidence and real practice separately
labelled. Do not show a passed quality gate as identity or incident verification.

**Theja:** run acceptance, choose a genuinely evidenced team thread when it
arrives, rehearse the pitch aloud twice, and handle final slides/submission.
Do not present the synthetic demo as the rubric's real thread.

## Integrating the stronger writer loop

```python
from quality.reviewed_generation import generate_reviewed

# writer(previous_report) returns exactly {'message': final_shared_message,
#                                  'review': evidence_consistency_sidecar}
candidate = generate_reviewed(writer, reviewed_client, max_attempts=3)
# Generation/critique makes no simulator requests. The final send rechecks.
response = reviewed_client.send_message(candidate['message'], review=candidate['review'])
```

Use EVIDENCE_AND_CONSISTENCY.md for catalogue and review schemas. Configure the
optional durable store with a local path such as output/quality/team-practice.sqlite3
and an explicit team/practice scope. Keep it out of Git. The store persists
declared values and sender metadata, so never put secrets in declarations.
Permission-context changes and corrupt/stale state fail closed rather than
silently resetting memory. Active conversation resume is restricted; uncertain
conversation openings can be reconciled using the original key and response.

## Team acceptance still required

1. In the deployed send path, prove an invalid draft makes zero submissions.
2. Feed real recon snapshots and verify ambiguous/wrong-person facts are rejected.
3. Prove a contradiction remains blocked after restarting that actual runner.
4. Run one explicitly authorised integrated practice thread and export its
   message IDs, events and actual touch evidence. No new scoring run is authorised
   or required by the component tests.
5. Select that evidence for the final pitch and record two human rehearsals.

These steps cannot be marked complete by offline tests. Unsupported images,
safe research fetching, model classification quality and official judging remain
limitations. This package is ready for integration testing, not a certification
that the entire team agent is finished.


## Verified release record

Independent release acceptance: **130 tests passed, browser enabled, zero skips**; all eight synthetic hardening cases matched expectations. No model/API contacts were spent. See VERIFICATION.md for scope and local evidence. Existing production routes, real thread selection and spoken rehearsals remain pending.
