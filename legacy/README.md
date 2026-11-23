# Legacy

Code from the hackathon that worked when it was written but is no longer part of the running agent.
It is kept for reference and credit; nothing in the main pipeline imports it, and the test suite does not
collect this folder (see `conftest.py` at the repo root). Imports inside these files still refer to their
original locations (`backend.run`, `quality.craft`, ...), so they will not run from here without moving
them back.

| File | Author | What it did | What replaced it |
|---|---|---|---|
| `backend/run.py` | Chye Yu En | The first end-to-end loop: research → contact → read the reaction → decide, with placeholder agents | `backend/orchestrator.py`, the full tree search |
| `backend/eval_run.py` | Chye Yu En, Theja | One command per scoring run | `python -m backend.orchestrator <target> --eval` |
| `backend/resume.py` | Chye Yu En | Crash resume: find a session after a crash and reload it from the API log | Not replaced; the orchestrator ends a run on a crash |
| `quality/craft.py` | Theja | Offline comparison of writer output with heuristic craft scores | – |
| `quality/demo.py` | Theja | Synthetic offline walkthrough of the quality checks (screenshots, video) | – |
| `quality/acceptance.py` | Theja | One-command local acceptance check for teammates | – |
| `quality/reviewed_generation.py` | Theja | Bounded correction of a message with review candidates | `quality.integration.generate_checked` |
| `quality/writer_adapter.py` | Theja | Mapped the first writer's output to the quality contracts | The orchestrator calls the writer directly |
| `quality/viewer_export.py` | Theja | Joined a run tree and an API log into a viewer bundle | The orchestrator writes viewer bundles itself |
| `frontend/` | Izen | "Strategy Lab": a Node UI for the early strategy experiments | `viewer/` (replay viewer) |
| `tests/test_closed_loop.py`, `tests/test_memory_safety.py` | perfold, Theja | Tests of the lesson-memory orchestrator that was superseded at the final merge | – (`backend/lessons.py` is still used by `strategy.py`) |
| other `tests/` | Theja, Izen | Tests of the files above | – |
