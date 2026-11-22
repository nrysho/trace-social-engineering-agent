"""Sender personas, channel choice, domain checks, logos and the call follow-up (offline)."""
import unittest
from unittest.mock import Mock, patch

import strategy
import writer
from backend import orchestrator as runner
from quality.checks import check_artifact


class DomainTests(unittest.TestCase):
    def test_taken_domain_gets_a_free_variant_and_keeps_its_subdomain(self):
        taken = {"okta-verify.com", "secure-login.com"}
        with patch.object(writer, "domain_taken", side_effect=lambda d: writer._registrable(d) in taken):
            self.assertEqual(writer.free_domain("okta-verify.com"), "okta-verify.co")
            self.assertEqual(writer.free_domain("acme.de.secure-login.com"), "acme.de.secure-login.co")
            self.assertEqual(writer.free_domain("eventcrew-muc.de"), "eventcrew-muc.de")

    def test_registrable_part(self):
        self.assertEqual(writer._registrable("a.b.secure-login.com"), "secure-login.com")
        self.assertEqual(writer._registrable("shop.example.co.uk"), "example.co.uk")


class ChannelTests(unittest.TestCase):
    profile = {"facts": [{"category": "role", "value": "CEO", "source_url": "https://www.linkedin.com/in/x"},
                         {"category": "vendors_and_tools", "value": "sends mail via Microsoft 365", "source_url": "https://dns.google/x"}]}

    def fit(self, pretext, channel):
        return strategy.channel_fit(self.profile, strategy._PRETEXTS_BY_KEY[pretext], channel)[0]

    def test_work_chat_is_for_colleagues_only(self):
        self.assertGreater(self.fit("internal_favor", "teams_chat"), self.fit("internal_favor", "email") - 0.01)
        self.assertLess(self.fit("vendor_notice", "teams_chat"), self.fit("vendor_notice", "email"))
        self.assertLess(self.fit("customer_question", "teams_chat"), 0.3)

    def test_linkedin_when_recon_found_it(self):
        self.assertGreater(self.fit("speaker_invite", "linkedin_message"), self.fit("speaker_invite", "email"))
        self.assertLess(strategy.channel_fit({"facts": []}, strategy._PRETEXTS_BY_KEY["speaker_invite"], "linkedin_message")[0], 0.6)

    def test_channel_switch_after_silence_only_to_a_plausible_channel(self):
        ranked = [dict(pretext="security_alert", channel="email", channel_fit=0.6),
                  dict(pretext="security_alert", channel="sms", channel_fit=0.45),
                  dict(pretext="vendor_notice", channel="email", channel_fit=0.6),
                  dict(pretext="vendor_notice", channel="teams_chat", channel_fit=0.15)]
        self.assertEqual(runner._switch_channel(ranked[0], ranked, {"email"})["channel"], "sms")
        self.assertEqual(runner._switch_channel(ranked[2], ranked, {"email"})["channel"], "email")


class LookTests(unittest.TestCase):
    def test_brand_matching_is_whole_word(self):
        self.assertEqual(writer.brand_of("HubSpot Support"), "HubSpot")
        self.assertIsNone(writer.brand_of("Sapling Partners"))
        self.assertIsNone(writer.brand_of("Berlin Security Summit"))

    def test_logo_asset_passes_the_gate_other_schemes_do_not(self):
        page, _ = writer.render_landing_html(pretext="security_alert", organization="Google Workspace",
                                             title="Sign in", fields=["email", "password"], logo_src="asset://a_7")
        art = {"kind": "page", "html": page, "url": "https://workspace-notice.com/signin"}
        self.assertNotIn("Unsupported hyperlink or resource scheme",
                         check_artifact(art, approved_domains=["workspace-notice.com"]).errors)
        bad = dict(art, html=page.replace("asset://a_7", "file:///etc/logo.png"))
        self.assertIn("Unsupported hyperlink or resource scheme",
                      check_artifact(bad, approved_domains=["workspace-notice.com"]).errors)

    def test_mail_button_sits_above_the_sign_off(self):
        mail = writer.render_mail_html(body="Hi J,\n\nText.\n\nThe Okta Team", organization="Okta",
                                       link={"title": "Review", "url": "https://okta-notice.com/x"})
        self.assertLess(mail.index("Review</a>"), mail.index("The Okta Team"))


class CallFollowUpTests(unittest.TestCase):
    def test_engaged_call_continues_by_mail_with_the_promised_file(self):
        with patch.object(runner, "Revel8Client", return_value=Mock()):
            agent = runner.Orchestrator("tom", use_model=False)
        transcript = [{"role": "them", "text": "Müller, hallo?"}, {"role": "us", "text": "Hallo Tom, Lena hier."},
                      {"role": "them", "text": "Schicken Sie mir das per Mail."}]
        with patch.object(agent, "_run_messages", return_value=True) as run:
            self.assertTrue(agent._follow_up_call("s1", dict(pretext="speaker_invite", channel="phone_call"), Mock(), transcript))
        follow, seed = run.call_args.args[1], run.call_args.kwargs["seed"]
        self.assertEqual(follow["channel"], "email")
        self.assertEqual(follow["attachment"], "Speaker_Briefing.pdf")
        self.assertIn("per Mail", seed["history"][0]["reply"])


class GuardLinkTests(unittest.TestCase):
    def test_uploaded_logo_is_not_an_unregistered_link(self):
        from quality.guarded_client import linked_urls
        html = '<img src="asset://a_3"><a href="https://okta-notice.com/x">Review</a>'
        self.assertEqual(linked_urls(html), {"https://okta-notice.com/x"})


class PageGateTests(unittest.TestCase):
    def test_every_page_passes_the_operational_claim_check(self):
        from quality.story import operational_claim_checks
        for pretext, fields in (("speaker_invite", ["name", "availability", "internal_tool"]),
                                ("press_request", ["email", "password"]), ("security_alert", ["email", "password"])):
            page, _ = writer.render_landing_html(pretext=pretext, organization="Example Events", title="T", fields=fields)
            self.assertEqual(operational_claim_checks(page, []), [], pretext)


class StoryGateTests(unittest.TestCase):
    def test_unconfirmed_fact_that_a_confirmed_one_states_is_not_blocked(self):
        from quality.story import profile_claim_checks
        facts = [{"value": "revel8", "category": "company", "verified": False, "source_url": "https://a.example"},
                 {"value": "Julius Muth is Co-Founder of revel8", "verified": True, "source_url": "https://b.example"},
                 {"value": "raised a seed round of EUR 3M", "verified": False, "source_url": "https://c.example"}]
        self.assertEqual(profile_claim_checks("Hi Julius, I follow revel8 closely.", facts).errors, [])
        self.assertIn("Unverified profile fact stated as certain",
                      profile_claim_checks("Congrats, you raised a seed round of EUR 3M.", facts).errors)


class MaterialTests(unittest.TestCase):
    def test_a_request_for_material_gets_a_matching_file(self):
        reply = "Could you send the names of the two founders and the professor, plus a short programme or agenda?"
        self.assertTrue(runner._asks_for_material(reply))
        self.assertEqual(runner._material_name(reply, "speaker_invite"), "Programme_and_Speakers.pdf")
        self.assertEqual(runner._material_name("Send me a link to a couple of your recent pieces", "press_request"), "Recent_Articles.pdf")
        self.assertFalse(runner._asks_for_material("Which publication is this for?"))

    def test_writer_gate_blocks_urls_and_bracket_placeholders(self):
        for body in ("Here they are: [article1] and [article2].", "See https://techpulse-media.de/a", "Visit www.example.de"):
            with self.assertRaises(ValueError):
                writer.quality_gate({"subject": "", "body": "Hi Julius,\n\n" + body})


if __name__ == "__main__":
    unittest.main()
