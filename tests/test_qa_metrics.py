from copy import deepcopy
import unittest
from viewer.qa_metrics import quality_summary,by_version


class MetricsTests(unittest.TestCase):
    def bundle(self, passed=True, warnings=None):
        qa={'passed':passed,'errors':[] if passed else ['AI wording'],'warnings':warnings or []}
        return {'nodes':[{'id':'n1','level':'contact','qa':qa}],
                'messages':[{'node_id':'n1','qa':deepcopy(qa)}]}

    def test_node_message_duplicate_counts_once(self):
        self.assertEqual(quality_summary(self.bundle())['checked'],1)

    def test_block_and_warning_percentages_are_qa_only(self):
        report=quality_summary(self.bundle(False,['Signature']))
        self.assertEqual(report['blocked_percent'],100)
        self.assertEqual(report['warning_percent'],100)
        self.assertNotIn('incidents',report)

    def test_bypass_is_not_successful_check(self):
        bundle=self.bundle();bundle['nodes'][0]['qa']['bypassed']=True
        bundle['messages'][0]['qa']['bypassed']=True
        report=quality_summary(bundle)
        self.assertEqual(report['checked'],0);self.assertEqual(report['bypassed'],1)
        self.assertIsNone(report['blocked_percent'])

    def test_conflicting_verdicts_are_excluded(self):
        bundle=self.bundle();bundle['messages'][0]['qa']['passed']=False
        result=quality_summary(bundle)
        self.assertEqual(result['conflicting_verdicts'],1);self.assertEqual(result['checked'],0)

    def test_missing_or_malformed_qa_stays_unknown(self):
        result=quality_summary({'messages':[{'node_id':'n1','qa':{'passed':'true'}}]})
        self.assertEqual(result['missing_verdicts'],1);self.assertIsNone(result['warning_percent'])

    def test_local_craft_is_not_official_score(self):
        bundle=self.bundle();bundle['messages'][0]['craft']=[{'local_total_0_8':6},{'local_total_0_8':None}]
        report=quality_summary(bundle)
        self.assertEqual(report['local_craft_mean_0_8'],6);self.assertIsNone(report['official_craft_score'])

    def test_grouping_does_not_invent_agent_versions(self):
        a=self.bundle();b=self.bundle(False);a['agent_version']='v1'
        result=by_version([a,b])
        self.assertEqual(set(result),{'v1','unknown'})
        self.assertEqual(result['unknown']['blocked'],1)

    def test_recorded_bench_label_is_a_version(self):
        bundle=self.bundle();bundle['metrics']={'label':'bench-v2'}
        self.assertEqual(set(by_version([bundle])),{'bench-v2'})

    def test_viewer_summary_adds_qa_without_changing_touch_math(self):
        from viewer.serve import summary
        bundle=self.bundle();bundle['events']={'n1':[]}
        report=summary('synthetic',bundle)
        self.assertEqual(report['contacts'],1);self.assertEqual(report['qa']['checked'],1)

    def test_full_bundle_preserves_qa_over_bare_tree(self):
        import json,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from viewer import serve
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'trees').mkdir()
            bundle=self.bundle();bundle['run_id']='synthetic';bundle['events']={'n1':[]}
            (root/'synthetic.json').write_text(json.dumps(bundle))
            (root/'trees/synthetic.json').write_text(json.dumps([{'id':'n1','level':'contact'}]))
            with patch.object(serve,'RUNS',root):
                selected=serve.bundles()['synthetic']()
            self.assertTrue(selected['nodes'][0]['qa']['passed'])

    def test_clean_message_has_no_universal_advisory_warning(self):
        from test_quality_gate import message,context
        from quality.integration import prepare_message
        candidate=message();candidate['body']+='\nRegistered company: Events Example'
        report=prepare_message(candidate,context())['report']
        self.assertTrue(report['passed']);self.assertEqual(report['warnings'],[])
