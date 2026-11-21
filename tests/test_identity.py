from copy import deepcopy
import unittest
from quality.identity import check_target, context_from_practice, public_name_mentions
from quality.guarded_client import GuardedClient
from quality.integration import QualityBlocked


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.scenarios = [{'id':'practice','open':True,'company':'revel8','targets':[
            {'id':'julius','name':'Julius Muth','role':'Founder'}, {'id':'tom','name':'Tom Müller'}]}]
        self.context = {'simulation_only':True,'authorized_targets':['hand-entered-wrong-id'],
                        'approved_sender_domains':['review.example'],'approved_link_hosts':[]}

    def test_exact_target_and_profile_fields_match(self):
        self.assertTrue(check_target(self.scenarios,'julius',expected_name='Julius Muth',expected_company='revel8')['passed'])

    def test_typo_and_same_first_name_block(self):
        self.assertFalse(check_target(self.scenarios,'julias')['passed'])
        self.assertFalse(check_target(self.scenarios,'julius',expected_name='Julius Another')['passed'])

    def test_aliases_and_company_conflicts_are_not_assumed(self):
        self.assertFalse(check_target(self.scenarios,'tom',expected_name='Tom-Christopher Müller')['passed'])
        self.assertFalse(check_target(self.scenarios,'julius',expected_company='Another company')['passed'])

    def test_closed_missing_and_duplicate_scenarios_fail(self):
        for scenarios in [[], [{'id':'practice','open':False}], self.scenarios*2]:
            with self.assertRaises(QualityBlocked): check_target(scenarios,'julius')
        duplicate=deepcopy(self.scenarios)
        duplicate[0]['targets'].append(duplicate[0]['targets'][0])
        with self.assertRaises(QualityBlocked): check_target(duplicate,'julius')

    def test_context_uses_api_targets_without_approving_any_domains(self):
        result=context_from_practice(self.scenarios,self.context)
        self.assertEqual(result['authorized_targets'],['julius','tom'])
        self.assertEqual(result['approved_sender_domains'],['review.example'])
        self.assertEqual(self.context['authorized_targets'],['hand-entered-wrong-id'])

    def test_factory_only_reads_and_snapshot_is_explicit(self):
        scenarios=self.scenarios
        class ReadOnly:
            calls=0
            def scenarios(self): self.calls+=1;return deepcopy(scenarios)
        client=ReadOnly()
        guard=GuardedClient.from_current_practice(client,self.context)
        self.assertEqual(client.calls,1)
        self.assertEqual(guard.context['authorized_targets'],['julius','tom'])
        self.assertIn('recorded_at',guard.context['target_snapshot'])

    def test_full_name_mentions_do_not_confirm_identity(self):
        sources=[{'url':'https://review.example/imprint','text':'Managing director Julius Muth'},
                 {'url':'https://review.example/imprint#top','text':'Managing director Julius Muth'}]
        result=public_name_mentions('Julius Muth',sources)
        self.assertTrue(result['mention_found'])
        self.assertEqual(len(result['matching_sources']),1)
        self.assertIsNone(result['public_identity_verified'])

    def test_unrelated_first_name_or_no_match_is_not_nonexistence(self):
        result=public_name_mentions('Julius Muth',[{'url':'https://review.example','text':'Julius Another, engineer'}])
        self.assertFalse(result['mention_found'])
        self.assertIsNone(result['public_identity_verified'])


if __name__ == '__main__': unittest.main()
