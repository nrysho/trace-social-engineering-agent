from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import test_evidence_consistency as fixtures
from quality.claim_coverage import check_coverage, critic_input
from quality.identity_review import IdentityReviewer
from quality.integration import QualityBlocked
from quality.reviewed_client import ReviewedClient
from quality.session_consistency import content_digest, message_content, SessionLedger
from quality.state_store import ReviewStateStore, StateConflict


class Person5Hardening(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.EvidenceConsistency()
        self.f.setUp()
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = ReviewStateStore(Path(self.temp.name)/'review.sqlite3', scope='synthetic-team:practice')
        self.scenarios = [dict(id='practice', open=True, targets=[dict(id='julius', name='Synthetic Twin')])]
        self.profiles = {'julius': dict(name='Synthetic Twin', company='Example Company')}
        self.records = [dict(target_id='julius', candidate_id='public-person-1', name='Synthetic Twin',
                             company='Example Company', review_status='supported',
                             supports=[dict(source_id='s1', quote=self.f.sources[0]['text'])])]

    def identity(self, **kwargs):
        return IdentityReviewer(self.scenarios, self.profiles, self.f.sources, self.records,
                                clock=lambda: fixtures.NOW, **kwargs)

    def durable(self, **kwargs):
        return ReviewedClient(self.f.fake, self.f.context, evidence_catalog=self.f.catalogue(),
                              session_ids=['synthetic-session', 'other-session'], state_store=self.state, **kwargs)

    def critic_result(self, *, kind='nonfactual', claims=None, assertions=None):
        message = self.f.message
        return dict(content_sha256=content_digest(message), complete=True,
                    segments=[dict(start=0, end=len(message_content(message)), kind=kind,
                                   claim_ids=claims or [], assertions=assertions or [])])

    def test_identity_separates_eligibility_from_supported_match(self):
        result = self.identity().assess('julius')
        self.assertTrue(result['passed'])
        self.assertEqual(result['status'], 'supported_match')
        self.assertIsNone(result['person_exists'])
        self.assertIsNone(result['public_identity_verified'])

    def test_no_public_evidence_is_not_person_does_not_exist(self):
        self.records = []
        result = self.identity().assess('julius')
        self.assertTrue(result['authorised_target'])
        self.assertEqual(result['status'], 'insufficient_evidence')
        self.assertIsNone(result['person_exists'])

    def test_wrong_profile_does_not_revoke_official_target_eligibility(self):
        self.profiles['julius']['name'] = 'Another Person'
        result = self.identity().assess('julius')
        self.assertTrue(result['authorised_target'])
        self.assertFalse(result['passed'])
        self.assertEqual(result['status'], 'conflicting')

    def test_two_same_name_people_are_ambiguous(self):
        self.records.append(dict(self.records[0], candidate_id='public-person-2'))
        result = self.identity().assess('julius')
        self.assertFalse(result['passed'])
        self.assertEqual(result['status'], 'ambiguous')

    def test_wrong_company_and_unresolved_identity_are_not_accepted(self):
        for field, value in [('company', 'Another Company'), ('review_status', 'uncertain')]:
            records = deepcopy(self.records)
            records[0][field] = value
            reviewer = IdentityReviewer(self.scenarios, self.profiles, self.f.sources, records, clock=lambda: fixtures.NOW)
            self.assertFalse(reviewer.assess('julius')['passed'])

    def test_missing_name_company_quote_and_stale_sources_fail(self):
        for change in [dict(text='Synthetic Twin, unrelated page'), dict(retrieved_at='2020-01-01T00:00:00Z')]:
            sources = deepcopy(self.f.sources)
            sources[0].update(change)
            reviewer = IdentityReviewer(self.scenarios, self.profiles, sources, self.records, clock=lambda: fixtures.NOW)
            self.assertFalse(reviewer.assess('julius')['passed'])

    def test_conflicting_identity_or_unauthorised_target_blocks(self):
        self.records[0]['review_status'] = 'conflicting'
        self.assertEqual(self.identity().assess('julius')['status'], 'conflicting')
        self.assertFalse(self.identity().assess('julias')['authorised_target'])

    def test_identity_gate_prevents_submission(self):
        self.records = []
        guard = self.durable(identity_reviewer=self.identity())
        with self.assertRaises(QualityBlocked): guard.send_message(self.f.message, review=self.f.review())
        self.f.fake.send_message.assert_not_called()

    def test_critic_detects_writer_omitted_target_claim(self):
        result = self.critic_result(kind='target_fact', claims=['c1'])
        guard = self.durable(critic=lambda payload: result)
        with self.assertRaises(QualityBlocked):
            guard.send_message(self.f.message, review=self.f.review(claims=[]))
        self.f.fake.send_message.assert_not_called()

    def test_critic_requires_exact_full_coverage_and_matching_digest(self):
        for change in [dict(complete=False), dict(content_sha256='old'), dict(segments=[]),
                       dict(segments=[dict(start=1, end=2, kind='nonfactual')])]:
            result = self.critic_result()
            result.update(change)
            self.assertFalse(check_coverage(self.f.message, self.f.review(), result, self.f.catalogue()).passed)

    def test_critic_cannot_invent_a_session_promise(self):
        result = self.critic_result(kind='scenario_story', assertions=[dict(scope='session', key='meeting_date', value='Sunday', kind='scenario_story')])
        report = check_coverage(self.f.message, self.f.review(), result, self.f.catalogue())
        self.assertFalse(report.passed)

    def test_critic_failure_stops_without_transport_or_secret_exception_logging(self):
        guard = self.durable(critic=Mock(side_effect=TimeoutError('SECRET-SHOULD-NOT-APPEAR')))
        with self.assertRaises(QualityBlocked) as caught:
            guard.send_message(self.f.message, review=self.f.review())
        self.assertNotIn('SECRET', str(caught.exception))
        self.f.fake.send_message.assert_not_called()

    def test_hard_rules_run_before_optional_critic(self):
        critic = Mock()
        guard = self.durable(critic=critic)
        self.f.message['sender']['address'] = 'reviewer@official.example'
        with self.assertRaises(QualityBlocked): guard.send_message(self.f.message, review=self.f.review())
        critic.assert_not_called()
        self.f.fake.send_message.assert_not_called()

    def test_critic_classification_does_not_grant_permission(self):
        result = self.critic_result()
        self.assertTrue(check_coverage(self.f.message, self.f.review(), result, self.f.catalogue()).passed)
        payload = critic_input(self.f.message, self.f.catalogue())
        self.assertEqual(payload['content_sha256'], content_digest(self.f.message))
        self.assertNotIn('sources', payload)

    def test_acknowledged_declarations_survive_restart(self):
        first = self.durable()
        first.send_message(self.f.message, review=self.f.review())
        resumed = self.durable()
        followup = self.f.followup()
        review = self.f.review(followup, claims=[], assertions=[dict(scope='session', key='meeting_date', value='Thursday', kind='scenario_story')])
        with self.assertRaises(QualityBlocked): resumed.send_message(followup, review=review)
        self.assertEqual(self.f.fake.send_message.call_count, 1)

    def test_pending_send_survives_restart_and_can_be_reconciled(self):
        first = self.durable()
        self.f.fake.send_message.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError): first.send_message(self.f.message, review=self.f.review())
        resumed = self.durable()
        with self.assertRaises(QualityBlocked): resumed.send_message(self.f.message, review=self.f.review())
        resumed.reconcile_acknowledgement('synthetic-session', self.f.message['idempotency_key'], dict(message_id='m1', events=[]))
        self.assertTrue(self.durable().ledger.snapshot()['declarations'])

    def test_delivered_key_after_restart_does_not_resend(self):
        self.durable().send_message(self.f.message, review=self.f.review())
        with self.assertRaises(QualityBlocked): self.durable().send_message(self.f.message, review=self.f.review())
        self.assertEqual(self.f.fake.send_message.call_count, 1)

    def test_no_raw_bodies_or_reply_values_persisted(self):
        self.f.message['body'] += ' UNIQUE-RAW-BODY'
        self.f.fake.send_message.return_value['events'] = [dict(type='reply', body='UNIQUE-PRIVATE-REPLY', fields={'password': 'SECRET'})]
        self.durable().send_message(self.f.message, review=self.f.review())
        _, state = self.state.load()
        raw = json.dumps(state)
        for text in ('UNIQUE-RAW-BODY', 'UNIQUE-PRIVATE-REPLY', 'SECRET'):
            self.assertNotIn(text, raw)

    def test_storage_failure_before_send_makes_zero_submissions(self):
        guard = self.durable()
        with patch.object(self.state, 'save', side_effect=OSError('Disk full')):
            with self.assertRaises(OSError): guard.send_message(self.f.message, review=self.f.review())
        self.f.fake.send_message.assert_not_called()
        with self.assertRaises(RuntimeError): guard.send_message(self.f.message, review=self.f.review())

    def test_storage_cas_prevents_stale_controller_overwrite(self):
        revision, state = self.state.load()
        self.state.save(revision, dict(example='first'))
        with self.assertRaises(StateConflict): self.state.save(revision, dict(example='stale'))
        self.assertEqual(self.state.load()[1]['example'], 'first')

    def test_changed_permission_context_cannot_reuse_state(self):
        self.durable().send_message(self.f.message, review=self.f.review())
        self.f.context['authorized_targets'] = ['other-person']
        with self.assertRaises(ValueError): self.durable()

    def test_corrupt_ledger_fails_closed_instead_of_resetting(self):
        with self.assertRaises(ValueError): SessionLedger.from_snapshot(dict(declarations=[{}], personas=[]))
        self.state.save(0, dict(schema_version=99))
        with self.assertRaises(ValueError): self.durable()

    def test_pending_conversation_open_survives_restart(self):
        self.f.fake.start_conversation.side_effect = TimeoutError()
        guard = self.durable()
        with self.assertRaises(TimeoutError):
            guard.start_conversation('synthetic-session', 'julius', 'phone_call', self.f.message['sender'], idem_key='open-key')
        resumed = self.durable()
        with self.assertRaises(QualityBlocked):
            resumed.start_conversation('synthetic-session', 'julius', 'phone_call', self.f.message['sender'], idem_key='new-key')
        resumed.reconcile_acknowledgement('synthetic-session', 'open-key', dict(conversation_id='original-call'))
        self.assertEqual(resumed.conversations['original-call'], 'synthetic-session')

    def test_second_session_commit_not_lost_when_first_is_reconciled(self):
        guard = self.durable()
        self.f.fake.send_message.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError): guard.send_message(self.f.message, review=self.f.review())
        self.f.fake.send_message.side_effect = None
        other = self.f.followup(session='other-session', body='Meeting Friday. Layout reviewer')
        guard.send_message(other, review=self.f.review(other, claims=[]))
        guard.reconcile_acknowledgement('synthetic-session', self.f.message['idempotency_key'], dict(message_id='m1', events=[]))
        sessions = {row['session_id'] for row in self.durable().ledger.snapshot()['declarations']}
        self.assertEqual(sessions, {'synthetic-session', 'other-session'})

    def test_actual_api_client_blocks_bad_evidence_before_page_or_message_http(self):
        import requests
        from backend.revel8 import Revel8Client
        client = Revel8Client(key='synthetic-fixture-only', log_dir=self.temp.name)
        self.addCleanup(client.http.close)
        calls = []
        def fake_http(method, url, **kwargs):
            calls.append(url)
            response = requests.Response()
            response.status_code = 200
            value = dict(page_id='synthetic-page') if url.endswith('/pages') else dict(message_id='synthetic-message', events=[], touches_used=1)
            response._content = json.dumps(value).encode()
            return response
        message = deepcopy(self.f.message)
        message['landing_page'] = dict(url='https://review.example/agenda', title='Synthetic', text='Synthetic layout', html='', fields=[])
        guard = ReviewedClient(client, self.f.context, evidence_catalog=self.f.catalogue(),
                               session_ids=['synthetic-session'], state_store=self.state)
        with patch('requests.sessions.Session.request', side_effect=fake_http):
            with self.assertRaises(QualityBlocked): guard.send_message(message, review=self.f.review(message, claims=['invented']))
            self.assertEqual(calls, [])
            guard.send_message(message, review=self.f.review(message))
        self.assertEqual([url.rsplit('/', 1)[-1] for url in calls], ['pages', 'messages'])

    def test_storage_failure_after_ack_keeps_durable_request_pending(self):
        original = self.state.save
        saves = []
        def save(revision, state):
            saves.append(revision)
            if len(saves) == 2:
                raise OSError('Synthetic storage failure after acknowledgement')
            return original(revision, state)
        guard = self.durable()
        with patch.object(self.state, 'save', side_effect=save):
            with self.assertRaises(OSError): guard.send_message(self.f.message, review=self.f.review())
        self.assertEqual(self.f.fake.send_message.call_count, 1)
        resumed = self.durable()
        self.assertEqual(resumed.review_snapshot()['unresolved_sessions'], ['synthetic-session'])
        resumed.reconcile_acknowledgement('synthetic-session', self.f.message['idempotency_key'], dict(message_id='m1', events=[]))
        self.assertFalse(resumed.review_snapshot()['unresolved_sessions'])

    def test_audit_has_join_metadata_and_no_raw_content(self):
        self.durable().send_message(self.f.message, review=self.f.review())
        records = self.state.audit_records()
        self.assertEqual([row['operation'] for row in records], ['evidence.consistency', 'delivery.acknowledged'])
        self.assertEqual(records[0]['node_id'], self.f.message['node_id'])
        self.assertEqual(records[0]['content_sha256'], content_digest(self.f.message))
        self.assertNotIn(self.f.message['body'], json.dumps(records))

    def test_audit_storage_failure_cannot_silently_continue_to_send(self):
        guard = self.durable()
        with patch.object(self.state, 'append_audit', side_effect=OSError('Synthetic write failure')):
            with self.assertRaises(OSError): guard.send_message(self.f.message, review=self.f.review())
        self.f.fake.send_message.assert_not_called()
