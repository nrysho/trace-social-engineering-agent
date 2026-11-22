# Running the agent

How to run recon and the agent against practice twins, the eval targets, or the local bench.
Run every command from the repository root, with the project's Python environment active.

## 0. Setup (once)

```bash
cp .env.example .env      # then fill in REVEL8_API_KEY and RADEON_API_KEY (see README)
```

Keys are read from `.env` only. Never commit it.

## 1. Is the eval open, and who are the targets?

```bash
python -c "from backend.revel8 import Revel8Client; [print(s['id'], 'open=', s.get('open'), [(t['id'], t.get('name')) for t in s.get('targets', [])]) for s in Revel8Client().scenarios()]"
```

Example output before the eval opens:

```
eval      open= False  []
practice  open= True   [('julius', 'Julius Muth'), ('robert', 'Robert Seilbeck'), ('tom', 'Tom Müller')]
```

Use the target ids (`julius`, `tom`, ...) in the commands below.

## 2. Research a target first (recommended)

```bash
python -m backend.recon "Full Name" "Company" "Role"
```

This writes `runs/profiles/<full-name>.json` and `.md`. Read the `.md` before you spend touches:
a wrong fact or a missing current need is far cheaper to fix here. A stated need ("looking for a
venue", "hiring a controller") is the strongest lead the agent can get.

## 3. Run the agent

```bash
# rehearsal: practice scenario, a clean session per approach (each with the eval's 10 touches)
PYTHONUNBUFFERED=1 python -m backend.orchestrator <target_id>

# the real thing: eval scenario, 10 touches in one session
PYTHONUNBUFFERED=1 python -m backend.orchestrator <target_id> --eval
```

Each `--eval` run uses one eval session. The eval allows 3 sessions per target.

> **Do not use `--mock` on new targets.** When no cached profile exists, `--mock` loads the demo
> profile in `mock/profile.json`, which is about someone else. Without it, the agent uses the profile
> from step 2, or runs recon itself.

Other flags:

| Flag / variable | Effect |
|---|---|
| `--compose` | Template messages without the model (testing only) |
| `--mock` | Use a cached profile, else the demo profile (tests only) |
| `REVEL8_API_URL=http://127.0.0.1:8770/v1` | Run against the local bench instead of revel8 |
| `QUALITY_GATE=off` | Skip the quality gate (practice only; refused in eval) |

## 4. Watch a run live

```bash
python viewer/serve.py 8766       # open http://127.0.0.1:8766, pick the run, tick "live"
```

Or keep the raw log: append `2>&1 | tee run_<target>.log` to the step 3 command.

## 5. Local bench (fictional personas with ground truth)

```bash
python -m bench.server                                   # terminal 1: personas mara, daniel, sofia, lukas
python -m backend.recon --bench lukas                    # profile a persona from its bench pages
REVEL8_API_URL=http://127.0.0.1:8770/v1 PYTHONUNBUFFERED=1 python -m backend.orchestrator lukas --eval
```

Ground truth per session (hook hit, suspicion, incidents) lands in `runs/bench/<session_id>.json`
in the folder the bench server runs from.

## Eval day checklist

1. Check the eval targets (step 1).
2. Run recon on each target and read the profiles (step 2).
3. If practice is still open, rehearse on a practice twin (step 3, no `--eval`).
4. Run `--eval` on **one** target and check the result before starting the others: eval sessions
   are limited.

## Tests

```bash
python -m pytest -q
```
