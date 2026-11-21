"""Regression coverage for the teammate writer update combined with Person 5."""
from copy import deepcopy
import unittest
from unittest.mock import Mock, patch
from backend import orchestrator as runner
from quality.guarded_client import GuardedClient
from test_quality_gate import context


class LatestWriterMergeTests(unittest.TestCase):
    def test_brand_sender_instructions_do_not_require_an_invented_person(self):
        import json
        import writer
        cfg=writer.ModelConfig(api_key='synthetic',fallback_model='synthetic-fallback')
        def complete(config,model,messages):
            payload=json.loads(messages[-1]['content'])
            self.assertEqual(payload['you_are']['name'],'Example Billing')
            rules=' '.join(payload['writing_rules'])
            self.assertIn('using exactly you_are.name',rules)
            self.assertIn('Never invent the recipient',rules)
            return json.dumps({'subject':'Question','body':'Hi Mara,\nWho handles billing enquiries?\nBest,\nExample Billing'})
        with patch.object(writer,'_completion',side_effect=complete):
            result=writer.generate_message(cfg,target={'name':'Mara Felsen'},approach={'channel':'email'},
                sender={'name':'Example Billing','email':'billing@events.example'},verified_facts=[])
        self.assertIn('Example Billing',result['content']['body'])

    def setUp(self):
        with patch.object(runner, 'Revel8Client', return_value=Mock()):
            self.agent = runner.Orchestrator('mara', use_model=True)
        self.agent.profile = dict(name='Mara Felsen', domain='company.example', facts=[])
        self.approach = dict(pretext='speaker_invite', channel='email', hook='Agenda')
        self.comp = dict(sender=dict(name='Jonas Weber', address='jonas@events.example'),
            attachment='Agenda.pdf', landing_page=None)
        self.agent.client = GuardedClient(Mock(), context())

    def test_model_receives_upstream_features_and_quality_feedback(self):
        self.comp['sender'].update(role='Events lead', organization='Example Events')
        feedback = dict(passed=False, errors=['Correct signature'])
        with patch.object(self.agent, '_cfg', return_value=object()), patch.object(
                runner.writer, 'generate_message', return_value={'content': {'body': 'Corrected'}}) as generate:
            self.agent._model_body(self.approach, self.comp, [], feedback=feedback, link_follows=True)
        args = generate.call_args.kwargs
        self.assertEqual(args['attachment'], 'Agenda.pdf')
        self.assertTrue(args['link_follows'])
        self.assertEqual(args['sender']['organization'], 'Example Events')
        self.assertIn('Correct signature', args['conversation_history'][-1]['text'])

    def test_generated_domain_requires_explicit_permission(self):
        key = ('speaker_invite', 'email', 'Agenda')
        self.agent._personas[key] = dict(name='Alice Example', role='Organizer', organization='Reviewed Events',
            domain='unreviewed.example', address='alice@unreviewed.example')
        original = deepcopy(self.comp)
        self.agent._apply_persona(self.approach, self.comp)
        self.assertEqual(self.comp, original)
        self.agent.client.context['approved_sender_domains'].append('unreviewed.example')
        self.agent._apply_persona(self.approach, self.comp)
        self.assertEqual(self.comp['sender']['address'], 'alice@unreviewed.example')

    def test_real_org_domain_cannot_be_authorised_by_extra_policy(self):
        self.agent.client.context['approved_sender_domains'].append('company.example')
        self.agent._personas[('speaker_invite', 'email', 'Agenda')] = dict(name='Alice Example', role='Organizer',
            organization='Example', domain='company.example', address='alice@company.example')
        original = deepcopy(self.comp)
        self.agent._apply_persona(self.approach, self.comp)
        self.assertEqual(self.comp, original)

    def test_company_from_role_preserved_without_cross_scenario_fallback(self):
        self.agent.client = Mock()
        self.agent.client.scenarios.return_value = [
            {'id':'practice','targets':[{'id':'mara','name':'Mara Felsen','role':'CFO, Example GmbH'}]},
            {'id':'eval','targets':[{'id':'mara','name':'Different Mara','company':'Wrong company'}]}]
        self.assertEqual(self.agent._target_card()['company'], 'Example GmbH')
        self.agent.target_id = 'missing'
        with self.assertRaises(ValueError): self.agent._target_card()
