"""Exercise the actual team viewer HTML with synthetic, intercepted API data."""
import json
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('PERSON5_BROWSER_TESTS') == '1', 'Optional Chrome viewer check')
class ViewerQualityUI(unittest.TestCase):
    def test_qa_states_and_results_are_visible_and_safe(self):
        from playwright.sync_api import sync_playwright
        html = (ROOT / 'viewer/index.html').read_text(encoding='utf-8')
        bundle = dict(run_id='synthetic-qa', mode='sample', profile={'name': 'Mara Example'},
            nodes=[dict(id='n1', level='attempt', agent='writer', decision='Synthetic blocked draft',
                        reasoning='', timestamp='2026-11-21T12:00:00Z', status='failed')], messages=[], events={})
        results = dict(totals=[], runs=[dict(id='synthetic-qa', source='synthetic', target='Mara Example',
            touches=0, incidents=[], topic_hits=None, voided=False,
            qa=dict(checked=1, blocked=1, warnings=0, bypassed=0, missing_verdicts=0,
                    conflicting_verdicts=0, local_craft_mean_0_8=6))])
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                def route(request):
                    path = request.request.url.split('person5.test', 1)[-1].split('?', 1)[0]
                    if path == '/': return request.fulfill(body=html, content_type='text/html')
                    if path == '/api/runs': data = [dict(id='synthetic-qa', source='agent', label='Synthetic QA')]
                    elif path == '/api/runs/synthetic-qa': data = bundle
                    elif path == '/api/results': data = results
                    else: return request.abort()
                    request.fulfill(body=json.dumps(data), content_type='application/json')
                page.route('**/*', route)
                cases = [
                    (None, 'Unknown - no saved verdict'),
                    ({'passed': True, 'errors': [], 'warnings': []}, 'Passed'),
                    ({'passed': True, 'errors': [], 'warnings': ['Check signature']}, 'Passed with warnings'),
                    ({'passed': False, 'errors': ['<script>window.injected=true</script>'], 'warnings': []}, 'Blocked'),
                    ({'passed': True, 'bypassed': True, 'errors': [], 'warnings': []}, 'Bypassed - practice checks disabled'),
                    ({'passed': 'yes', 'errors': []}, 'Unknown - no saved verdict'),
                    ({'passed': True, 'errors': ['Contradictory error']}, 'Unknown - no saved verdict'),
                ]
                for qa, label in cases:
                    with self.subTest(label=label):
                        bundle['nodes'][0]['qa'] = qa
                        page.goto('http://person5.test/?run=synthetic-qa&node=n1')
                        panel = page.locator('.quality-panel')
                        panel.wait_for()
                        self.assertEqual(panel.get_attribute('data-qa-status'), label)
                        self.assertIn('not a confirmed sent contact', panel.inner_text())
                        self.assertIsNone(page.evaluate('window.injected'))
                bundle['nodes'][0]['qa'] = {'passed': True, 'errors': [], 'warnings': []}
                bundle['messages'] = [{'node_id': 'n1', 'channel': 'sms', 'body': 'Synthetic',
                    'qa': {'warnings': [], 'errors': [], 'passed': True}}]
                page.goto('http://person5.test/?run=synthetic-qa&node=n1')
                page.locator('[data-qa-status="Passed"]').wait_for()
                bundle['messages'][0]['qa'] = {'passed': False, 'errors': ['Blocked'], 'warnings': []}
                page.goto('http://person5.test/?run=synthetic-qa&node=n1')
                page.locator('[data-qa-status="Conflicting verdicts"]').wait_for()
                page.locator('#tabResults').click()
                page.get_by_text('1 checked; 1 blocked', exact=False).wait_for()
                self.assertIn('6.0/8 local proxy', page.locator('#results').inner_text())
                bundle['run_status']='aborted'
                bundle['abort_reason']='No verified sourced research facts'
                bundle['nodes'][0]['level']='target'
                page.goto('http://person5.test/?run=synthetic-qa&node=n1')
                page.get_by_text('Aborted - no message sent', exact=True).wait_for()
                self.assertIn('No verified sourced research facts', page.locator('#inspector').inner_text())
                self.assertEqual(errors, [])
            finally:
                browser.close()
