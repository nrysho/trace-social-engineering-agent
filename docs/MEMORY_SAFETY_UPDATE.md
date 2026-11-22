# Closed-loop memory safety update

Built on main 7ab053c. Existing teammate lesson storage, classification and
branch selection are retained. No official contacts were spent on these fixes.

## Corrections

- Classify every occurrence across sentences, so an earlier quoted/conditional
  stop phrase cannot hide a later direct stop. Typographic apostrophes normalise
  for phrase matching. This remains a limited bilingual heuristic.
- Aggregate all returned reply events before classification, not just the first.
- Check the call opening and every received turn before generating the next turn.
  An explicit global stop or approach decline prevents further turns/follow-up.
- Preserve prior lesson context for call writing and call-to-email continuation.
- Save branch closure/lesson before returning to branch selection. Saving failure
  raises and stops progression. Bundle/tree snapshots use atomic file replacement;
  that does not make API+journal+memory a single transaction or solve full resume.
- Attach branch/contact and available message/conversation/request IDs to lessons.
  A failed branch cannot borrow a receipt from another branch. Per-turn/event-level
  provenance and validating every excerpt against immutable raw journals remain
  future work; current references are contact-level.
- Treat scepticism-only/closure-only lessons as tentative. An explicit observation
  with nonempty quoted support is required before memory calls it explicit.
- The configured Python guard checks global-stop memory immediately before message,
  page and call submissions, even with practice content QA disabled. Passive reads
  and cleanup remain usable. Other manual/Node entrypoints do not acquire the
  orchestrator's memory policy automatically; no claim of universal coverage.

## Verification

265 tests pass with Chrome enabled and no skips. New fake-response cases cover
opening/mid-call stops, multiple message replies, quoted-then-real stop, call
memory, final guard enforcement, closure-save failure, unrelated receipt isolation
and atomic snapshot failure. Existing sender/channel, budget, QA, retry and
rendering checks remain passing. Tests are local; they do not establish real
scoring performance or complete semantic rejection classification.

## Deliberately unchanged

Teammate research/domain policy and strategy ranking are unchanged. Full automatic
used-session restore remains blocked. A general memory viewer and richer pending
question/preference lifecycle remain separate work. This change does not enable
scoring runs, create real contacts, or certify domain ownership/factual truth.
