"""Repeatable synthetic offline walkthrough. No model or simulator requests.

python -m quality.demo --output output/quality/walkthrough [--screenshots] [--video]
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from .cli import preview
from .guarded_client import GuardedClient
from .integration import prepare_message, prepare_page, checked_turn, generate_checked, QualityBlocked
from .results import summarize_run, report_html
from .presentation import revision_preview

SAMPLES = Path(__file__).with_name('samples')


def case_results(context):
    results = []
    for case in json.loads((SAMPLES/'test_cases.json').read_text()):
        if case['kind'] == 'message':
            passed = prepare_message(case['artifact'], context)['report']['passed']
        elif case['kind'] == 'page':
            passed = prepare_page(case['artifact'], context)[1].passed
        else:
            try:
                checked_turn(case['artifact'], context)
                passed = True
            except QualityBlocked:
                passed = False
        results.append({'name': case['name'], 'expected_pass': case['expected_pass'],
                        'actual_pass': passed, 'matches': passed == case['expected_pass']})
    return results


class SyntheticClient:
    """In-memory demonstration only. Does not inherit or call a transport."""
    def __init__(self):
        self.send_count = 0
        self.records = [{'kind': 'session.create', 'scenario_id': 'mock'}]

    def send_message(self, message):
        self.send_count += 1
        event = {'id': 'synthetic-event', 'type': 'reply', 'body': 'Synthetic response, not revel8.'}
        self.records.extend([{'kind': 'sent', 'message_id': 'synthetic-message', 'touches_used': 1},
                             {'kind': 'event', 'message_id': 'synthetic-message', 'event': event},
                             {'kind': 'event', 'message_id': 'synthetic-message', 'event': deepcopy(event)}])
        return {'message_id': 'synthetic-message', 'touches_used': 1, 'events': [event]}


def build_demo(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    context = json.loads((SAMPLES/'context.json').read_text())
    valid = json.loads((SAMPLES/'valid_message.json').read_text())
    invalid = json.loads((SAMPLES/'invalid_message.json').read_text())
    cases = case_results(context)
    if not all(c['matches'] for c in cases):
        raise AssertionError('Fixture expectations failed; demo not approved')
    client = SyntheticClient()
    audits = []
    guard = GuardedClient(client, context, session_ids=[valid['session_id']], audit=audits.append)
    valid_report = prepare_message(valid, context)['report']
    try:
        guard.send_message(invalid)
    except QualityBlocked as exc:
        blocked_report = exc.report.to_dict()
    else:
        raise AssertionError('Invalid demonstration content reached fake sender')
    blocked_sends = client.send_count
    retry_audits = []
    def writer(previous):
        return deepcopy(invalid if previous is None else valid)
    corrected = generate_checked(writer, context, max_attempts=2, audit=retry_audits.append)
    # The corrected draft goes through the same final boundary, not directly to sender.
    final_message = {k: v for k, v in corrected['payload'].items() if k != 'from'}
    final_message.update(sender=corrected['payload']['from'], session_id=corrected['session_id'],
                         idempotency_key=corrected['idempotency_key'], node_id=corrected['node_id'],
                         landing_page=corrected['page'])
    guard.send_message(final_message)
    summary = summarize_run(client.records)
    evidence = {'synthetic': True, 'network_requests': 0, 'send_count_after_block': blocked_sends,
                'fake_send_count_after_correction': client.send_count, 'correction_attempts': retry_audits,
                'quality_audit': audits, 'fixture_results': cases, 'summary': summary}
    for name, value in [('evidence', evidence), ('summary', summary)]:
        (output/(name+'.json')).write_text(json.dumps(value, indent=2), encoding='utf-8')
    (output/'pass.html').write_text(preview(valid, valid_report), encoding='utf-8')
    (output/'block.html').write_text(preview(invalid, blocked_report), encoding='utf-8')
    corrected_preview = revision_preview(invalid, final_message, blocked_report, corrected['report'],
                                         attempts=len(retry_audits))
    (output/'corrected.html').write_text(corrected_preview, encoding='utf-8')
    (output/'report.html').write_text(report_html(summary, []), encoding='utf-8')
    (output/'index.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>Person 5 offline walkthrough</title><style>body{max-width:900px;margin:40px auto;padding:24px;
font:19px/1.6 Arial;color:#182633}li{padding:12px 0}a{color:#14528a}pre{white-space:pre-wrap}</style>
<h1>Person 5: checked, corrected, recorded</h1><p><b>SYNTHETIC OFFLINE DEMO.</b> No API key, model call,
simulator request or official outcome. This demonstrates the QA boundary, not the whole agent.</p>
<ol><li><a href="pass.html">Complete message passes</a> with explicit review warnings.</li>
<li><a href="block.html">Invalid message blocks</a>: zero calls to the fake sender.</li>
<li><a href="corrected.html">Automatic correction succeeds</a> on attempt two, then passes the final gate.</li>
<li><a href="report.html">Evidence report</a>: one fake contact, one unique reply, duplicate ignored, no official win.</li></ol>
<p>All ten fixture expectations passed. Machine-readable details: evidence.json.</p>
<p>Actual teammate integration and real practice/scoring results are separate. Human pitch rehearsals remain pending.</p></html>''', encoding='utf-8')
    return evidence, valid, context


def capture(output, valid, context, *, video=False):
    from playwright.sync_api import sync_playwright
    from .render import render_review
    render_review([{'kind': 'message', **prepare_message(valid, context)['payload']},
                   {'kind': 'page', **valid['landing_page']}], output/'craft',
                  approved_domains=context['approved_link_hosts'] + context['approved_sender_domains'])
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        options = {'viewport': {'width': 1280, 'height': 900}, 'java_script_enabled': False,
                   'service_workers': 'block'}
        if video:
            options.update(record_video_dir=str(output/'video'), record_video_size={'width': 1280, 'height': 900})
        try:
            ctx = browser.new_context(**options)
            ctx.route('**/*', lambda route: route.abort())
            page = ctx.new_page()
            clip = page.video if video else None
            for name in ('index', 'pass', 'block', 'corrected', 'report'):
                page.set_content((output/(name+'.html')).read_text(encoding='utf-8'))
                page.screenshot(path=str(output/(name+'.png')), full_page=True)
                if video:
                    if name in {'block', 'corrected'}:
                        page.wait_for_timeout(1800)
                        heading = 'Accepted revision' if name == 'corrected' else 'What needs fixing'
                        page.get_by_role('heading', name=heading, exact=True).scroll_into_view_if_needed()
                        page.wait_for_timeout(2200)
                    else:
                        page.wait_for_timeout(4000)
            ctx.close()
            if clip:
                clip.save_as(str(output/'person5-offline-walkthrough.webm'))
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--screenshots', action='store_true')
    parser.add_argument('--video', action='store_true')
    args = parser.parse_args()
    evidence, valid, context = build_demo(args.output)
    if args.screenshots or args.video:
        capture(args.output, valid, context, video=args.video)
    print(f"Offline demo ready: {args.output/'index.html'}; 10/10 fixtures matched, no network contacts.")


if __name__ == '__main__': main()
