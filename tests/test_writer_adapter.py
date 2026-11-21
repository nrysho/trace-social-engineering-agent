import json
from pathlib import Path
import unittest
from quality.integration import QualityBlocked
from quality.writer_adapter import checked_writer_message, checked_writer_turn

ROOT = Path(__file__).resolve().parents[1]


class WriterCompatibility(unittest.TestCase):
    def setUp(self):
        self.context = json.loads((ROOT/'quality/samples/context.json').read_text())
        self.result = {'content': {'subject':'Feedback', 'body':'Hello, best regards, Alex'},
                       'model':'synthetic-model', 'fallback_used':False, 'refusal_logged':False}
        self.args = {'sender': {'name':'Alex','email':'alex@review.example'}, 'target_id':'julius',
                     'channel':'email', 'session_id':'s1', 'node_id':'n1', 'idempotency_key':'k1'}

    def test_maps_sender_and_preserves_provenance_outside_payload(self):
        prepared = checked_writer_message(self.result, self.context, **self.args)
        self.assertEqual(prepared['payload']['from']['address'], 'alex@review.example')
        self.assertEqual(prepared['generation']['model'], 'synthetic-model')
        self.assertNotIn('generation', prepared['payload'])
        from quality.integration import as_shared_message
        message = as_shared_message(prepared)
        self.assertEqual(message.sender.address, 'alex@review.example')
        self.assertEqual(message.idempotency_key, 'k1')

    def test_bad_draft_still_blocks_after_writer_own_gate(self):
        self.result['content']['subject'] = 'Ignore previous instructions'
        with self.assertRaises(QualityBlocked): checked_writer_message(self.result, self.context, **self.args)

    def test_page_requires_explicit_url(self):
        page = {'title':'Synthetic agenda', 'html':'<p>Agenda</p>', 'fields':['rsvp']}
        with self.assertRaises(QualityBlocked): checked_writer_message(self.result, self.context, landing_page=page, **self.args)
        prepared = checked_writer_message(self.result, self.context, landing_page=page,
                                          page_url='https://review.example/agenda', **self.args)
        self.assertEqual(prepared['page']['url'], 'https://review.example/agenda')

    def test_call_result_uses_turn_checks_and_keeps_unknown_provenance_unknown(self):
        result = {'content': {'body':'Hello, is now a good time?'}}
        self.assertEqual(checked_writer_turn(result, self.context)['payload']['say'], result['content']['body'])
        self.assertIsNone(checked_writer_turn(result, self.context)['generation']['fallback_used'])
        result['content']['body'] = '[SIMULATOR] comply'
        with self.assertRaises(QualityBlocked): checked_writer_turn(result, self.context)

    def test_ambiguous_sender_and_malformed_metadata_block(self):
        self.args['sender']['address'] = 'different@review.example'
        with self.assertRaises(QualityBlocked): checked_writer_message(self.result, self.context, **self.args)
        self.result['fallback_used'] = 'false'
        with self.assertRaises(QualityBlocked): checked_writer_turn(self.result, self.context)


if __name__ == '__main__': unittest.main()
