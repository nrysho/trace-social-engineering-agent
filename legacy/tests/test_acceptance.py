from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from quality.acceptance import run_acceptance


class AcceptanceTests(unittest.TestCase):
    def run_fake(self, response, browser=False):
        with tempfile.TemporaryDirectory() as out:
            with patch('quality.acceptance.subprocess.run', return_value=response) as runner:
                summary = run_acceptance(out, browser=browser)
                self.assertTrue((Path(out)/'acceptance.json').exists())
                self.assertEqual(runner.call_args.kwargs['env']['PERSON5_BROWSER_TESTS'], '1' if browser else '0')
            return summary

    def test_success_records_tests_and_builds_demo(self):
        response = SimpleNamespace(returncode=0, stdout='', stderr='Ran 12 tests\nOK (skipped=2)')
        summary = self.run_fake(response)
        self.assertTrue(summary['accepted'])
        self.assertEqual(summary['tests_discovered'], 12)
        self.assertEqual(summary['tests_skipped'], 2)
        self.assertEqual(summary['blocked_fake_sends'], 0)

    def test_suite_failure_cannot_claim_acceptance(self):
        response = SimpleNamespace(returncode=1, stdout='', stderr='Ran 12 tests\nFAILED')
        summary = self.run_fake(response)
        self.assertFalse(summary['accepted'])
        self.assertFalse(summary['demo_ready'])

    def test_browser_request_cannot_pass_when_checks_skip(self):
        response = SimpleNamespace(returncode=0, stdout='', stderr='Ran 12 tests\nOK (skipped=2)')
        self.assertFalse(self.run_fake(response, browser=True)['accepted'])


if __name__ == '__main__': unittest.main()
