"""eval launcher: one scoring run against one hidden eval target. no human in the loop.

    python -m backend.eval_run <target>              # a real eval session (10 touches)
    python -m backend.eval_run <target> --practice   # same flow on practice, to rehearse
    python -m backend.eval_run <target> --company "Acme"   # company for live recon

one command per scoring run, the same path proven in practice. it resumes an existing
active session for the target, so a crash does not waste one of the three eval runs
(an eval session only counts once a touch is used in it).
"""
import sys

from . import resume
from .orchestrator import Orchestrator


def run_eval(target, scenario="eval", company=None):
    orch = Orchestrator(target, eval_mode=True, scenario=scenario, company=company)
    existing = resume.latest_active(orch.client, scenario)
    if existing:
        orch.resume_sid = existing["session_id"]
        print(f"found an active {scenario} session, resuming it: {orch.resume_sid}")
    run_id, nodes = orch.run()
    if getattr(orch, 'run_status', None) == 'aborted':
        raise RuntimeError('Run aborted before sending: ' + orch.abort_reason)
    incident = any(n.status == "incident" for n in nodes)
    print(f"\neval run {run_id}: {'INCIDENT' if incident else 'no incident'} "
          f"in {orch.budget.used}/{orch.budget.total} touches")
    return run_id, incident


def main():
    args = sys.argv[1:]
    scenario = "practice" if "--practice" in args else "eval"
    company = None
    if "--company" in args:
        i = args.index("--company")
        company = args[i + 1]
        args = args[:i] + args[i + 2:]
    targets = [a for a in args if not a.startswith("-")]
    if not targets:
        sys.exit("usage: python -m backend.eval_run <target> [--practice] [--company NAME]")
    run_eval(targets[0], scenario=scenario, company=company)


if __name__ == "__main__":
    main()
