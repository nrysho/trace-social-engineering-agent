import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock
from quality.guarded_client import GuardedClient
from quality.integration import QualityBlocked
from test_quality_gate import context


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.raw = Mock()
        self.raw.get_session.return_value = dict(session_id='s1', scenario_id='practice',
            status='active', touches_used=0, touch_budget=30)
        self.raw.get_events.return_value = {'events': []}
        self.guard = GuardedClient(self.raw, context())

    def test_unused_session_restored_read_only(self):
        self.assertEqual(self.guard.restore_session('s1')['touches_used'], 0)
        self.assertIn('s1', self.guard.sessions)
        self.raw.create_session.assert_not_called()

    def test_used_uncertain_or_wrong_scope_cannot_reset_story(self):
        base = self.raw.get_session.return_value.copy()
        for changes in [dict(touches_used=1), dict(touches_used=None), dict(touches_used=False),
                        dict(scenario_id='eval'), dict(status='ended'), dict(session_id='other')]:
            with self.subTest(changes=changes):
                self.raw.get_session.return_value = dict(base, **changes)
                with self.assertRaises(QualityBlocked): self.guard.restore_session('s1')
                self.assertNotIn('s1', self.guard.sessions)
        self.raw.create_session.assert_not_called()

    def test_missing_or_nonempty_events_cannot_resume(self):
        for events in [None, {}, {'events': [{'type': 'reply'}]}]:
            self.raw.get_events.return_value = events
            with self.assertRaises(QualityBlocked): self.guard.restore_session('s1')
        self.raw.create_session.assert_not_called()

    def test_launcher_can_list_sessions_before_guard_scope(self):
        self.raw.list_sessions.return_value = {'sessions': []}
        self.assertEqual(self.guard.list_sessions(), {'sessions': []})

    def test_zero_api_touches_do_not_clear_pending_local_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            self.raw.log_dir = Path(directory)
            (Path(directory) / 's1.jsonl').write_text('{"kind":"quality","qa":{"passed":true}}\n')
            with self.assertRaises(QualityBlocked): self.guard.restore_session('s1')
            self.raw.get_session.assert_not_called()
            self.raw.create_session.assert_not_called()
