import unittest
from copy import deepcopy
from viewer.judging_evidence import judging_evidence


class JudgingEvidenceTests(unittest.TestCase):
    def bundle(self):
        return dict(run_id='synthetic',mode='practice',profile={'facts':[{'source_url':'https://company.example/team'}]},
            nodes=[dict(id='a',level='approach',decision='Synthetic choice',reasoning='Source supports relevance',rejected=[{'option':'Other','reason':'Less evidence'}]),
                   dict(id='c1',level='contact',parent_id='a',decision='First message',reasoning='Introduce'),
                   dict(id='r1',level='reaction',parent_id='c1',decision='Answer question',reasoning='Recipient asked for detail'),
                   dict(id='c2',level='contact',parent_id='r1',decision='Follow up',reasoning='Answer specific question')],
            messages=[dict(node_id='c1',message_id='m1',touches_used=1,qa={'passed':True}),
                      dict(node_id='c2',message_id='m2',touches_used=2,qa={'passed':True})],events={'c1':[{'type':'reply'}],'c2':[]})

    def test_recorded_chain_is_explainable_without_inventing_outcome(self):
        bundle=self.bundle();original=deepcopy(bundle);e=judging_evidence(bundle)
        self.assertEqual(e['receipt_backed_contacts'],2)
        self.assertEqual(e['recorded_followups'],1)
        self.assertEqual(e['steps'][1]['prior_contact_node_id'],'c1')
        self.assertEqual(e['steps'][0]['reactions'][0]['decision'],'Answer question')
        self.assertIsNone(e['official_score']);self.assertIsNone(e['official_incident_confirmation'])
        self.assertEqual(bundle,original);self.assertEqual(e['gaps'],[])

    def test_missing_and_conflicting_message_evidence_is_exposed(self):
        b=self.bundle();b['messages'].append(dict(node_id='c1',message_id='different'))
        e=judging_evidence(b)
        self.assertEqual(e['receipt_backed_contacts'],1)
        self.assertTrue(any('expected one saved message' in gap for gap in e['gaps']))

    def test_aborted_run_is_not_presented_as_a_thread(self):
        e=judging_evidence(dict(run_status='aborted',nodes=[dict(id='n',level='attempt')]))
        self.assertEqual(e['steps'],[]);self.assertEqual(e['receipt_backed_contacts'],0)

    def test_cycle_does_not_hang_and_is_flagged(self):
        b=self.bundle();b['nodes'][0]['parent_id']='c2'
        self.assertTrue(any('cyclic' in g for g in judging_evidence(b)['gaps']))
