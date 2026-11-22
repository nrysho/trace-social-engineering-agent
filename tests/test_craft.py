import os
from pathlib import Path
import tempfile
import unittest
from quality.craft import score_item, review_bundle, craft_readiness


class CraftTests(unittest.TestCase):
    def test_readiness_uses_median_and_exposes_missing_artifacts(self):
        rows=[dict(message_index=i,kind='email',local_total_0_8=value) for i,value in enumerate([8,2,None])]
        result=craft_readiness(rows)
        self.assertEqual(result['local_median_0_8'],5)
        self.assertFalse(result['coverage_complete'])
        self.assertEqual(result['rendered_artifacts'],2)
        self.assertEqual(result['issues'][0]['message_index'],2)
        self.assertIsNone(result['official_craft_score'])

    def test_no_artifacts_cannot_claim_craft_readiness(self):
        result=craft_readiness([])
        self.assertFalse(result['coverage_complete']);self.assertIsNone(result['local_median_0_8'])

    def test_clean_render_with_signature_warning_remains_visible(self):
        result=craft_readiness([dict(message_index=0,kind='email',local_total_0_8=6,
            quality_warnings=['Inspect signature'],signals={'clipped_element_count':1})])
        self.assertTrue(result['coverage_complete'])
        self.assertIn('Inspect signature',result['issues'][0]['reasons'])
        self.assertIn('clipped_element_count',result['issues'][0]['reasons'])
    def test_missing_render_is_unknown_not_zero(self):
        self.assertIsNone(score_item({}, {'render_status':'blocked'})['local_total_0_8'])

    def test_heuristic_scores_never_become_official(self):
        result=score_item({'from':{'name':'Jonas','address':'jonas@events.example'}},
                          {'render_status':'saved','quality':{'warnings':[],'errors':[]},'layout':{}})
        self.assertEqual(result['local_total_0_8'],8)
        self.assertIsNone(result['official_craft_score'])

    @unittest.skipUnless(os.environ.get('PERSON5_BROWSER_TESTS')=='1','Optional Chrome craft evidence')
    def test_saved_email_and_page_widths_with_scripts_and_network_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            result=review_bundle({'run_id':'synthetic','messages':[{'node_id':'n1','channel':'email',
                'sender':{'name':'Jonas','address':'jonas@events.example'},'subject':'Agenda',
                'body':'Hello Mara, please reply. Best, Jonas',
                'landing_page':{'url':'https://portal.example/agenda','title':'Agenda','text':'Please confirm','fields':[]}}]},
                temp,approved_domains=['events.example','portal.example'])
            self.assertEqual([row['kind'] for row in result['items']],['email','page'])
            import struct
            self.assertEqual([struct.unpack('>I',(Path(temp)/row['screenshot']).read_bytes()[16:20])[0] for row in result['items']],[700,1200])
            self.assertTrue((Path(temp)/'bundle-with-craft.json').exists())
