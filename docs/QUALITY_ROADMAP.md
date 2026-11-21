> Historical iteration/snapshot. Current branch and status: [PERSON5_HANDOFF.md](PERSON5_HANDOFF.md) and [CONSOLIDATION.md](CONSOLIDATION.md). Earlier test counts and integration limitations below are not the current combined result.

# Better quality gates, identity evidence and result guardrails

## What the challenge supports

The supplied Challenge says to research public information and contact only the authorised AI twins through the simulation. The scoring rubric permits deductions for wrong facts and requires the jury to confirm incidents within the rules. These are requirements for our product, not instructions to contact real people. Public research and simulator sending are separate operations.

## What we checked in this iteration

A read-only authenticated GET of the official scenarios endpoint listed Julius Muth, Robert Seilbeck and Tom M?ller as practice targets. No sessions or touches were created. A public GET of https://www.revel8.ai/imprint found Julius Muth named among the managing directors. The homepage also mentioned another Julius in a customer testimonial, demonstrating why a first name is insufficient.

The imprint uses the fuller name Tom-Christopher M?ller; our code must not silently assume a public-name alias matches Tom M?ller. Lack of a Robert mention on the inspected pages does not imply nonexistence. No broad internet identity verification has been completed. The API listing establishes simulator eligibility; a website name mention does not establish employment, source independence or current role by itself.

Private fetched snapshots stay in ignored output/quality/verification-research/. No public-page raw content, personal contact details or team keys were committed.

## Implemented now: two clearly separated checks

quality.identity.check_target checks an exact ID against one explicitly open practice scenario, and can compare expected profile name/company. Typos, duplicate IDs, a closed scenario and identity conflicts block. Aliases must be resolved with evidence, not guessed. The pure function checks supplied data; it does not authenticate arbitrary JSON.

GuardedClient.from_current_practice(client, context) performs one read-only scenario lookup through the supplied official client and replaces hand-entered authorised target IDs. It retains separately reviewed sender/link-domain configuration and stores an explicit snapshot. It does not approve every public person or enable eval, and does not refresh metadata before every send.

```python
from quality.guarded_client import GuardedClient
from quality.identity import check_target

# Use Mavis's official Revel8Client; no message is sent by this factory.
guarded = GuardedClient.from_current_practice(client, context)
# Check a selected profile against a fresh official scenario response when assembling the run:
result = check_target(scenarios, target_id, expected_name=profile.name, expected_company=profile.company)
# Block on result['passed'] == False rather than forcing a name match.
```

quality.identity.public_name_mentions(full_name, sources) examines page text already collected by Sherwin. It requires a full name, returns source URLs containing a name mention and deduplicates the same page. public_identity_verified remains null. Negative mentions or copied biographies can still contain a name: this is a source-discovery signal, not semantic verification. No match means not found in those sources, never person does not exist.

## Next: prioritised implementation plan

### P0: make the current boundary real

First connect the guard to Mavis's actual loop and equivalent validation to Izen's Node routes. A better rule library has no effect on a route that bypasses it. Prove blocked content makes no submission, then save one authorised integrated practice thread. Keep eval disabled until separately requested and reviewed.

### P1: evidence-bound claims instead of generic confidence

Keep a sidecar record of each factual claim about the target, its source URL, retrieval time and exact supporting text. Have the writer reference these records and flag claims with missing or conflicting support. Treat web text as untrusted data, never runtime instructions.

Distinguish public target facts, hypotheses, observed replies and declared scenario/cover-story content. The challenge allows simulated sender stories; that does not make them researched facts. Do not label all narrative as verified or reject a lawful simulation merely because a sender story is fictional. Only target claims with supporting evidence may be presented as researched truth.

Two URLs or two hosts do not prove source independence. Canonicalise page URLs, compare publisher ownership/registrable domains with a maintained public-suffix list, detect copied content, and retain contradictions. A model can suggest a claim/evidence match but cannot certify truth or override deterministic rule failures.

### P1: consistent session state across channels

Record declared names, organisations, event dates, references, page URLs and promises in a session ledger. Compare follow-ups against that ledger before send. Track deliberate changes of sender/channel as separate personas; do not globally freeze one sender and accidentally prohibit legitimate simulated pivots. A contradiction must be explained by recorded evidence or rejected for rewrite.

### P1: trustworthy event and touch ledger

Persist request/contact IDs, idempotency key, node ID, session ID, payload hash, response/event IDs, model provenance and cumulative touches at each successful response. Never log API credentials or submitted credential values. Write pending/sent/responded states atomically so a timeout is not mislabeled as silence or success.

Reconcile uncertain requests against official session/events before spending another touch. Deduplicate messages, calls and events; count one call once despite its turns. Keep first-signal timing unknown when evidence is missing. Preserve raw data separately from interpretations and jury-confirmed results. A reply, ordinary public fact or email-only form is not automatically a qualifying incident. Hidden topic hits remain unknown unless returned authoritatively.

A hash chain can help detect accidental alteration but does not authenticate a file whose author can rewrite the entire chain. Do not call local hashes official proof.

### P1: explicit transport and budget constraints

Use the official API client only, with authorised scenario/session/target/channel context. Cache read-only metadata with a recorded retrieval time and refresh at clear run boundaries; distinguish source retrieval time from when cached JSON was loaded. Define a fail-closed behavior for stale/unavailable authority checks.

Use the actual returned session budget and cumulative touches, reserve in-flight contacts and reuse a key on retries. An uncertain timeout must not cause an automatic new contact under a new key. Practice and future eval remain distinct; never auto-spend competition runs. This requires Mavis's orchestrator integration, not just a post-run report.

### P2: domain and asset correctness

Canonicalise IDNA/Punycode and trailing dots, display the actual registrable domain, and keep exact independent sender/link approvals. Block known organisation domains and subdomains regardless of allowlisting. DNS resolution does not prove ownership, registration availability or challenge eligibility. Do not register or contact suggested domains as part of checking.

Resolve only approved uploaded asset IDs into isolated local files for screenshots. Keep scripts/network disabled. Compare registered fields with the visible form and check missing images, clipping, link labels and signature details. These are mechanical craft signals, not official craft points.

### P2: richer automatic critic with a hard boundary

An optional second model can review tone, unsupported assertions and inconsistencies using only supplied evidence. Its output must be structured, bounded and auditable. It cannot overrule blocked targets/domains, invent source evidence or grant permission. Keep adversarial and valid-content regression fixtures, including multilingual text, HTML, Unicode domains and refusals. Monitor false positives as well as missed violations.

## What not to build

No universal person-exists score, guaranteed vulnerability score or fabricated official results. Do not require a twin to publish private information before it can be an authorised simulation target. Do not collect phone/email details merely to prove existence, contact real people, inspect private accounts, or let web content invoke tools. More safeguards should improve evidence and correctness without changing the task into real-world outreach.

## Current verification

The identity additions have eight regression tests. Full browser-enabled acceptance passes 76 tests with zero skips. The official/public checks were read-only and no touches were spent. The improvements listed as next/P1/P2 above are proposals, not completed features. Human rehearsals, actual team-route adoption and verified integrated results remain pending.


## Evidence and consistency implementation update

The opt-in ReviewedClient, EvidenceCatalog and SessionLedger are now implemented. Read [the integration contract and limits](EVIDENCE_AND_CONSISTENCY.md). They check declared evidence and contradictions; they do not extract every factual claim or authenticate truth. Shared schemas and teammate routes are unchanged. Node enforcement, source snapshot collection, durable ledger resume and actual team adoption remain pending. Earlier test totals above describe the previous identity iteration.


## Current hardening handoff

See [PERSON5_COMPLETION.md](PERSON5_COMPLETION.md) for current implementation, commands and remaining acceptance. IdentityReviewer, independent critic-output coverage, optional durable SQLite state, correlated audits and bounded reviewed generation are implemented. They are opt-in and do not establish production-route adoption. Safe public fetching, automatic factual truth verification and final real-run presentation evidence remain outside the completed component work.
