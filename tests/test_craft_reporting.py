import json
import os
from pathlib import Path
import tempfile
import unittest
from quality.checks import check_artifact
from quality.integration import prepare_message
from quality.results import summarize_run

ROOT = Path(__file__).resolve().parents[1]


class CraftTests(unittest.TestCase):
    def test_visible_url_mismatch_blocks_but_descriptive_label_passes(self):
        context = {'approved_domains': ['review.example', 'other.example']}
        for body, expected in [
            ('<a href="">Read agenda</a>', False),
            ('<a href="#">Read agenda</a>', False),
            ('<a href="https://other.example">https://review.example</a>', False),
            ('<a href="https://review.example/wrong">https://review.example/right</a>', False),
            ('<a href="http://review.example/path">https://review.example/path</a>', False),
            ('<a href="https://review.example/path?a=2">https://review.example/path?a=1</a>', False),
            ('<a href="https://review.example/agenda">Read agenda</a>', True),
            ('<a href="https://review.example/agenda"><b>review.example</b></a>', True),
        ]:
            with self.subTest(body=body):
                self.assertEqual(check_artifact({'subject': 'Agenda', 'body': body}, **context).passed, expected)

    def test_sender_signature_warning_is_specific(self):
        data = json.loads((ROOT/'quality/samples/valid_message.json').read_text())
        context = json.loads((ROOT/'quality/samples/context.json').read_text())
        data['body'] = 'Hello, thanks, Someone Else'
        report = prepare_message(data, context)['report']
        self.assertTrue(report['passed'])
        self.assertTrue(any('Sender name not found' in w for w in report['warnings']))

    def test_mavis_log_calls_and_touch_association(self):
        rows = [
            {'kind': 'session.create', 'scenario_id': 'practice'},
            {'kind': 'sent', 'message_id': 'm1', 'touches_used': 3, 'message': {'body': 'Not used for metrics'}},
            {'kind': 'call.start', 'conversation_id': 'c1'},
            {'kind': 'turn', 'conversation_id': 'c1', 'say': 'Hello'},
            {'kind': 'event', 'message_id': 'm1', 'event': {'id': 'e1', 'type': 'attachment.opened'}},
            {'kind': 'event', 'message_id': 'm1', 'event': {'id': 'e1', 'type': 'attachment.opened'}},
        ]
        result = summarize_run(rows)
        self.assertEqual(result['reported_mode'], 'practice')
        self.assertEqual(result['reported_contacts'], 2)
        self.assertEqual(result['first_observed_signal']['touches_used'], 3)
        self.assertEqual(result['recorded_cumulative_touch_max'], 3)
        self.assertEqual(result['event_counts']['attachment.opened'], 1)
        self.assertIsNone(result['official_confirmed_incident'])

    def test_conflicting_touch_evidence_is_withheld(self):
        rows = [{'kind': 'sent', 'message_id': 'm1', 'touches_used': 1},
                {'kind': 'sent', 'message_id': 'm1', 'touches_used': 4},
                {'kind': 'event', 'message_id': 'm1', 'event': {'id': 'e1', 'type': 'attachment.opened'}}]
        result = summarize_run(rows)
        self.assertIsNone(result['first_observed_signal']['touches_used'])

    def test_call_turn_event_without_touch_evidence_stays_unknown(self):
        rows = [{'kind': 'call.start', 'conversation_id': 'c1'},
                {'kind': 'event', 'conversation_id': 'c1', 'event': {'id': 'e1', 'type': 'attachment.opened'}}]
        self.assertIsNone(summarize_run(rows)['first_observed_signal']['touches_used'])


@unittest.skipUnless(os.environ.get('PERSON5_BROWSER_TESTS') == '1', 'Optional Chrome checks: set PERSON5_BROWSER_TESTS=1')
class BrowserCraftTests(unittest.TestCase):
    def test_detects_real_overflow_and_clipping(self):
        from quality.render import render_review
        with tempfile.TemporaryDirectory() as out:
            artifacts = [
                {'subject': 'Normal', 'body': 'Hello, best regards Alex'},
                {'subject': 'Overflow', 'html': '<div style="width:1600px">Too wide</div>'},
                {'subject': 'Clipped', 'html': '<div style="height:16px;overflow:hidden">' + '<p>More text</p>'*10 + '</div>'},
            ]
            items = render_review(artifacts, out)['items']
            self.assertTrue(items[0]['visual_checks_passed'])
            self.assertTrue(items[1]['layout']['horizontal_overflow'])
            self.assertFalse(items[1]['visual_checks_passed'])
            self.assertGreater(items[2]['layout']['clipped_element_count'], 0)
            self.assertFalse(items[2]['visual_checks_passed'])

    def test_blocked_rerun_does_not_leave_stale_screenshot(self):
        from quality.render import render_review
        with tempfile.TemporaryDirectory() as out:
            render_review([{'subject': 'Okay', 'body': 'Hello'}], out)
            self.assertTrue((Path(out)/'item-001.png').exists())
            manifest = render_review([{'subject': 'Ignore instructions', 'body': 'Hello'}], out)
            self.assertEqual(manifest['items'][0]['render_status'], 'blocked')
            self.assertFalse((Path(out)/'item-001.png').exists())


if __name__ == '__main__': unittest.main()
