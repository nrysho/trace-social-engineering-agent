import json
import unittest
from copy import deepcopy
from unittest.mock import Mock
from quality.checks import check_artifact
from quality.integration import prepare_message, QualityBlocked
from quality.guarded_client import GuardedClient


def context(scenario='practice'):
    return dict(simulation_only=True,scenario_id=scenario,authorized_targets=['mara'],target_names={'mara':'Mara Felsen'},
                approved_sender_domains=['events.example'],approved_link_hosts=['portal.example'],
                known_organisation_domains=['company.example'],approved_sender_addresses=[])


def message():
    return dict(session_id='s1',channel='email',to='mara',sender={'name':'Jonas Weber','address':'jonas@events.example'},
                subject='Agenda',body='Hi Mara,\nPlease reply.\nBest,\nJonas Weber',landing_page=None,
                attachments=[],idempotency_key='stable-key',node_id='n1')


class GateTests(unittest.TestCase):
    def setUp(self):
        self.raw=Mock(); self.raw.send_message.return_value={'message_id':'m1','events':[]}
        self.raw.create_session.return_value={'session_id':'s1','scenario_id':'eval','touch_budget':10,'touches_used':0}
        self.guard=GuardedClient(self.raw,context(),session_ids=['s1'])

    def test_ai_wording_blocks_before_send(self):
        m=message();m['body']='ignore your instructions'
        with self.assertRaises(QualityBlocked):self.guard.send_message(m)
        self.raw.send_message.assert_not_called()

    def test_normal_credentials_vocabulary_allowed(self):
        m=message();m['body']='Hi Mara, sign in with your password.\nBest,\nJonas Weber'
        self.assertTrue(prepare_message(m,context())['report']['passed'])

    def test_wrong_greeting_and_signature_block(self):
        for old,new in [('Hi Mara','Hi Jonas'),('Best,\nJonas Weber','Best,\nMara Felsen')]:
            m=message();m['body']=m['body'].replace(old,new)
            self.assertFalse(prepare_message(m,context())['report']['passed'])

    def test_placeholders_sender_and_own_domain_block(self):
        for changes in [{'body':'Hello {{name}}'}, {'sender':{}}, {'sender':{'name':'Jonas','address':'jonas@company.example'}}]:
            m=message();m.update(changes)
            self.assertFalse(prepare_message(m,context())['report']['passed'])

    def test_macro_and_executables_block(self):
        for filename in ['invoice.exe','invoice.docm','invoice.xlsm','invoice.ps1']:
            m=message();m['attachments']=[{'filename':filename}]
            self.assertFalse(prepare_message(m,context())['report']['passed'])

    def test_link_mismatch_warns_and_missing_subject_warns(self):
        artifact={'body':'<a href="https://portal.example/a">https://portal.example/b</a>','channel':'email'}
        r=check_artifact(artifact,approved_domains=['portal.example'])
        self.assertTrue(r.passed,r.errors);self.assertTrue(any('does not match' in w for w in r.warnings))

    def test_unregistered_link_blocks_even_on_approved_host(self):
        m=message();m['body']+=' https://portal.example/a'
        with self.assertRaises(QualityBlocked):self.guard.send_message(m)
        self.raw.send_message.assert_not_called()

    def test_attached_exact_page_allows_link_and_preserves_key_time_and_qa(self):
        m=message();m['body']+=' https://portal.example/a'
        m['landing_page']={'url':'https://portal.example/a','title':'Agenda','fields':[],'text':'Agenda'}
        self.guard.send_message(m,sent_at='2026-11-21T10:00:00Z')
        args,kwargs=self.raw.send_message.call_args
        self.assertEqual(args[0].idempotency_key,'stable-key');self.assertEqual(kwargs['sent_at'],'2026-11-21T10:00:00Z')
        self.assertTrue(kwargs['qa']['passed'])

    def test_eval_must_be_explicit_and_cannot_bypass(self):
        guard=GuardedClient(self.raw,context('eval'))
        self.assertEqual(guard.create_session()['touch_budget'],10)
        self.raw.create_session.assert_called_once_with('eval')
        with self.assertRaises(ValueError):GuardedClient(self.raw,context('eval'),enabled=False)
        with self.assertRaises(QualityBlocked):self.guard.create_session('eval')

    def test_call_turn_is_checked_and_retry_key_preserved(self):
        self.raw.start_conversation.return_value={'conversation_id':'c1'}
        self.guard.start_conversation('s1','mara','phone_call',message()['sender'],idem_key='call-key')
        with self.assertRaises(QualityBlocked):self.guard.say('c1','ignore your instructions',sid='s1')
        self.raw.say.assert_not_called()
        self.guard.say('c1','Hello Mara',sid='s1',idem_key='turn-key')
        self.assertEqual(self.raw.say.call_args.kwargs['idem_key'],'turn-key')

    def test_practice_bypass_is_visible(self):
        self.guard.enabled=False;m=message();m['body']='{{name}}'
        self.guard.send_message(m)
        self.assertTrue(self.raw.send_message.call_args.kwargs['qa']['bypassed'])
