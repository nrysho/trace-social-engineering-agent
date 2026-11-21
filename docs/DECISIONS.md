# Person 5 decision log

Recorded on 21 November 2026 during this implementation, not a reconstructed first-hour log.

- We chose a clean branch based on main 1b764bc over merging the old TRACE backend because main now owns different shared dataclasses/config. This prevents competing schema and backend conventions.
- We chose pure dictionary/dataclass adapters over editing schemas.py because Mavis owns that contract. sender is mapped to API from, while pages and session/idempotency metadata remain separate.
- We chose bounded writer callbacks over direct model calls because Izen and the shared backend.llm own generation. Three attempts by default, then fail closed, with no per-message human approval.
- We chose source-aware reporting over parsing phrases like reply: interested because main's outcomes are text notes, not API event records. Missing metrics remain unknown.
- We chose unique message/conversation IDs over line counts because one call can have ten turns but costs one touch. Local log counts are not assumed to be session totals.
- We chose separate exact-host sender/link approvals with organisation blocks over guessing domain availability. Configuration requires team review.
- We chose local offline evidence over publishing thread contents. Synthetic fixtures, real practice and scoring are never merged into one claimed success metric.
