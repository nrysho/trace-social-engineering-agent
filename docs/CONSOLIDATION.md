# One Person 5 branch

Use **theja-person5**. It contains the histories and features of both the newer
integration branch and the earlier theja-person5-main package. Main was not
modified. The older Person 5 branch can now be retired; the original theja-branch
is a separate legacy TRACE project and is not part of this consolidation.

## Active versus optional

The actual Python orchestrator uses GuardedClient by default on this branch.
It retains explicit practice/eval scope, mandatory eval checks, bounded draft
correction, exact page registration checks, sender/domain checks and QA sidecars.
Its simple story heuristics remain process-local.

ReviewedClient is the optional stronger boundary. It adds approved claim IDs,
source excerpts/timestamps, identity disambiguation, optional critic coverage,
explicit persona/session declarations and optional SQLite reservations. It is
not automatically selected by the writer/orchestrator: its review sidecars and
source snapshots must be supplied first. Identity review supports explicitly
selected practice or eval metadata and must match the client's scenario.

Both clients retain hard permission checks and preserve QA outside API payloads.
The stronger client never permits a bypass. Its explicit declaration ledger
replaces ambiguous date heuristics, so a persona-specific reference cannot be
mistaken for a shared meeting date. Ordinary credential vocabulary is allowed;
link-label/craft problems warn while unsafe destinations and content still block.

## Transport and state compatibility

ReviewedClient accepts the current client's sent_at argument. When present,
the review must contain `transport={'sent_at': exact_value}`. Content hashing
still binds the final shared Message; request hashing additionally binds the
transport metadata. Changing a timestamp under an acknowledged key cannot return
an old response or send a second contact.

SQLite state now binds scenario as well as domain/target permissions. An older
database with a different policy fingerprint fails closed. Keep the old database
for reference and reconcile any pending request before choosing a new state scope;
do not delete it to bypass an unresolved delivery. Source text, API keys and raw
reply/credential values are not persisted by this review-state store.

The replay exporter preserves message IDs, available retry keys and QA metadata.
It adds QA overlays without changing recorded evaluator statuses or raw events.
Results reports remain offline compatibility tools; Neryss's viewer is still
the team's results/Progress system.

## Documentation

PERSON5_README.md and PERSON5_HANDOFF.md are current. Older plans, test totals
and branch snapshots are historical context. The current architecture and pitch
remain the integration versions; advanced modules are optional, not fictional
claims of automatic adoption or complete factual verification.

## Verification

Run `py -m quality.acceptance --browser --output runs/quality/consolidated-acceptance`.
The combined suite includes the prior component tests, actual local-bench HTTP,
Chrome rendering, evidence/identity checks, metadata binding and restart recovery.
No official simulator contact or external model request is required.

Verified consolidation: **174 tests passed with browser checks enabled, zero skips**. Both offline walkthroughs matched their expectations. Evidence is saved in runs/quality/consolidated-acceptance/. No official simulator session or external model call was used.
