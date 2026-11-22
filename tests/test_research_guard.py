from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from backend import orchestrator as runner
from quality.research_gate import research_readiness
from quality.story import profile_claim_checks
from quality.guarded_client import GuardedClient
from quality.integration import QualityBlocked, generate_checked, as_shared_message
from test_quality_gate import context, message


class ResearchGuardTests(unittest.TestCase):
    def test_company_entity_label_does_not_block_all_mentions(self):
        facts=[dict(category='company',value='Example Corp',verified=False)]
        self.assertTrue(profile_claim_checks('A question about Example Corp.',facts).passed)
        facts.append(dict(category='role',value='You work at Example Corp',verified=False))
        self.assertFalse(profile_claim_checks('You work at Example Corp.',facts).passed)

    def test_exact_verified_sentence_overrides_duplicate_unverified_substring_only_within_its_span(self):
        facts=[dict(category='role',value='Co-Founder and CEO of Example',verified=False),
               dict(category='role',value='Mara is Co-Founder and CEO of Example.',verified=True,
                    source_url='https://company.example/team')]
        self.assertTrue(profile_claim_checks('Mara is Co-Founder and CEO of Example.',facts).passed)
        self.assertFalse(profile_claim_checks('Someone else is Co-Founder and CEO of Example.',facts).passed)

    def test_profile_requires_matching_identity_and_sourced_verified_facts(self):
        fact = dict(value='Finance lead', verified=True, source_url='https://company.example/team')
        good = dict(name='Mara Felsen', target_id='mara', facts=[fact])
        self.assertTrue(research_readiness(good, 'mara', 'Mara Felsen').passed)
        # the wrong person stops the run
        for changes in [dict(name='Someone Else'), dict(target_id='other')]:
            with self.subTest(changes=changes):
                self.assertFalse(research_readiness(dict(good, **changes), 'mara', 'Mara Felsen').passed)
        # thin or unconfirmed recon only warns: sending nothing in a scoring run is a certain loss
        for changes in [dict(facts=[]), dict(facts=[dict(fact, verified=False)]),
                        dict(facts=[dict(fact, source_url='javascript:bad')]),
                        dict(facts=[dict(fact, source_url=123)]),
                        dict(facts=[dict(fact, source_url='https://user:secret@company.example')])]:
            with self.subTest(changes=changes):
                report = research_readiness(dict(good, **changes), 'mara', 'Mara Felsen')
                self.assertTrue(report.passed)
                self.assertTrue(any('confirmed' in w for w in report.warnings))

    def test_wrong_person_aborts_before_strategy_or_any_session(self):
        raw = Mock()
        raw.scenarios.return_value = [{'id':'practice','targets':[{'id':'mara','name':'Mara Felsen'}]}]
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(runner,'Revel8Client',return_value=raw), patch.object(
                    runner,'load_profile',return_value={'name':'Someone Else','facts':[]}), patch.object(
                    runner.strategy,'rank_approaches') as rank, patch.object(
                    runner,'RUNS',Path(directory)), patch.object(runner,'TREE_DIR',Path(directory)/'trees'):
                agent = runner.Orchestrator('mara')
                with redirect_stdout(io.StringIO()): run_id, nodes = agent.run()
                bundle = json.loads((Path(directory)/(run_id+'.json')).read_text())
        rank.assert_not_called(); raw.create_session.assert_not_called(); raw.send_message.assert_not_called()
        self.assertEqual(bundle['run_status'], 'aborted')
        self.assertEqual(bundle['messages'], [])
        self.assertFalse(any(n.level == 'contact' for n in nodes))
        self.assertTrue(any(n.level == 'attempt' for n in nodes))

    def test_observed_live_failure_now_blocks_without_requests(self):
        raw = Mock(); guard = GuardedClient(raw, context(), session_ids=['s1'])
        draft = message()
        draft['body'] = ("Hi Mara,\nWe're reviewing subscriptions and noticed your team relies heavily "
                         "on the analytics platform we use for reporting. Could you confirm any issues?\nBest,\nJonas Weber")
        with self.assertRaises(QualityBlocked): guard.send_message(draft)
        raw.send_message.assert_not_called()

    def test_unrelated_verified_fact_does_not_support_a_tool_claim(self):
        facts = [dict(value='Finance lead', verified=True, source_url='https://company.example/team')]
        self.assertFalse(profile_claim_checks('Your team uses Okta.', facts).passed)
        self.assertFalse(profile_claim_checks('Your team uses Okta.', []).passed)
        self.assertFalse(profile_claim_checks('Ihr Team nutzt Okta.', []).passed)
        self.assertFalse(profile_claim_checks('You are using Okta.', []).passed)

    def test_exact_supported_fact_and_neutral_questions_pass(self):
        facts = [dict(value='Your team uses Okta', verified=True, source_url='https://company.example/tools')]
        for text in ['Your team uses Okta.', 'Which tool does your team use?', 'Do you use Okta?',
                     'Could you tell me which reporting tool you use?', 'Nutzen Sie Okta?']:
            with self.subTest(text=text): self.assertTrue(profile_claim_checks(text, facts).passed)
        self.assertFalse(profile_claim_checks('Your team uses Okta and Salesforce.', facts).passed)

    def test_subject_and_call_turns_cannot_bypass_assertion_check(self):
        raw = Mock(); guard = GuardedClient(raw, context(), session_ids=['s1'],conversation_sessions={'c1':'s1'})
        draft=message();draft['subject']='Your team uses Okta'
        with self.assertRaises(QualityBlocked): guard.send_message(draft)
        with self.assertRaises(QualityBlocked): guard.say('c1','Your team uses Okta.',sid='s1')
        raw.send_message.assert_not_called();raw.say.assert_not_called()

    def test_automatic_correction_can_replace_claim_with_neutral_question(self):
        attempts=[]; raw=Mock();raw.send_message.return_value={'message_id':'m1','events':[],'touches_used':1}
        guard=GuardedClient(raw,context(),session_ids=['s1'])
        def draft(feedback):
            attempts.append(feedback);m=message()
            m['body']='Your team uses Okta.' if not feedback else 'Hi Mara,\nWhich reporting tool do you use?\nBest,\nJonas Weber'
            return m
        prepared=generate_checked(draft,context(),validator=guard.check_message,max_attempts=3)
        guard.send_message(as_shared_message(prepared))
        self.assertEqual(len(attempts),2);raw.send_message.assert_called_once()
