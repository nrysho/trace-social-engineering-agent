from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from backend import eval_run


class EvalLauncherAbortTests(unittest.TestCase):
    def test_eval_launcher_does_not_report_an_abort_as_a_completed_run(self):
        agent=SimpleNamespace(client=Mock(),run=Mock(return_value=('run',[])),
                              run_status='aborted',abort_reason='Missing research')
        with patch.object(eval_run,'Orchestrator',return_value=agent),patch.object(
                eval_run.resume,'latest_active',return_value=None):
            with self.assertRaisesRegex(RuntimeError,'aborted before sending'):
                eval_run.run_eval('mara',scenario='practice')
