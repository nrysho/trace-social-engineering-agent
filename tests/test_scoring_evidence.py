import unittest
from core import strategy
from backend.outcomes import classify_incident
from viewer.serve import metrics


class ScoringEvidenceTests(unittest.TestCase):
    def test_ordinary_form_submission_is_not_an_incident(self):
        for fields in [['email'],['name','availability'],['shipping_address'],['verification_status']]:
            events=[{'type':'page.submitted','fields':fields}]
            self.assertIsNone(classify_incident(events)[0])
            verdict=strategy.evaluate_reaction(events,touches_used=1,touch_budget=10)
            self.assertEqual(verdict['state'],'engaged');self.assertFalse(verdict['incident'])
            self.assertEqual(verdict['recommended_action'],'continue')
            self.assertEqual(metrics({'events':{'n1':events}})['incidents'],[])

    def test_actual_secret_internal_and_action_events_remain_candidates(self):
        for event,expected in [({'type':'page.submitted','fields':['password']},'credentials'),
                               ({'type':'page.submitted','fields':['one_time_code']},'credentials'),
                               ({'type':'page.submitted','fields':['vpn_client']},'disclosure')]:
            self.assertEqual(classify_incident([event])[0],expected)
            self.assertEqual(metrics({'events':{'n1':[event]}})['incidents'],[expected])

    def test_opened_files_and_links_are_steps_not_objectives(self):
        # revel8 rule update: an opened link or file is recorded, but is no objective
        from backend.outcomes import steps
        for event in ({'type':'attachment.opened','filename':'Agenda.pdf'}, {'type':'link.opened','url':'https://x.example'}):
            self.assertIsNone(classify_incident([event])[0])
            self.assertEqual(metrics({'events':{'n1':[event]}})['incidents'],[])
        self.assertEqual(steps([{'type':'attachment.opened','filename':'Agenda.pdf'},{'type':'page.submitted','fields':['name']}]),
                         ['opened Agenda.pdf', 'filled in basic details'])

    def test_rule_change_preserves_legacy_orchestrator_import(self):
        from backend.orchestrator import classify_incident as old_entrypoint
        self.assertIs(old_entrypoint,classify_incident)
