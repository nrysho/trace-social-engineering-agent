from copy import deepcopy
import unittest
from unittest.mock import Mock, patch
from backend import orchestrator as runner
from quality.guarded_client import GuardedClient
from quality.integration import as_shared_message, prepare_message
from test_quality_gate import context, message


class RunIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.raw=Mock()
        with patch.object(runner,'Revel8Client',return_value=self.raw):
            self.agent=runner.Orchestrator('mara',use_model=False)
        self.agent.profile={'name':'Mara Felsen','facts':[]}
        self.agent.client=GuardedClient(self.raw,context(),session_ids=['s1'])
        self.node=self.agent.add_node('approach','strategy','Synthetic approach','',None)
        self.saved=[]
        self.agent._save_tree=lambda:self.saved.append(deepcopy(self.agent.messages))

    def test_untrustworthy_touch_counts_cannot_continue_the_message_loop(self):
        draft=as_shared_message(prepare_message(message(),context()))
        for count in [None,0,-1,True,'1']:
            with self.subTest(count=count):
                self.raw.reset_mock()
                self.raw.send_message.return_value={'message_id':'m1','events':[],'touches_used':count}
                with patch.object(runner.writer,'compose',return_value={'landing_page':None}),patch.object(
                        self.agent,'_draft_checked',return_value=draft):
                    with self.assertRaisesRegex(ValueError,'touch count'):
                        self.agent._run_messages('s1',{'pretext':'speaker_invite','incident_goal':'reply'},self.node)
                self.raw.send_message.assert_called_once()
                self.assertEqual(self.agent.messages,[])

    def test_already_acknowledged_call_survives_a_later_turn_failure(self):
        self.raw.start_conversation.return_value={'conversation_id':'c1','touches_used':1,'persona_says':'Hello'}
        self.raw.say.side_effect=[{'persona_says':'Please continue','events':[],'ended':False},TimeoutError('Synthetic timeout')]
        comp={'sender':message()['sender']}
        with patch.object(runner.writer,'compose',return_value=comp),patch.object(
                runner.writer,'generate_call_line',return_value={'content':{'body':'Hello Mara'}}),patch.object(
                self.agent,'_cfg',return_value=object()):
            with self.assertRaises(TimeoutError):
                self.agent._run_call('s1',{'pretext':'speaker_invite','channel':'phone_call'},self.node)
        self.assertEqual(self.agent.budget.used,1)
        self.assertEqual(len(self.agent.messages),1)
        self.assertEqual(self.agent.messages[0]['conversation_id'],'c1')
        self.assertIn('Please continue',self.agent.messages[0]['body'])
        self.assertEqual(self.saved[0][0]['body'],'them: Hello')
        self.raw.start_conversation.assert_called_once()

    def test_invalid_call_start_count_stops_before_call_turns(self):
        self.raw.start_conversation.return_value={'conversation_id':'c1','persona_says':'Hello'}
        with patch.object(runner.writer,'compose',return_value={'sender':message()['sender']}):
            with self.assertRaisesRegex(ValueError,'touch count'):
                self.agent._run_call('s1',{'pretext':'speaker_invite','channel':'phone_call'},self.node)
        self.raw.say.assert_not_called()

    def test_api_count_advancing_past_local_cap_stops_the_loop(self):
        self.agent.budget.total=1
        self.agent._check_contact_touches({'touches_used':2})
        self.agent.budget.sync(2)
        self.assertTrue(self.agent.budget.exhausted())

    def test_uncertain_branch_does_not_pivot_and_send_on_another_branch(self):
        approaches=[{'pretext':'speaker_invite','score':0.5},{'pretext':'press_request','score':0.4}]
        with patch.object(self.agent,'_run_branch',side_effect=TimeoutError('Unknown delivery')) as branch:
            with self.assertRaises(TimeoutError):self.agent._search({},'s1',approaches,None)
        branch.assert_called_once()


class TransportRetryTests(unittest.TestCase):
    def setUp(self):
        from backend.revel8 import Revel8Client
        self.client=Revel8Client(key='synthetic-offline-key')
        self.addCleanup(self.client.http.close)

    def response(self,status,data):
        import requests,json
        response=requests.Response();response.status_code=status
        response._content=json.dumps(data).encode();return response

    def test_session_creation_is_not_repeated_after_a_timeout(self):
        import requests
        from backend.revel8 import ApiError
        with patch.object(self.client.http,'request',side_effect=requests.Timeout('Synthetic timeout')) as request:
            with self.assertRaisesRegex(ApiError,'not retried'):self.client.create_session('eval')
        request.assert_called_once()

    def test_unkeyed_gateway_error_is_not_retried(self):
        from backend.revel8 import ApiError
        with patch.object(self.client.http,'request',return_value=self.response(504,{})) as request:
            with self.assertRaisesRegex(ApiError,'not retried'):self.client._call('POST','/sessions',{'scenario_id':'eval'})
        request.assert_called_once()

    def test_message_retry_keeps_original_key_and_payload(self):
        import requests
        with patch.object(self.client.http,'request',side_effect=[requests.Timeout('Synthetic timeout'),self.response(200,{'message_id':'m1'})]) as request,patch(
                'backend.revel8.time.sleep'):
            self.client._call('POST','/sessions/s1/messages',{'body':'Synthetic'},idempotent=True,idem_key='stable-original')
        self.assertEqual(request.call_count,2)
        self.assertEqual(request.call_args_list[0],request.call_args_list[1])
