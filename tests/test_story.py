import unittest
from quality.story import StoryLedger, profile_claim_checks

class StoryTests(unittest.TestCase):
    def test_time_change_blocks_count_change_warns(self):
        ledger=StoryLedger();ledger.commit('s','panel','Friday 9-11am, 100 students')
        result=ledger.review('s','panel','Friday 10-11am, 120 attendees')
        self.assertTrue(any('time' in e for e in result.errors));self.assertTrue(any('count' in w for w in result.warnings))
    def test_date_change_blocks_across_personas_but_not_other_events(self):
        ledger=StoryLedger();ledger.commit('s','panel','Friday')
        self.assertFalse(ledger.review('s','panel','Thursday').passed)
        self.assertTrue(ledger.review('s','other-event','Thursday').passed)
    def test_unknown_details_do_not_invent_a_contradiction(self):
        ledger=StoryLedger();ledger.commit('s','panel','Friday 9-11am')
        self.assertTrue(ledger.review('s','panel','Please reply').passed)
    def test_declared_names_and_organisations_warn(self):
        ledger=StoryLedger();ledger.commit('s','panel','',{'organiser':'Jonas'})
        result=ledger.review('s','panel','',{'organiser':'Clara'})
        self.assertTrue(result.passed);self.assertTrue(result.warnings)
    def test_certain_unverified_profile_fact_blocks(self):
        facts=[{'value':'You are the CFO','verified':False}]
        self.assertFalse(profile_claim_checks('You are the CFO.',facts).passed)
        self.assertTrue(profile_claim_checks('Perhaps you are the CFO.',facts).passed)
    def test_verified_fact_requires_craft_warning_if_source_missing(self):
        result=profile_claim_checks('You are the CFO',[{'value':'You are the CFO','verified':True}])
        self.assertTrue(result.passed);self.assertTrue(result.warnings)

    def test_channel_and_ask_craft_issues_only_warn(self):
        from quality.checks import check_artifact
        report=check_artifact({'kind':'message','channel':'sms','subject':'Unexpected','body':'Please reply. Could you confirm? '+('Text '*100)})
        self.assertTrue(report.passed);self.assertTrue(any('subject' in w for w in report.warnings));self.assertTrue(any('one clear ask' in w for w in report.warnings))

    def test_formal_target_greeting_does_not_block_valid_email(self):
        from test_quality_gate import context,message
        from quality.integration import prepare_message
        candidate=message();candidate['body']=candidate['body'].replace('Hi Mara,','Dear Dr Felsen,')
        self.assertTrue(prepare_message(candidate,context())['report']['passed'])
