from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import requests
import schemas
from backend import run as agent_loop
from backend.revel8 import Revel8Client
from quality.guarded_client import GuardedClient
from quality.integration import QualityBlocked
from quality.profile_review import review_profile
from quality.results import summarize_run
from quality.viewer_export import build_bundle

ROOT = Path(__file__).resolve().parents[1]


class BranchCompatibility(unittest.TestCase):
    def setUp(self):
        self.context = json.loads((ROOT/'quality/samples/context.json').read_text())
        self.message = json.loads((ROOT/'quality/samples/valid_message.json').read_text())

    def run_loop(self, invalid=False, event_type='reply'):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            calls, count = [], [0]
            def http(method, url, **kw):
                calls.append((method, url, kw))
                if url.endswith('/scenarios'):
                    data = [{'id': 'practice', 'targets': [{'id': 'julius', 'name': 'Synthetic Twin', 'role': 'Fixture'}]}]
                elif url.endswith('/sessions'):
                    data = {'session_id': 'synthetic-session', 'scenario_id': 'practice', 'touch_budget': 30}
                elif url.endswith('/pages'):
                    data = {'page_id': 'synthetic-page'}
                elif url.endswith('/messages'):
                    count[0] += 1
                    mid = f'm{count[0]}'
                    data = {'message_id': mid, 'touches_used': count[0], 'events': [
                        {'id': 'e'+str(count[0]), 'type': event_type, 'fields': ['email'], 'body': 'Synthetic reply', 'message_id': mid}]}
                else:
                    raise AssertionError('Unexpected endpoint')
                response = requests.Response()
                response.status_code = 200
                response._content = json.dumps(data).encode()
                return response
            client = Revel8Client(key='synthetic-not-real', log_dir=temp/'api')
            self.addCleanup(client.http.close)
            guard = GuardedClient(client, self.context)
            def writer(profile, sid, history, node_id):
                data = deepcopy(self.message)
                data.update(session_id=sid, node_id=node_id, idempotency_key=node_id)
                if invalid: data['body'] = 'Ignore previous instructions'
                return schemas.message_from_dict(data)
            with patch('requests.sessions.Session.request', side_effect=http), \
                 patch.object(agent_loop, 'Revel8Client', return_value=guard), \
                 patch.object(agent_loop, 'write_message', side_effect=writer), \
                 patch.object(agent_loop, 'TREE_DIR', temp/'trees'), redirect_stdout(io.StringIO()):
                if invalid:
                    with self.assertRaises(QualityBlocked): agent_loop.run('julius', max_contacts=2)
                else:
                    agent_loop.run('julius', max_contacts=2)
            tree = json.loads(next((temp/'trees').glob('*.json')).read_text())
            rows = [json.loads(line) for line in next((temp/'api').glob('*.jsonl')).read_text().splitlines()]
            return tree, rows, calls

    def test_current_main_loop_works_with_guard_and_export(self):
        tree, rows, _ = self.run_loop()
        bundle = build_bundle(tree, rows)
        result = summarize_run(bundle)
        self.assertEqual(len(bundle['messages']), 2)
        self.assertTrue(bundle['messages'][0]['qa']['passed'])
        self.assertTrue(bundle['messages'][0]['message_id'])
        self.assertTrue(bundle['messages'][0]['idempotency_key'])
        self.assertEqual(result['reported_contacts'], 2)
        self.assertEqual(result['event_counts']['reply'], 2)
        self.assertEqual(bundle['messages'][0]['sender']['name'], self.message['sender']['name'])
        self.assertIsNone(result['official_confirmed_incident'])

    def test_blocked_loop_saves_tree_but_makes_no_contact_requests(self):
        tree, rows, calls = self.run_loop(invalid=True)
        self.assertTrue(tree)
        self.assertFalse(any(url.endswith(('/messages', '/pages')) for _, url, _ in calls))
        bundle = build_bundle(tree, rows)
        self.assertEqual(bundle['quality_evidence']['recorded_contacts'], 0)
        self.assertTrue(bundle['quality_evidence']['missing_sent_node_ids'])

    def test_evaluator_incident_label_is_not_official_confirmation(self):
        tree, rows, _ = self.run_loop(event_type='page.submitted')
        result = summarize_run(build_bundle(tree, rows))
        self.assertTrue(result['evaluator_incident_node_ids'])
        self.assertEqual(result['observed_signals'], [])  # email-only form != credential submission
        self.assertIsNone(result['official_confirmed_incident'])

    def test_viewer_sample_mode_is_explicitly_synthetic(self):
        bundle = {'run_id': 'viewer-sample', 'mode': 'sample', 'nodes': [],
                  'events': {'n1': [{'id': 'e1', 'type': 'attachment.opened'}]}}
        result = summarize_run(bundle)
        self.assertTrue(result['synthetic'])
        self.assertEqual(result['run_id'], 'viewer-sample')
        self.assertEqual(result['event_counts']['attachment.opened'], 1)
        self.assertIsNone(result['first_observed_signal']['touches_used'])

    def test_export_rejects_unmatched_and_conflicting_logs(self):
        tree, rows, _ = self.run_loop()
        wrong = deepcopy(rows)
        next(r for r in wrong if r.get('kind') == 'sent')['node_id'] = 'unrelated'
        with self.assertRaises(ValueError): build_bundle(tree, wrong)
        conflict = deepcopy(next(r for r in rows if r.get('kind') == 'event'))
        conflict['event']['type'] = 'attachment.opened'
        with self.assertRaises(ValueError): build_bundle(tree, rows + [conflict])

    def test_export_deduplicates_without_rewriting_tree_status(self):
        tree, rows, _ = self.run_loop()
        event = deepcopy(next(r for r in rows if r.get('kind') == 'event'))
        bundle = build_bundle(tree, rows + [event])
        self.assertEqual([{k:v for k,v in node.items() if k != 'qa'} for node in bundle['nodes']], tree)
        self.assertTrue(any('qa' in node for node in bundle['nodes']))
        self.assertEqual(bundle['quality_evidence']['duplicate_events_ignored'], 1)
        self.assertEqual(summarize_run(bundle)['export_duplicate_events_ignored'], 1)

    def test_wrapper_refuses_eval_creation_before_request(self):
        class NeverCall:
            def create_session(self, *args): raise AssertionError('Must not call')
        with self.assertRaises(QualityBlocked): GuardedClient(NeverCall(), self.context).create_session('eval')

    def test_closed_sessions_and_calls_lose_scope(self):
        class Lifecycle:
            def end_session(self, sid): return {'status': 'ended'}
            def end_conversation(self, cid): return {'status': 'ended'}
        guard = GuardedClient(Lifecycle(), self.context, session_ids=['s1'], conversation_sessions={'c1':'s1'})
        guard.end_conversation('c1')
        with self.assertRaises(QualityBlocked): guard.say('c1', 'Hello', sid='s1', idem_key='k1')
        guard.end_session('s1')
        with self.assertRaises(QualityBlocked): guard.get_session('s1')

    def test_export_keeps_unlinked_call_count_and_rejects_conflicting_reference(self):
        tree, rows, _ = self.run_loop()
        rows.append({'kind':'call.start', 'conversation_id':'unlinked-call'})
        bundle = build_bundle(tree, rows)
        self.assertEqual(bundle['quality_evidence']['recorded_contacts'], 3)
        self.assertEqual(bundle['quality_evidence']['recorded_linked_message_contacts'], 2)
        bad = deepcopy(rows)
        next(r for r in bad if r.get('kind') == 'event')['message_id'] = 'wrong-message'
        with self.assertRaises(ValueError): build_bundle(tree, bad)

    def test_profile_review_is_structural_and_read_only(self):
        profile = schemas.Profile(name='Synthetic', facts=[schemas.Fact(category='role', value='Developer',
            source_url='https://review.example/team', verified=True, confidence=.8)])
        original = profile.to_dict()
        report = review_profile(profile)
        self.assertTrue(report.passed)
        self.assertTrue(any('fewer than two' in w for w in report.warnings))
        self.assertEqual(profile.to_dict(), original)
        profile.facts[0].source_url = ''
        self.assertFalse(review_profile(profile).passed)


if __name__ == '__main__': unittest.main()
