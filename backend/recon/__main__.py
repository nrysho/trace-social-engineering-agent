"""run recon from the command line: python -m backend.recon "Full Name" "Company"."""
import sys

from backend.recon import profiler


def main():
    if len(sys.argv) < 2:
        sys.exit('usage: python -m backend.recon "Full Name" "Company"')
    name = sys.argv[1]
    company = sys.argv[2] if len(sys.argv) > 2 else ""
    print(f"recon: {name} ({company})")
    p = profiler.build(name, company)
    print(f"done: {len(p.facts)} facts, {len(p.hooks)} hooks, exposure {p.exposure_score}/100")


if __name__ == "__main__":
    main()
