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


class RefusalReadingTests(unittest.TestCase):
    def test_a_formal_invitation_is_not_a_refused_form(self):
        heard = ("I'm not sure which talk you mean, but I'm happy to review a formal invitation. "
                 "Please email me the link to the official conference page.")
        self.assertEqual(runner._refused(heard), set())

    def test_refusals_are_read_per_clause(self):
        self.assertEqual(runner._refused("Bitte keine Anhänge, schicken Sie mir einen Link."), {"files"})
        self.assertEqual(runner._refused("Links klicke ich nicht an, PDFs öffne ich nicht."), {"files", "links"})
        self.assertEqual(runner._refused("I don't open attachments or links from people I don't know."), {"files", "links"})

    def test_asking_for_the_page_counts_as_asking_for_a_link(self):
        self.assertTrue(runner._WANTS_LINK.search("Schicken Sie mir die Seite zur Veranstaltung"))
        self.assertTrue(runner._WANTS_LINK.search("send me the event page and agenda"))


class SenderIdentityTests(unittest.TestCase):
    def test_a_taken_domain_never_gets_a_hyphen_inside_a_word(self):
        import writer
        taken = {"insightflow.de", "insightflow.co", "insightflow.io", "insightflow.net", "insightflow.eu",
                 "insightflow.org", "insightflow.com"}
        with patch.object(writer, "domain_taken", side_effect=lambda d: d in taken):
            out = writer.free_domain("insightflow.de")
        self.assertTrue(out.startswith("insightflow"), out)
        self.assertNotIn("ins-ight", out)

    def test_nordic_letters_survive_in_the_address(self):
        import writer
        self.assertEqual(writer._local_part("Elin Søderberg"), "elin.soderberg")

    def test_each_sender_has_its_own_fixed_number(self):
        import writer
        a, b = writer.sender_phone("lena@k8s-reliability.de"), writer.sender_phone("katrin@cn-talent.de")
        self.assertEqual(a, writer.sender_phone("LENA@k8s-reliability.de"))
        self.assertNotEqual(a, b)
        self.assertRegex(a, r"^\+49 30 23125 \d{3}$")

    def test_the_writer_is_given_that_number(self):
        import json, writer
        seen = {}
        def fake(config, model, messages):
            seen["payload"] = json.loads(messages[1]["content"])
            return json.dumps({"subject": "Hallo", "body": "Hallo"})
        cfg = writer.ModelConfig(api_key="x", fallback_model="f")
        with patch.object(writer, "_completion", side_effect=fake), patch.object(writer, "quality_gate"):
            writer.generate_message(cfg, target={"name": "Anna Berg"}, approach={"channel": "email", "pretext": "solution_offer"},
                                    sender={"name": "Miriam Kolb", "email": "miriam.kolb@kolb-partners.de"}, verified_facts=[])
        self.assertEqual(seen["payload"]["you_are"]["phone"], writer.sender_phone("miriam.kolb@kolb-partners.de"))


class DeliverAfterCallTests(unittest.TestCase):
    def test_the_mail_a_call_promised_delivers_before_it_asks(self):
        agent = agent_for("tom")
        agent.client = Mock()
        agent.budget = runner.TouchBudget(10, 6)
        seed = {"history": [{"message": "(phone call) hallo", "events": [], "reply": "Schicken Sie mir das Angebot per Mail."}],
                "scepticism": 2, "call_back": None}
        steps = []
        def draft(step, sid, node, history, include_link):
            steps.append(step)
            raise RuntimeError("stop after the first draft")
        approach = dict(pretext="solution_offer", channel="email", incident_goal="x", attachment="Proposal_and_Options.pdf")
        with patch.object(agent, "_draft_checked", side_effect=draft):
            agent._run_messages("s1", approach, Mock(id="n_1"), seed=seed)
        self.assertEqual(steps[0]["next_move"], "deliver")
        self.assertEqual(steps[0]["attachment"], "Proposal_and_Options.pdf")

    def test_the_writer_knows_the_deliver_move(self):
        import writer
        self.assertIn("deliver", writer.MOVE_GUIDANCE)
        self.assertIn("No internal question".lower(), writer.MOVE_GUIDANCE["deliver"].lower().replace("ask no internal question", "no internal question"))


class StoryConsistencyTests(unittest.TestCase):
    def test_a_vendor_writes_about_its_own_brand_only(self):
        import writer
        self.assertEqual(writer.brand_clash("HubSpot Renewals Team", "Microsoft 365 Renewal for revel8"), "Microsoft 365")
        self.assertEqual(writer.brand_clash("HubSpot Renewals Team", "Your HubSpot renewal"), "")
        self.assertEqual(writer.brand_clash("Nordic Finance Forum", "We use Slack and Microsoft 365"), "")   # not a vendor

    def test_the_quality_gate_rejects_a_brand_clash(self):
        import writer
        with self.assertRaises(ValueError):
            writer.quality_gate({"subject": "Microsoft 365 Renewal", "body": "Hallo Robert, ..."}, sender_org="HubSpot Renewals Team")

    def test_a_known_founder_is_never_an_assistant(self):
        import writer
        facts = [{"value": "Julius Muth is a co-founder of revel8 alongside Tom Müller and Robert Seilbeck."}]
        self.assertTrue(writer._demotes("Tom Müller", "Executive Assistant", facts))
        self.assertFalse(writer._demotes("Tom Müller", "Co-Founder & Co-CEO", facts))
        self.assertFalse(writer._demotes("Anna Berg", "Executive Assistant", facts))   # nothing known about her

    def test_a_replan_cannot_lift_a_penalised_approach(self):
        model_order = [dict(pretext="meeting_reschedule", score=0.4), dict(pretext="recruiting", score=0.95),
                       dict(pretext="press_request", score=0.8)]
        out = [a["pretext"] for a in runner.keep_score_band(model_order)]
        self.assertEqual(out, ["recruiting", "press_request", "meeting_reschedule"])

    def test_a_replan_may_reorder_close_options(self):
        model_order = [dict(pretext="press_request", score=0.8), dict(pretext="recruiting", score=0.95)]
        self.assertEqual([a["pretext"] for a in runner.keep_score_band(model_order)], ["press_request", "recruiting"])

    def test_a_quiet_engaged_thread_gets_one_nudge(self):
        first = strategy.plan_next_move(turn=3, last_state="silent", engaged_count=1, nudged=0)
        second = strategy.plan_next_move(turn=4, last_state="silent", engaged_count=1, nudged=1)
        self.assertEqual(first["intent"], "nudge")
        self.assertTrue(second.get("stop"))


class JudgedDisclosureTests(unittest.TestCase):
    def mail_run(self, events, judged):
        agent = agent_for("tom")
        agent.client = Mock()
        agent.client.send_message.side_effect = [
            {"message_id": "m1", "events": events[0], "touches_used": 1},
            {"message_id": "m2", "events": events[1], "touches_used": 2}]
        agent.client.last_report = {}
        agent.use_model = True                  # the writer is mocked; with it off a thread is one mail
        agent.budget = runner.TouchBudget(10, 6)
        msgs = [Mock(body=f"Hallo, Nachricht {i}", subject="Hi", channel="email", to_dict=lambda: {}) for i in (1, 2)]
        approach = dict(pretext="solution_offer", channel="email", incident_goal="x")
        with patch.object(agent, "_draft_checked", side_effect=msgs), \
                patch.object(agent, "_judge_disclosure", side_effect=judged), \
                patch.object(agent, "_judge_scepticism", return_value=(1, "fine")), \
                patch.object(runner.strategy, "assess_scepticism", return_value={"score": 1, "reason": "fine"}), \
                patch.object(agent, "_save_tree"):
            return agent, agent._run_messages("s1", approach, Mock(id="n_1"))

    def test_a_judged_disclosure_does_not_end_the_run(self):
        reply = [{"type": "reply", "body": "Bei uns entscheidet Mira Hansen aus People & Culture."}]
        signed_in = [{"type": "page.submitted", "fields": ["email", "password"],
                      "values": {"email": "tom@x.example", "password": "(entered, not shown)"}}]
        agent, won = self.mail_run([reply, signed_in], [("disclosure", "named the decider"), (None, "")])
        self.assertTrue(won)                                     # the typed secret ended it, not the judge
        self.assertEqual(agent.client.send_message.call_count, 2)
        self.assertEqual(len(agent.judged_disclosures), 1)
        self.assertEqual(agent.judged_disclosures[0]["touch"], 1)


class ConcreteIncidentTests(unittest.TestCase):
    def test_the_proposal_page_asks_the_internal_details_as_fields(self):
        import writer
        from backend import outcomes
        landing = writer.compose({"name": "Anna Berg", "domain": "nordhafen.de"}, dict(pretext="solution_offer", channel="email"))["landing_page"]
        self.assertTrue(set(landing["fields"]) & outcomes.DISCLOSURE_FIELDS)   # a submitted field is an API event
        page, _ = writer.render_landing_html(pretext="solution_offer", organization="Kolb Partners",
                                             title="Your proposal", fields=landing["fields"])
        self.assertIn("Who signs off on this on your side?", page)

    def test_the_proposal_link_waits_until_they_engage(self):
        self.assertFalse(runner._is_lure_goal(strategy._PRETEXTS_BY_KEY["solution_offer"].incident_goal))

    def test_every_story_has_a_file_to_open(self):
        for p in strategy.PRETEXTS:
            if p.key in ("security_alert", "it_helpdesk"):          # sign-in lures: the page is the event
                continue
            self.assertIn(p.key, runner.FOLLOW_UP_ATTACHMENTS, p.key)

    def test_a_submitted_internal_field_is_a_confirmed_disclosure(self):
        from backend import outcomes
        events = [{"type": "page.submitted", "fields": {"name": "Anna", "approver": "Finance lead"}}]
        kind, _ = outcomes.classify_incident(events)
        self.assertEqual(kind, "disclosure")

    def test_judged_disclosures_carry_a_grade(self):
        agent = agent_for("tom")
        node = Mock(id="n_9", outcome="")
        agent._note_judged("s1", node, "disclosure", "[soft] Tom revealed internal details: Mira Hansen")
        agent._note_judged("s1", node, "disclosure", "[concrete] Tom revealed internal details: ServiceNow")
        self.assertEqual([d["grade"] for d in agent.judged_disclosures], ["soft", "concrete"])


class NewObjectiveRulesTests(JudgedDisclosureTests):
    def test_an_opened_file_is_a_step_and_the_run_goes_on(self):
        opened = [{"type": "attachment.opened", "filename": "Proposal.pdf"}]
        reply = [{"type": "reply", "body": "Freigegeben, bitte reservieren Sie den Termin."}]
        agent, won = self.mail_run([opened, reply], [("action", "[concrete] Tom acted for the sender: approved")])
        self.assertFalse(won)                                    # neither the file nor a judged act ends it
        self.assertEqual(agent.client.send_message.call_count, 2)
        self.assertEqual([d["kind"] for d in agent.judged_disclosures], ["action"])

    test_a_judged_disclosure_does_not_end_the_run = None

    def test_the_bench_scores_by_the_new_rules(self):
        from bench import server
        self.assertNotIn("attachment.opened\" else []", open(server.__file__).read())


if __name__ == "__main__":
    unittest.main()
