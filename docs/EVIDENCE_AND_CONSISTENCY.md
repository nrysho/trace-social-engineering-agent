> Consolidated on **theja-person5**. See [CONSOLIDATION.md](CONSOLIDATION.md) for current transport and state compatibility; historical verification counts below describe earlier iterations.

# Evidence and consistency gate — Person 5

## What is implemented

`quality.reviewed_client.ReviewedClient` is an **opt-in** subclass of the existing
`GuardedClient`. Existing send routes do not acquire these checks automatically.
It retains the hard simulation/target/sender/domain/content checks and adds:

- A separate, recon-owned `EvidenceCatalog`, copied when constructed. Writer
  output references catalogue IDs; it cannot submit its own source records.
- Explicit source URL, timezone-aware retrieval time, retained source text and
  supporting excerpt checks. Default source freshness policy: 30 days. Future
  timestamps, missing excerpts, unknown IDs and unresolved conflicting values block.
- Exact approved claim wording must occur in the message, call turn or attached
  page. A paraphrase needs another reviewed catalogue entry.
- A review sidecar bound to a SHA-256 digest of the complete shared message.
  Changing the sender, content, page, channel or request key invalidates the review.
- Session-wide declarations (event date, document reference, promise) and
  persona-specific declarations. The same persona cannot silently change sender
  identity. Different personas are permitted; session promises remain shared.
- Successful acknowledgement commits declarations. Same-key/same-content retries
  return the saved response; changed content under an old key blocks.
- Uncertain transport leaves a pending reservation and blocks further sends in
  that session. Reconciliation requires the original key and an authoritative
  response supplied by the caller. This is not automatic history discovery.

Example: an email declares `meeting_date=Friday` in session scope. A later SMS or
call declaring `meeting_date=Thursday` is blocked before submission. Another
persona can use a different persona-scoped reference, but cannot change that
shared meeting date.

## Important limits

This is **deterministic checking of declared claims**, not automatic extraction
of every claim from prose. Empty `claim_ids` means the caller declares no target
facts; it does not prove that the prose contains none. Missing declarations and
misclassified cover stories remain an upstream writer/critic risk.

`review_status=supported` is an assertion made by the trusted recon/review owner.
The checker verifies metadata, quote membership and consistency, not whether a
quote logically entails a claim or is true. A negative sentence can contain a
name. Two URLs do not establish independent sources. A content hash binds the
review to text; it does not authenticate evidence or prove accuracy.

Hypotheses and observed-reply assertions are currently blocked as factual ledger
entries. Reply-evidence provenance and explicitly tentative hypothesis support
remain future work. A simulation sender story uses `scenario_story` and is not
presented as a researched target fact. Legitimate corrections currently require
an integration change/reviewed reconciliation; do not silently overwrite dates.

State is process-local by default. Supplying `state_store=ReviewStateStore(path,
scope='team:practice')` enables SQLite reservations, declaration recovery and
same-key protection across restarts. Reservations reach disk before transport.
Persistence errors stop the controller; stale writes from a second controller
are rejected. Restored acknowledged keys block resend and require recovering
the original response from API history. Active conversations are not generally
resumable; an uncertain opening can be reconciled using its original key/ID.
The store excludes raw messages, replies, evidence snapshots and API keys, but
retains declared values and sender metadata. Do not declare credential values.
Keep the database local under ignored output, restrict access and retain it for
as long as the session can be resumed. No database hash authenticates the API.

Optional `identity_reviewer=IdentityReviewer(...)` requires a supported full-name
and company match, distinguishing ambiguous, conflicting and insufficient
public evidence. `person_exists` and `public_identity_verified` stay unknown.
Optional `critic=callback` checks independent claim coverage. It must return
ordered character spans covering `message_content(message)` completely, the
complete message digest, classifications, claim IDs and declarations. Callback
failure blocks; model labels never override deterministic checks. Use
`quality.claim_coverage.CRITIC_SYSTEM` as system instructions and pass
`critic_input` as untrusted JSON data. This package does not call a model for you.

## Recon contract and current branches

Checked remote refs on 21 November 2026 after an authenticated fetch:

- `main`: `9565b48` — tree-search orchestrator and existing shared Fact shape.
- `recon-osint`: `333b973` — role matching, tech/domain checks and activity date.
  `Fact.date` is an activity date, **not retrieval time**. `SearchResult` still
  lacks retrieval time and extraction does not retain supporting excerpts.
- `izen/autonomous-strategy-lab`: `aa84835` — separate Node send path and new
  decision metadata. The Python wrapper does not protect that path.
- `neryss/profile-replay`: `2f1f853` — bench/chat replay with profile fallback and
  local event-to-win mapping. Bench ground truth, fallback founder profiles,
  observed events and official adjudication must remain separately labelled.
- Older client, loop, tree-search and viewer branches were compared to `main`;
  their relevant interfaces are already represented in the checked main version.

`profile_claim_candidates(profile, target_id)` accepts dictionaries/dataclasses
from main and the new recon branch without changing `schemas.py`. It preserves
optional activity dates but produces `needs_review` candidates, with empty
supports. Existing `verified=True`, confidence and `Profile.generated_at` never
manufacture supporting excerpts or source retrieval times.

### Sherwin

Retain the actual fetched text, canonical source URL and original retrieval
timestamp when collecting research. Add an evidence sidecar to the Profile
handoff; do not put arbitrary writer-produced evidence into the catalogue.
Review each atomic claim and retain contradictory entries until resolved.
Disambiguate same-name people against the official target before selecting facts.

### Izen

Return the approved claim IDs actually used, and a complete set of declared
session/persona facts. Map these to a review sidecar after preparing the final
shared Message. Feed `QualityBlocked.report` into the existing bounded correction
loop. Do not recalculate a hash and call that factual review.

Node Strategy Lab needs equivalent enforcement at its **server** send boundary.
Do not rely on a browser-only flag, and do not say this Python work protects Node.

### Mavis

Use `ReviewedClient` explicitly where the final Python loop sends; pass the review
sidecar on each send/turn. Supply reviewed domain context, authorised practice
session IDs and the recon catalogue. Calls need metadata from
`start_conversation` on this same wrapper; resumed conversations are rejected.
Standalone `register_page` is blocked: attach the page to the reviewed Message
so the existing client registers it only after the combined checks pass.

Enable ReviewStateStore before resuming sessions. Supply original authoritative
responses when reconciling; the diagnostic snapshot alone is not a restore file. Do not store API keys or credential values in it.

### Neryss

Show `evidence.consistency` audit reports next to the corresponding draft/node,
including blocked alternatives. ReviewedClient audit records now include session,
node/conversation IDs, request key and content digest, and are persisted when
ReviewStateStore is enabled. The older GuardedClient audit shape remains narrower. Keep
personal source text local and show source URLs and timestamps selectively.
Never turn a passed check into an “identity verified” or “incident confirmed” badge.

## Minimal integration shape

```python
from quality.claim_evidence import EvidenceCatalog
from quality.integration import plain
from quality.reviewed_client import ReviewedClient
from quality.session_consistency import content_digest

# Inputs come from reviewed recon snapshots, not from generated message text.
catalog = EvidenceCatalog(sources, claims, max_age_days=30)
guard = ReviewedClient.from_current_practice(
    mavis_client, context, evidence_catalog=catalog,
    session_ids=[practice_session_id], audit=save_quality_report,
)

message = plain(shared_message)  # Final dataclass after writer adaptation.
review = {
    'schema_version': 1,
    'claims_declared': True,
    'persona_id': 'speaker-coordinator',
    'content_sha256': content_digest(message),
    'claim_ids': ['approved-role-claim'],
    'assertions': [
        {'scope': 'session', 'key': 'meeting_date', 'value': 'Friday',
         'kind': 'scenario_story'},
    ],
}
guard.send_message(message, review=review)
```

Source record: `source_id`, `url`, `retrieved_at` (ISO 8601 with timezone), `text`.
Claim record: `claim_id`, `target_id`, `text` (approved rendering), `fact_key`,
`fact_value`, `review_status='supported'`, `supports=[{'source_id':..., 'quote':...}]`.
A `target_fact` assertion also needs `claim_id` matching `claim_ids`, key and value.
Choose keys with explicit entity/time context, such as `event:panel-1:date` or
`role:current`; distinct roles/events should not collide under a generic key.

For a call, hash the complete turn snapshot with `session_id`, `conversation_id`,
`to`, `channel`, `sender`, `say`, and `idempotency_key`; pass it as the sidecar to
`guard.say(cid, line, sid=..., idem_key=..., review=...)`. The transport payload
remains the original client contract. Call turns do not become new contact counts.

## Offline verification

```powershell
py -m unittest discover -s tests -p test_evidence_consistency.py -v
py -m quality.acceptance --browser --output output/quality/evidence-acceptance
```

Tests cover both successful and blocked messages, stale/missing evidence,
same-name/wrong-target evidence, conflicts, changed content, calls, persona
changes, retries, timeouts and preservation of existing permission checks.
They use synthetic fixtures and fake clients; no public research, model request,
practice contact, new scoring result or real route adoption is established.


Verified: 23 new evidence/consistency tests pass. A clean archive of current Person 5 HEAD (`703cfbb`, including main `9565b48`) plus only the six files for this feature passes all 99 Python/browser acceptance tests with zero skips. This independent check excludes the separate uncommitted incident changes. No simulator/model requests were made. Verification output remains under ignored `output/quality/evidence-isolated-bf55b70c/output/quality/evidence-acceptance/`.


Current completion status, demo commands and remaining teammate actions are maintained in [PERSON5_COMPLETION.md](PERSON5_COMPLETION.md). Earlier 99-test verification above records the previous iteration, not the current total.

When passing sent_at to ReviewedClient, bind it exactly with review.transport = {"sent_at": value}. IdentityReviewer accepts scenario_id="practice" or "eval" explicitly; it must match the client scope. Basic automatic story heuristics are replaced by the stronger explicit declaration ledger when using ReviewedClient.
