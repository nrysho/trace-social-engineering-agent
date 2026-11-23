from pathlib import Path
import tempfile
import unittest
from quality.demo import build_demo


class DemoTests(unittest.TestCase):
    def test_complete_offline_walkthrough(self):
        with tempfile.TemporaryDirectory() as out:
            evidence, _, _ = build_demo(out)
            self.assertTrue(evidence['synthetic'])
            self.assertEqual(evidence['network_requests'], 0)
            self.assertEqual(evidence['send_count_after_block'], 0)
            self.assertEqual(evidence['fake_send_count_after_correction'], 1)
            attempts = evidence['correction_attempts']
            self.assertEqual(len(attempts), 2)
            self.assertFalse(attempts[0]['report']['passed'])
            self.assertTrue(attempts[1]['report']['passed'])
            self.assertEqual(evidence['summary']['duplicate_events_ignored'], 1)
            self.assertIn('attempt 2 passed', (Path(out)/'corrected.html').read_text())
            self.assertIn('Duplicate event records ignored: 1', (Path(out)/'report.html').read_text())
            self.assertTrue(evidence['summary']['synthetic'])
            self.assertEqual(len(evidence['fixture_results']), 10)
            self.assertTrue(all(case['matches'] for case in evidence['fixture_results']))
            for name in ('index', 'pass', 'block', 'corrected', 'report'):
                self.assertTrue((Path(out)/(name+'.html')).exists())


if __name__ == '__main__': unittest.main()
