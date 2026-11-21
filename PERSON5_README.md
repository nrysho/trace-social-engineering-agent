# Person 5: one branch, one package

Use **theja-person5**. It contains both the integrated sending guard and the
advanced evidence/identity/SQLite package from the former theja-person5-main.
Main has not been changed. See [the consolidation record](docs/CONSOLIDATION.md).

## What runs by default on this branch

The Python orchestrator uses GuardedClient for messages, attached pages and call
lines. Eval selects its explicit scenario and cannot disable checks. Blocked
drafts receive bounded correction; no sent contact is invented. Story heuristics,
craft warnings, screenshots, QA statistics and replay metadata are preserved.

## Optional stronger checks

ReviewedClient adds evidence-bound claims, identity disambiguation, critic
coverage, explicit session/persona declarations and optional durable SQLite
state. It requires a review sidecar and real source snapshots; it is not silently
enabled for a writer that does not supply those inputs. These features are now
on this same branch, not a separate experimental branch.

Identity evidence is not proof that a person exists or that every claim is true.
A selected simulator target, public corroboration and official outcome are
separate concepts. Node Strategy Lab and manual scripts are separate send paths.

## Test and use

    py -m quality.acceptance --browser --output runs/quality/consolidated-acceptance

Read [PERSON5_HANDOFF.md](docs/PERSON5_HANDOFF.md) for team actions and demo commands,
[EVIDENCE_AND_CONSISTENCY.md](docs/EVIDENCE_AND_CONSISTENCY.md) for advanced contracts,
and [CONSOLIDATION.md](docs/CONSOLIDATION.md) for compatibility and state migration.
Screenshots, videos, state databases and private evidence stay local/ignored.

The earlier standalone README is preserved in
[LEGACY_PERSON5_README.md](docs/LEGACY_PERSON5_README.md); its branch names, test
counts and integration status are historical. Final real-run selection, team
review/merge, two spoken rehearsals and submission remain external tasks.
