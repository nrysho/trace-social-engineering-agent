import os
from pathlib import Path
import tempfile
import unittest
from quality.craft import score_item, review_bundle


class CraftTests(unittest.TestCase):
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
