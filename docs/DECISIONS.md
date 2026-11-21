# Person 5 decision log

Recorded on 21 November 2026 during this implementation, not a reconstructed first-hour log.

- We chose a clean branch based on main 1b764bc over merging the old TRACE backend because main now owns different shared dataclasses/config. This prevents competing schema and backend conventions.
- We chose pure dictionary/dataclass adapters over editing schemas.py because Mavis owns that contract. sender is mapped to API from, while pages and session/idempotency metadata remain separate.
- We chose bounded writer callbacks over direct model calls because Izen and the shared backend.llm own generation. Three attempts by default, then fail closed, with no per-message human approval.
- We chose source-aware reporting over parsing phrases like reply: interested because main's outcomes are text notes, not API event records. Missing metrics remain unknown.
- We chose unique message/conversation IDs over line counts because one call can have ten turns but costs one touch. Local log counts are not assumed to be session totals.
- We chose separate exact-host sender/link approvals with organisation blocks over guessing domain availability. Configuration requires team review.
- We chose local offline evidence over publishing thread contents. Synthetic fixtures, real practice and scoring are never merged into one claimed success metric.

## API compatibility and acceptance iteration

- We chose an opt-in GuardedClient around Mavis's implementation over editing her methods, so teammates can adopt one verified boundary without conflicting ownership. It validates a copied shared Message before either page registration or sending.
- We chose real-client/fake-HTTP tests over a fresh practice send because they prove request ordering, retry-key preservation and zero calls on rejection reproducibly without spending touches.
- We joined event message IDs to logged cumulative touches instead of inferring time from contact order. Missing call timing and conflicting evidence remain unknown.
- We separated mechanical overflow/clipping flags from official craft scores: a passing layout check is not aesthetic approval. We added a repeatable synthetic demo rather than relabeling it as live evidence.

## Teammate acceptance and false-positive iteration

- We chose a one-command acceptance runner with saved machine-readable results over requiring teammates to interpret scattered commands. Requested browser checks cannot silently skip and still pass acceptance.
- We narrowed the as-an-AI rule to model-directed contexts and accepted case-insensitive HTTPS because legitimate AI-related work descriptions and valid URL schemes should not be blocked unnecessarily. Regression tests retain actual prohibited directives.
- We chose structured rejection for malformed shared payloads and readable repair guidance over exposing a traceback or requiring users to inspect raw JSON first. Raw reports remain available for integration.

## Current branch adaptation

Inspected main 16ae78b, neryss/viewer a7da34e and recon-osint b718bcc. Added a practice-session lifecycle adapter, explicit replay export and structural profile review without modifying team modules. Full 68-test browser-enabled acceptance passed. Verified a synthetic exported bundle in an isolated copy of Neryss's actual viewer over localhost with no page errors. Main's loop was exercised with fake HTTP/writers, including blocked sends and a local evaluator incident label unsupported as a credential outcome. Export refuses conflicting joins, preserves raw statuses and exposes unmatched evidence rather than guessing. See BRANCH_COMPATIBILITY.md for the integration gaps.
