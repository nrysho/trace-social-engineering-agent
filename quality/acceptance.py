"""One-command local teammate acceptance check. Never sends live contacts."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from .demo import build_demo

ROOT = Path(__file__).resolve().parents[1]


def run_acceptance(output, *, browser=False):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env['PERSON5_BROWSER_TESTS'] = '1' if browser else '0'
    result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                            cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    log = result.stdout + result.stderr
    (output/'test-output.txt').write_text(log, encoding='utf-8')
    match = re.search(r'Ran (\d+) tests?', log)
    skipped = re.search(r'OK \(skipped=(\d+)\)', log)
    summary = {'accepted': False, 'browser_checks_requested': browser,
               'tests_discovered': int(match.group(1)) if match else None,
               'tests_skipped': int(skipped.group(1)) if skipped else 0,
               'suite_exit_code': result.returncode, 'demo_ready': False,
               'live_contacts_sent': 0,
               'scope': 'Local QA tests, fake HTTP and synthetic examples; not real integration/scoring approval.'}
    if result.returncode == 0:
        evidence, _, _ = build_demo(output/'walkthrough')
        summary['demo_ready'] = True
        summary['fixture_expectations_matched'] = all(c['matches'] for c in evidence['fixture_results'])
        summary['blocked_fake_sends'] = evidence['send_count_after_block']
        summary['correction_attempts'] = len(evidence['correction_attempts'])
        summary['accepted'] = (summary['fixture_expectations_matched'] and summary['blocked_fake_sends'] == 0
                               and summary['tests_discovered'] is not None and summary['tests_discovered'] > 0)
        if browser and summary['tests_skipped']:
            summary['accepted'] = False
    (output/'acceptance.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--browser', action='store_true', help='Requires optional Playwright and installed Chrome')
    args = parser.parse_args()
    summary = run_acceptance(args.output, browser=args.browser)
    print(json.dumps(summary, indent=2))
    return 0 if summary['accepted'] else 1


if __name__ == '__main__': raise SystemExit(main())
