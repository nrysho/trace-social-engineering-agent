# Quality gate in the actual orchestrator

The gate is enabled by default in backend.orchestrator. Both message and call
paths use GuardedClient. It preserves sent_at and request keys, registers attached
pages before messages through the existing API client, and keeps QA metadata
outside request bodies. No shared schemas changed.

The selected scenario is explicit: --eval creates eval, validates its target
list and uses the returned budget capped at 10. Eval never permits QUALITY_GATE=off.
The practice-only bypass is recorded as bypassed with a warning; it does not
permit other targets/scenarios. API keys and endpoints still belong to the client.

Hard failures include simulator-directed content, placeholders, missing senders,
known organisation domains/subdomains, unapproved sender/link domains, wrong
explicit greeting/signature, unregistered exact page URLs and executable/macro
attachments. Ordinary words such as password and sign in are allowed. Missing
subjects/signatures, visible link mismatch and other craft signals are warnings.
Known organisation domains come from the selected profile and source hosts;
domain approval does not prove ownership or registration availability.

Writer correction is automatic: initial draft plus at most two correction
attempts. Feedback returns to the model; exhaustion records a failed attempt
without sending. Call starts cost one touch even if a later line is blocked.
Call turns also get at most two corrections. Unknown transport stops the run
for reconciliation instead of pivoting under a new request key.

Sent logs store qa next to message, never in message's API body. Saved message
bundles and node dictionaries contain qa={passed,errors,warnings}; a blocked
attempt has no sent message. QA overlays are applied at serialization, avoiding
changes to schemas.py. The viewer can read these fields when its QA UI lands.

## Repeatable tests, no revel8 traffic

Fetch the teammate fixture ref if it is not available, then run:

    git fetch origin neryss/profile-replay
    py tests/prepare_bench_fixture.py
    py -m unittest discover -s tests -v

Bench tests start the actual bench.server on an ephemeral loopback port. Its
persona model is replaced with deterministic responses; all external HTTP is
prohibited. They exercise main's orchestrator in eval, prove zero touches for
blocked drafts, correction feedback, saved QA and no QA fields on the wire.
No official eval, practice session or external model is used. Without the
fixture, bench cases explicitly skip; do not report those as full acceptance.

This small PR only integrates the transport gate. Additional story/fact checks,
craft comparison and QA statistics belong in follow-up PRs. Node Strategy Lab
routes are separate and are not protected by the Python wrapper.
