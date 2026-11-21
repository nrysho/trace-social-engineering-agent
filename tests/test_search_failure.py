import unittest
from unittest.mock import Mock, patch
from backend.recon.search import ddg


class SearchFailureTests(unittest.TestCase):
    def test_challenge_is_a_provider_failure_not_an_empty_search(self):
        for status, text in [(202,'challenge'), (200,'<form id="challenge-form">')]:
            with self.subTest(status=status), patch.object(ddg.requests,'get',return_value=Mock(status_code=status,text=text)):
                with self.assertRaisesRegex(RuntimeError,'TAVILY_API_KEY or SERPER_API_KEY'):
                    ddg.search('Synthetic example')

    def test_normal_search_results_still_parse(self):
        text=('<a href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fcompany.example%2Fteam" '
              'class="result-link">Example team</a><td class="result-snippet">Public profile</td>')
        with patch.object(ddg.requests,'get',return_value=Mock(status_code=200,text=text)):
            results=ddg.search('Synthetic example')
        self.assertEqual(results[0].url,'https://company.example/team')
        self.assertEqual(results[0].snippet,'Public profile')
