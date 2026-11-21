from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from quality.claim_evidence import EvidenceCatalog, profile_claim_candidates
from quality.integration import QualityBlocked
from quality.reviewed_client import ReviewedClient
from quality.session_consistency import content_digest

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 21, 19, tzinfo=timezone.utc)


class EvidenceConsistency(unittest.TestCase):
    def setUp(self):
        self.sources = [dict(source_id='s1', url='https://research.example/profile',
                             retrieved_at='2026-11-21T18:00:00Z',
                             text='Synthetic Twin is the director at Example Company.')]
        self.claims = [dict(claim_id='c1', target_id='julius', fact_key='role',
                            fact_value='director', text='Synthetic Twin is the director',
                            review_status='supported', supports=[dict(source_id='s1', quote=self.sources[0]['text'])])]
        self.context = json.loads((ROOT/'quality/samples/context.json').read_text())
        self.message = json.loads((ROOT/'quality/samples/valid_message.json').read_text())
        self.message['landing_page'] = None
        self.message['body'] = 'Synthetic Twin is the director. Meeting Friday.\nLayout reviewer'
        self.fake = Mock()
        self.fake.send_message.return_value = dict(message_id='m1', events=[], touches_used=1)
        self.guard = self.new_guard()

    def catalogue(self):
        return EvidenceCatalog(self.sources, self.claims, clock=lambda: NOW)

    def new_guard(self):
        return ReviewedClient(self.fake, self.context, evidence_catalog=self.catalogue(),
                              session_ids=['synthetic-session', 'other-session'])

    def review(self, message=None, *, assertions=None, claims=None, persona='reviewer'):
        return dict(schema_version=1, claims_declared=True, persona_id=persona,
                    content_sha256=content_digest(message or self.message),
                    claim_ids=['c1'] if claims is None else claims,
                    assertions=[dict(scope='session', key='meeting_date', value='Friday', kind='scenario_story')]
                    if assertions is None else assertions)

    def send(self, message=None, review=None):
        message = message or self.message
        return self.guard.send_message(message, review=review or self.review(message))

    def followup(self, *, body='Meeting Thursday. Layout reviewer', channel='sms', session=None):
        message = deepcopy(self.message)
        message.update(body=body, channel=channel, idempotency_key='second-key', node_id='second-node')
        if session: message['session_id'] = session
        return message

    def test_supported_claim_passes_and_preserves_request_key(self):
        with patch('requests.sessions.Session.request', side_effect=AssertionError('No real HTTP')):
            self.send()
        sent = self.fake.send_message.call_args.args[0]
        self.assertEqual(sent.idempotency_key, self.message['idempotency_key'])
        self.assertEqual(sent.body, self.message['body'])
        self.assertTrue(self.guard.review_snapshot()['ledger']['declarations'])

    def test_missing_sidecar_blocks_before_any_submission(self):
        with self.assertRaises(QualityBlocked): self.guard.send_message(self.message)
        self.fake.send_message.assert_not_called()

    def test_unknown_claim_blocks(self):
        with self.assertRaises(QualityBlocked): self.send(review=self.review(claims=['invented']))
        self.fake.send_message.assert_not_called()

    def test_source_excerpts_and_timestamp_are_required(self):
        changes = [{'retrieved_at': None}, {'retrieved_at': '2026-11-21T18:00:00'},
                   {'retrieved_at': '2026-11-22T00:00:00Z'}, {'retrieved_at': '2025-01-01T00:00:00Z'},
                   {'text': 'Different content'}, {'url': 'https://user:password@example.com'}]
        for change in changes:
            with self.subTest(change=change):
                sources = deepcopy(self.sources)
                sources[0].update(change)
                report = EvidenceCatalog(sources, self.claims, clock=lambda: NOW).review('julius', self.message['body'], ['c1'])
                self.assertFalse(report.passed)

    def test_other_person_and_unreviewed_claim_block(self):
        for change in [{'target_id': 'different-julius'}, {'review_status': 'needs_review'}, {'supports': []}]:
            claims = deepcopy(self.claims)
            claims[0].update(change)
            report = EvidenceCatalog(self.sources, claims, clock=lambda: NOW).review('julius', self.message['body'], ['c1'])
            self.assertFalse(report.passed)

    def test_conflicting_sources_block_even_if_both_marked_supported(self):
        other = deepcopy(self.claims[0])
        other.update(claim_id='c2', fact_value='engineer')
        report = EvidenceCatalog(self.sources, self.claims+[other], clock=lambda: NOW).review('julius', self.message['body'], ['c1'])
        self.assertTrue(any('conflicting' in e for e in report.errors))

    def test_shared_fact_date_is_activity_date_not_retrieval_proof(self):
        candidate = profile_claim_candidates({'generated_at': '2026-11-21T18:00:00Z', 'facts': [
            dict(category='role', value='Synthetic director', source_url='https://example.com', date='present', verified=True)]}, 'julius')[0]
        self.assertEqual(candidate['activity_date'], 'present')
        self.assertEqual(candidate['review_status'], 'needs_review')
        self.assertNotIn('retrieved_at', candidate)

    def test_stale_review_hash_blocks_modified_message(self):
        review = self.review()
        self.message['body'] += ' Changed after review.'
        with self.assertRaises(QualityBlocked): self.send(review=review)
        self.fake.send_message.assert_not_called()

    def test_cross_channel_date_contradiction_is_blocked(self):
        self.send()
        next_message = self.followup()
        sidecar = self.review(next_message, claims=[], assertions=[dict(scope='session', key='meeting_date', value='Thursday', kind='scenario_story')])
        with self.assertRaises(QualityBlocked): self.send(next_message, sidecar)
        self.assertEqual(self.fake.send_message.call_count, 1)

    def test_consistent_followup_passes_and_different_session_is_independent(self):
        self.send()
        message = self.followup(body='Meeting Friday. Layout reviewer')
        self.send(message, self.review(message, claims=[]))
        other = self.followup(session='other-session')
        sidecar = self.review(other, claims=[], assertions=[dict(scope='session', key='meeting_date', value='Thursday', kind='scenario_story')])
        self.send(other, sidecar)
        self.assertEqual(self.fake.send_message.call_count, 3)

    def test_new_persona_is_allowed_but_session_promises_remain_shared(self):
        self.send()
        message = self.followup(body='Meeting Friday. Another reviewer')
        message['sender']['name'] = 'Another reviewer'
        with self.assertRaises(QualityBlocked): self.send(message, self.review(message, claims=[]))
        self.send(message, self.review(message, claims=[], persona='second-persona'))
        self.assertEqual(self.fake.send_message.call_count, 2)

    def test_persona_scoped_reference_can_differ_for_other_persona(self):
        first = [dict(scope='persona', key='reference', value='Friday', kind='scenario_story')]
        self.send(review=self.review(assertions=first))
        message = self.followup()
        second = [dict(scope='persona', key='reference', value='Thursday', kind='scenario_story')]
        self.send(message, self.review(message, claims=[], persona='second', assertions=second))

    def test_contradictions_within_one_draft_are_blocked(self):
        self.message['body'] += ' Thursday'
        assertions = [dict(scope='session', key='meeting_date', value=d, kind='scenario_story') for d in ['Friday', 'Thursday']]
        with self.assertRaises(QualityBlocked): self.send(review=self.review(assertions=assertions))
        self.fake.send_message.assert_not_called()

    def test_target_fact_needs_matching_claim_reference(self):
        for claim_id in ['c1', 'unknown']:
            assertions = [dict(scope='session', key='role', value='director', kind='target_fact', claim_id=claim_id)]
            report = self.guard.inspect_review(self.message, self.review(assertions=assertions))
            self.assertEqual(report.passed, claim_id == 'c1')

    def test_declared_value_must_be_in_actual_content(self):
        assertions = [dict(scope='session', key='meeting_date', value='Sunday', kind='scenario_story')]
        with self.assertRaises(QualityBlocked): self.send(review=self.review(assertions=assertions))
        self.fake.send_message.assert_not_called()

    def test_timeout_retains_uncertainty_and_blocks_new_sends(self):
        self.fake.send_message.side_effect = TimeoutError('Synthetic')
        with self.assertRaises(TimeoutError): self.send()
        self.assertEqual(self.guard.review_snapshot()['unresolved_sessions'], ['synthetic-session'])
        self.fake.send_message.side_effect = None
        with self.assertRaises(QualityBlocked): self.send(self.followup(), self.review(self.followup(), claims=[]))
        self.assertEqual(self.fake.send_message.call_count, 1)
        self.assertFalse(self.guard.ledger.snapshot()['declarations'])

    def test_reconciliation_requires_original_key_and_ack(self):
        self.fake.send_message.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError): self.send()
        for key, result in [('wrong-key', dict(message_id='m', events=[])), (self.message['idempotency_key'], {})]:
            with self.assertRaises(ValueError): self.guard.reconcile_acknowledgement('synthetic-session', key, result)
        self.guard.reconcile_acknowledgement('synthetic-session', self.message['idempotency_key'], dict(message_id='m', events=[]))
        self.assertFalse(self.guard.review_snapshot()['unresolved_sessions'])
        self.assertTrue(self.guard.ledger.snapshot()['declarations'])

    def test_retry_returns_saved_response_but_key_reuse_with_changed_body_blocks(self):
        self.send()
        self.send()
        self.assertEqual(self.fake.send_message.call_count, 1)
        self.message['body'] += ' New content'
        with self.assertRaises(QualityBlocked): self.send()

    def test_existing_permission_gate_cannot_be_overridden(self):
        self.message['sender']['address'] = 'reviewer@official.example'
        with self.assertRaises(QualityBlocked): self.send()
        self.fake.send_message.assert_not_called()
        self.assertFalse(self.guard.review_snapshot()['unresolved_sessions'])

    def test_call_turn_uses_real_client_contract_not_message_id(self):
        self.fake.start_conversation.return_value = dict(conversation_id='cid')
        self.fake.say.return_value = dict(persona_says='Synthetic answer', ended=False, events=[], turns_used=1)
        sender = self.message['sender']
        self.guard.start_conversation('synthetic-session', 'julius', 'phone_call', sender, idem_key='call-key')
        snapshot = dict(session_id='synthetic-session', conversation_id='cid', to='julius', channel='phone_call', sender=sender,
                        say='Meeting Friday', idempotency_key='turn-key')
        self.guard.say('cid', snapshot['say'], sid='synthetic-session', idem_key='turn-key', review=self.review(snapshot, claims=[]))
        self.assertEqual(self.fake.say.call_count, 1)
        snapshot.update(say='Meeting Thursday', idempotency_key='turn2')
        sidecar = self.review(snapshot, claims=[], assertions=[dict(scope='session', key='meeting_date', value='Thursday', kind='scenario_story')])
        with self.assertRaises(QualityBlocked):
            self.guard.say('cid', snapshot['say'], sid='synthetic-session', idem_key='turn2', review=sidecar)
        self.assertEqual(self.fake.say.call_count, 1)

    def test_standalone_page_cannot_bypass_review(self):
        with self.assertRaises(QualityBlocked): self.guard.register_page('synthetic-session', dict(url='https://review.example'))
        self.fake.register_page.assert_not_called()

    def test_source_snapshot_and_audit_callback_cannot_mutate_payload(self):
        self.sources[0]['text'] = 'Changed original input'
        self.guard.audit = lambda record: record.clear()
        self.send()
        self.assertEqual(self.fake.send_message.call_args.args[0].body, self.message['body'])

    def test_duplicate_catalogue_ids_are_rejected(self):
        with self.assertRaises(ValueError): EvidenceCatalog(self.sources * 2, self.claims)
