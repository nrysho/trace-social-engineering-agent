"""experiment runner: run the agent many times and report the numbers that matter.

    python -m backend.experiment                  # all practice targets, 5 runs each
    python -m backend.experiment julius -n 10     # one target, 10 runs
    python -m backend.experiment --mock           # fast runs on the cached/mock profile

reports, per target: incident rate and the median number of contacts to the first
incident. this is the feedback loop: change recon, strategy or the writer, run this,
see the numbers move, and pick the version to freeze.

topic-hit is not reported: whether a contact hit the target's planted topic is private
to the target and the api never returns it. the jury measures it server-side at scoring.
"""
import statistics
import sys

from .orchestrator import Orchestrator

PRACTICE_TARGETS = ["julius", "robert", "tom"]


def first_incident(nodes):
    """(reached, contacts_to_first_incident). a contact is one touch (a message or a whole call)."""
    contacts = 0
    for n in nodes:
        if n.level in ("contact", "caller"):
            contacts += 1
        if n.status == "incident":
            return True, contacts
    return False, None


def run_experiment(targets, n, use_mock=False):
    summary = []
    for target in targets:
        print(f"\n=== {target}: {n} runs ===")
        reached, touches = 0, []
        for i in range(n):
            try:
                _, nodes = Orchestrator(target, use_mock=use_mock).run()
            except Exception as e:
                print(f"  run {i + 1} failed: {e}")
                continue
            ok, t = first_incident(nodes)
            if ok:
                reached += 1
                touches.append(t)
            print(f"  run {i + 1}: {'INCIDENT in ' + str(t) + ' contacts' if ok else 'no incident'}")
        rate = reached / n if n else 0.0
        median_t = statistics.median(touches) if touches else None
        summary.append((target, n, rate, median_t))

    print("\n" + "=" * 52)
    print(f"{'target':10} {'runs':>5} {'incident_rate':>14} {'median_contacts':>16}")
    for target, runs, rate, median_t in summary:
        mt = f"{median_t:.1f}" if median_t is not None else "-"
        print(f"{target:10} {runs:>5} {rate:>13.0%} {mt:>16}")
    print("(topic-hit is private to the target and not measurable here)")
    return summary


def main():
    args = sys.argv[1:]
    use_mock = "--mock" in args
    n = 5
    if "-n" in args:
        i = args.index("-n")
        n = int(args[i + 1])
        args = args[:i] + args[i + 2:]
    targets = [a for a in args if not a.startswith("-")] or PRACTICE_TARGETS
    run_experiment(targets, n, use_mock=use_mock)


if __name__ == "__main__":
    main()
