from contextlib import redirect_stdout
import io
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from backend import experiment, eval_run


class AbortReportingTests(unittest.TestCase):
    def test_experiments_exclude_aborted_empty_and_failed_attempts(self):
        def agent(nodes, status='recorded'):
            return SimpleNamespace(run=Mock(return_value=('run',nodes)),run_status=status)
        aborted=agent([], 'aborted')
        failed=SimpleNamespace(run=Mock(side_effect=RuntimeError('Synthetic gateway failure')))
        sent=agent([SimpleNamespace(level='contact',status='incident')])
        output=io.StringIO()
        with patch.object(experiment,'Orchestrator',side_effect=[aborted,failed,sent]), redirect_stdout(output):
            rows=experiment.run_experiment(['mara'],3)
        self.assertEqual(rows,[('mara',1,1.0,1)])
        self.assertIn('aborted 1; failed 1',output.getvalue())

    def test_no_contacts_means_unmeasured_not_zero_percent(self):
        agent=SimpleNamespace(run=Mock(return_value=('run',[])),run_status='aborted')
        output=io.StringIO()
        with patch.object(experiment,'Orchestrator',return_value=agent),redirect_stdout(output):
            rows=experiment.run_experiment(['mara'],1)
        self.assertIsNone(rows[0][2]);self.assertEqual(rows[0][1],0)
        self.assertIn('unmeasured',output.getvalue())

    def test_eval_launcher_does_not_report_an_abort_as_a_completed_run(self):
        agent=SimpleNamespace(client=Mock(),run=Mock(return_value=('run',[])),
                              run_status='aborted',abort_reason='Missing research')
        with patch.object(eval_run,'Orchestrator',return_value=agent),patch.object(
                eval_run.resume,'latest_active',return_value=None):
            with self.assertRaisesRegex(RuntimeError,'aborted before sending'):
                eval_run.run_eval('mara',scenario='practice')
