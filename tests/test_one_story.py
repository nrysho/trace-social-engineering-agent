"""One story per session, clean recon facts, real colleague names, calls that keep talking (offline)."""
import unittest
from unittest.mock import Mock, patch

import strategy
from backend import orchestrator as runner
from backend.recon import verify
import schemas


def agent_for(target="tom", **kw):
    with patch.object(runner, "Revel8Client", return_value=Mock()):
        return runner.Orchestrator(target, use_model=False, **kw)


class ColleagueNameTests(unittest.TestCase):
    def test_customer_lists_are_not_colleagues(self):
        profile = {"name": "Julius Muth", "facts": [
            {"category": "network", "value": "Lists Boehringer Ingelheim as a customer"},
            {"category": "network", "value": "Partners with Acme Consulting on training"},
        ]}
        self.assertEqual(strategy.first_colleague(profile), "")

    def test_a_named_cofounder_is_a_colleague_but_never_the_target(self):
        profile = {"name": "Julius Muth", "facts": [
            {"category": "network", "value": "Julius Muth is a co-founder of revel8 alongside Tom Müller and Robert Seilbeck."}]}
        self.assertEqual(strategy.first_colleague(profile), "Tom Müller")

    def test_an_organisation_is_not_a_person(self):
        profile = {"name": "Anna Berg", "facts": [
            {"category": "network", "value": "Anna Berg works with Nordhafen Logistik GmbH"}]}
        self.assertEqual(strategy.first_colleague(profile), "")

    def test_writer_uses_the_same_rule(self):
        import writer
        self.assertIs(writer._first_colleague, strategy.first_colleague)


class InsiderPretextTests(unittest.TestCase):
    founder = {"name": "Tom Müller", "role": "Co-Founder & Co-CEO", "company": "revel8", "facts": [
        {"category": "role", "value": "Co-Founder and Co-CEO of revel8", "source_url": "https://revel8.example", "verified": True},
        {"category": "upcoming_events", "value": "Speaks at a security summit in December", "source_url": "https://e.example", "verified": True},
        {"category": "interests", "value": "AI and social engineering", "source_url": "https://e.example", "verified": True},
        {"category": "network", "value": "Lists Boehringer Ingelheim as a customer", "source_url": "https://c.example", "verified": True},
        {"category": "communication_style", "value": "Writes short, direct posts", "source_url": "https://c.example"},
    ]}

    def order(self, profile):
        return [a["pretext"] for a in runner._dedupe_by_pretext(strategy.rank_approaches(profile))]

    def test_a_founder_never_gets_an_executive_request(self):
        order = self.order(self.founder)
        self.assertGreater(order.index("exec_request"), order.index("speaker_invite"))
        exec_score = max(a["score"] for a in strategy.rank_approaches(self.founder) if a["pretext"] == "exec_request")
        speaker = max(a["score"] for a in strategy.rank_approaches(self.founder) if a["pretext"] == "speaker_invite")
        self.assertLess(exec_score, speaker - 0.2)

    def test_an_invented_colleague_ranks_below_a_named_one(self):
        named = dict(self.founder, facts=self.founder["facts"] + [
            {"category": "network", "value": "Tom Müller co-founded revel8 with Julius Muth", "source_url": "https://x.example"}])
        def best(profile, key):
            return max(a["score"] for a in strategy.rank_approaches(profile) if a["pretext"] == key)
        self.assertLess(best(self.founder, "internal_favor"), best(named, "internal_favor"))

    def test_staff_keep_it_and_hr(self):
        clerk = {"name": "Jan Berg", "role": "Sales Assistant", "facts": [
            {"category": "role", "value": "Sales Assistant at Nordhafen", "source_url": "https://x.example", "verified": True}]}
        scores = {a["pretext"]: a["score"] for a in strategy.rank_approaches(clerk)}
        plain = {a["pretext"]: a["score"] for a in strategy.rank_approaches(dict(clerk, role=""))}
        self.assertEqual(scores.get("it_helpdesk"), plain.get("it_helpdesk"))


class CleanProfileTests(unittest.TestCase):
    def test_disputed_facts_never_reach_the_writer(self):
        prof = {"role": "CEO of revel8 [disputed: fact 6 says Co-CEO]", "facts": [
            {"category": "role", "value": "CEO of revel8 [disputed: fact 6 says Co-CEO]"},
            {"category": "role", "value": "Co-CEO of revel8"}]}
        out = runner.clean_profile(prof)
        self.assertEqual(out["role"], "CEO of revel8")
        self.assertEqual([f["value"] for f in out["facts"]], ["Co-CEO of revel8"])
        self.assertIn("[disputed", prof["facts"][0]["value"])          # the input is not mutated

    def test_verify_drops_a_disputed_claim(self):
        facts = [schemas.Fact("role", "CEO of revel8", "https://a.example", confidence=0.9),
                 schemas.Fact("role", "Co-CEO of revel8", "https://b.example", confidence=0.9)]
        with patch.object(verify, "_llm_groups", return_value=[([0], "contradicted by Co-CEO"), ([1], "")]):
            out = verify.verify(facts)
        self.assertEqual([f.value for f in out], ["Co-CEO of revel8"])

    def test_the_scenario_role_line_is_authoritative(self):
        agent = agent_for("tom")
        agent._target_card = lambda: {"id": "tom", "name": "Tom Müller", "role": "Co-Founder & Co-CEO, revel8 (product)", "company": "revel8"}
        prof = {"name": "Tom Müller", "role": "CEO", "facts": [{"category": "role", "value": "x", "source_url": "https://x"}]}
        with patch.object(runner, "load_profile", return_value=prof), \
                patch.object(runner, "research_readiness", return_value=Mock(passed=False, errors=["stop here"], to_dict=lambda: {})), \
                patch.object(agent, "_save_tree"):
            agent.run()
        self.assertEqual(agent.profile["role"], "Co-Founder & Co-CEO, revel8 (product)")


class SessionPerApproachTests(unittest.TestCase):
    def test_practice_opens_a_clean_session_for_each_approach(self):
        agent = agent_for("tom")
        self.assertTrue(agent.fresh_sessions)
        self.assertEqual(agent.budget.total, runner.EVAL_BUDGET)       # practice rehearses an eval run
        counter = iter(range(2, 10))
        agent.client = Mock()
        agent.client.create_session.side_effect = lambda scenario: {
            "session_id": f"s_{next(counter)}", "touch_budget": 30, "touches_used": 0}
        seen = []
        def branch(sid, approach, node):
            seen.append((sid, approach["pretext"], list(approach["session_lessons"])))
            agent.budget.sync(3)
            return False
        approaches = [dict(pretext=p, channel="email", score=1.0) for p in ("speaker_invite", "press_request", "recruiting")]
        with patch.object(agent, "_run_branch", side_effect=branch), patch.object(agent, "_replan", side_effect=lambda r, n: r):
            self.assertFalse(agent._search({}, "s_1", approaches, "n_000"))
        self.assertEqual([s for s, _, _ in seen], ["s_1", "s_2", "s_3"])
        self.assertTrue(all(lessons == [] for _, _, lessons in seen))  # nothing claims a history the person lacks
        self.assertEqual(agent.sessions_opened, ["s_2", "s_3"])

    def test_eval_stays_in_its_one_session(self):
        with patch.object(runner, "Revel8Client", return_value=Mock()):
            agent = runner.Orchestrator("mara", eval_mode=True, use_model=False)
        self.assertFalse(agent.fresh_sessions)
        agent.client = Mock()
        sids = []
        def branch(sid, approach, node):
            sids.append(sid)
            return False
        approaches = [dict(pretext=p, channel="email", score=1.0) for p in ("speaker_invite", "press_request")]
        with patch.object(agent, "_run_branch", side_effect=branch), patch.object(agent, "_replan", side_effect=lambda r, n: r):
            agent._search({}, "s_eval", approaches, "n_000")
        self.assertEqual(sids, ["s_eval", "s_eval"])
        agent.client.create_session.assert_not_called()

    def test_the_old_long_session_is_still_available(self):
        agent = agent_for("tom", fresh_sessions=False)
        self.assertFalse(agent.fresh_sessions)
        self.assertEqual(agent.budget.total, runner.PRACTICE_BUDGET)


class CallClosingTests(unittest.TestCase):
    def test_mail_request_with_questions_keeps_the_call_going(self):
        heard = ("Ein Panel zur dunklen Seite der KI passt gut zu meinen Themen. Wann und wo findet das statt, "
                 "wer sitzt noch auf dem Panel? Schicken Sie mir die Details gern per Mail.")
        self.assertTrue(runner._wants_out(heard))
        self.assertFalse(runner.call_should_close(heard, 1))

    def test_mail_request_without_questions_closes(self):
        self.assertTrue(runner.call_should_close("Schicken Sie mir das per Mail. Auf Wiederhören.", 1))

    def test_a_second_request_for_writing_closes(self):
        self.assertTrue(runner.call_should_close("Wie gesagt, bitte per Mail. Wann genau?", 2))

    def test_a_refusal_closes(self):
        self.assertTrue(runner.call_should_close("Interne Tools gebe ich am Telefon nicht weiter. Was noch?", 0))


class CallBackTests(unittest.TestCase):
    def test_an_unanswered_follow_up_mail_becomes_a_call_back(self):
        agent = agent_for("tom")
        agent.client = Mock()
        seed = {"history": [{"message": "(phone call) hallo", "events": [], "reply": "per Mail bitte"}],
                "scepticism": 3, "call_back": "phone_call"}
        approach = dict(pretext="speaker_invite", channel="email", incident_goal="x")
        with patch.object(runner.strategy, "plan_next_move", return_value={"intent": "nudge", "reason": "silent"}), \
                patch.object(agent, "_run_call", return_value=True) as call:
            self.assertTrue(agent._run_messages("s1", approach, Mock(id="n_1"), seed=seed))
        again, prior = call.call_args.args[1], call.call_args.kwargs["prior"]
        self.assertEqual(again["channel"], "phone_call")
        self.assertTrue(again["is_call_back"])
        self.assertIn("second call", prior[0]["text"])

    def test_a_call_back_never_schedules_another(self):
        agent = agent_for("tom")
        transcript = [{"role": "them", "text": "Müller?"}, {"role": "us", "text": "Hallo."},
                      {"role": "them", "text": "Schicken Sie es per Mail."}]
        with patch.object(agent, "_run_messages", return_value=False) as run:
            agent._follow_up_call("s1", dict(pretext="speaker_invite", channel="phone_call", is_call_back=True), Mock(), transcript)
        self.assertIsNone(run.call_args.kwargs["seed"]["call_back"])


class StatedNeedTests(unittest.TestCase):
    """a need the person stated publicly is the hook itself, for any job, and it leads"""
    import datetime as _dt
    today = _dt.date(2026, 11, 22)

    def needs(self, facts):
        return strategy.stated_needs({"name": "X Y", "facts": facts}, today=self.today)

    def test_a_request_for_recommendations_becomes_a_specific_offer_hook(self):
        fact = {"category": "recent_activity", "source_url": "https://l.example",
                "value": "Sofia Brandt posted asking for recommendations for a summer party venue in Munich for about 180 people"}
        [hook] = self.needs([fact])
        self.assertEqual(hook["pretext"], "solution_offer")
        self.assertEqual(hook["topic"], fact["value"])          # their words, not a catalogue label
        self.assertGreaterEqual(hook["probability"], 0.9)

    def test_hiring_needs_go_to_the_recruiter(self):
        [hook] = self.needs([{"category": "recent_activity", "value": "Robert is actively looking for engineers to join the team",
                              "source_url": "https://l.example"}])
        self.assertEqual(hook["pretext"], "recruiting")

    def test_old_needs_are_closed(self):
        self.assertEqual(self.needs([{"category": "recent_activity", "date": "2024", "source_url": "https://l.example",
                                      "value": "She was looking for a new payroll provider"}]), [])

    def test_last_years_plan_counts_less(self):
        [old] = self.needs([{"category": "recent_activity", "date": "2025", "source_url": "https://l.example",
                             "value": "The company plans to exhibit at more trade fairs"}])
        [new] = self.needs([{"category": "recent_activity", "date": "2026-10", "source_url": "https://l.example",
                             "value": "The company plans to exhibit at more trade fairs"}])
        self.assertLess(old["probability"], new["probability"])

    def test_plain_biography_is_not_a_need(self):
        self.assertEqual(self.needs([{"category": "recent_activity", "value": "Mentors early-career account executives",
                                      "source_url": "https://l.example"}]), [])

    def test_a_stated_need_outranks_a_generic_speaker_invite(self):
        profile = {"name": "Sofia Brandt", "role": "Office and People Operations Manager", "facts": [
            {"category": "role", "value": "Office Manager at Kranich", "source_url": "https://k.example", "verified": True},
            {"category": "upcoming_events", "value": "Panelist at People Ops Practice Day 2026", "source_url": "https://e.example"},
            {"category": "recent_activity", "source_url": "https://l.example",
             "value": "Asking for recommendations for a summer party venue in Munich"}],
            "hooks": [{"topic": "Speaking invite on onboarding", "probability": 0.95, "evidence": []}]}
        best = runner._dedupe_by_pretext(strategy.rank_approaches(profile))[0]
        self.assertEqual(best["pretext"], "solution_offer")
        self.assertTrue(best["stated_need"])
        self.assertIn("summer party venue", best["hook"])


if __name__ == "__main__":
    unittest.main()
