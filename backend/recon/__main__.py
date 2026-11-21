"""run recon from the command line: python -m backend.recon "Full Name" "Company"."""
import sys

from backend.recon import profiler, bench_osint


def main():
    if len(sys.argv) < 2:
        sys.exit('usage: python -m backend.recon "Full Name" "Company"\n'
                 '       python -m backend.recon --bench <target>   (fictional bench persona)')

    # --bench <target>: profile a fictional bench persona from its fake public pages
    if sys.argv[1] == "--bench":
        if len(sys.argv) < 3:
            sys.exit("usage: python -m backend.recon --bench <target>")
        target = sys.argv[2]
        info = bench_osint.target_info(target)  # agent-visible name + role, not ground truth
        name, role = info.get("name", target), info.get("role", "")
        print(f"recon (bench): {name} ({role})")
        p = profiler.build(name, "", role, bench_target=target)
        print(f"done: {len(p.facts)} facts, {len(p.hooks)} hooks, exposure {p.exposure_score}/100")
        return

    name = sys.argv[1]
    company = sys.argv[2] if len(sys.argv) > 2 else ""
    role = sys.argv[3] if len(sys.argv) > 3 else ""
    label = f"{role}, {company}" if role else company
    print(f"recon: {name} ({label})")
    p = profiler.build(name, company, role)
    print(f"done: {len(p.facts)} facts, {len(p.hooks)} hooks, exposure {p.exposure_score}/100")


if __name__ == "__main__":
    main()
