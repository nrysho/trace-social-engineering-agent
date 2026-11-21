"""Synthetic identity/evidence/restart walkthrough. Never creates an HTTP client.

python -m quality.hardening_demo --output output/quality/person5-hardening
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
from uuid import uuid4

from .claim_evidence import EvidenceCatalog
from .claim_coverage import check_coverage
from .identity_review import IdentityReviewer
from .integration import QualityBlocked
from .reviewed_client import ReviewedClient
from .session_consistency import content_digest
from .state_store import ReviewStateStore


class FakeTransport:
    def __init__(self):
        self.calls, self.timeout = 0, False

    def send_message(self, message, sent_at=None, *, qa=None):
        self.calls += 1
        if self.timeout:
            raise TimeoutError('Synthetic timeout; no HTTP request exists')
        return dict(message_id=f'synthetic-{self.calls}', events=[], touches_used=self.calls)


def build_hardening_demo(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    # Fresh namespace permits repeatable demos while retaining earlier evidence.
    state = ReviewStateStore(output/'synthetic-state.sqlite3', scope='demo:'+uuid4().hex)
    now = datetime(2026, 11, 21, 19, tzinfo=timezone.utc)
    source = dict(source_id='source-1', url='https://research.example/person',
                  retrieved_at='2026-11-21T18:00:00Z', text='Synthetic Person is a director at Example Company.')
    claim = dict(claim_id='claim-1', target_id='synthetic-target', fact_key='role:current',
                 fact_value='director', text='Synthetic Person is a director', review_status='supported',
                 supports=[dict(source_id='source-1', quote=source['text'])])
    catalog = EvidenceCatalog([source], [claim], clock=lambda: now)
    scenarios = [dict(id='practice', open=True, targets=[dict(id='synthetic-target', name='Synthetic Person')])]
    profiles = {'synthetic-target': dict(name='Synthetic Person', company='Example Company')}
    record = dict(target_id='synthetic-target', candidate_id='synthetic-public-profile',
                  name='Synthetic Person', company='Example Company', review_status='supported', supports=claim['supports'])
    identity = IdentityReviewer(scenarios, profiles, [source], [record], clock=lambda: now)
    ambiguous = IdentityReviewer(scenarios, profiles, [source], [record, dict(record, candidate_id='another-person')], clock=lambda: now)
    context = dict(simulation_only=True, authorized_targets=['synthetic-target'], approved_sender_domains=['review.example'],
                   approved_link_hosts=[], known_organisation_domains=[], approved_sender_addresses=[])
    message = dict(session_id='synthetic-session', to='synthetic-target', channel='email',
                   sender=dict(name='Layout reviewer', address='reviewer@review.example'),
                   subject='Synthetic exercise', body='Synthetic Person is a director. Meeting Friday.\nLayout reviewer',
                   idempotency_key='synthetic-key-1', node_id='synthetic-node-1', landing_page=None, attachments=[])

    def review(msg, ids=None, day='Friday'):
        return dict(schema_version=1, claims_declared=True, persona_id='coordinator',
                    content_sha256=content_digest(msg), claim_ids=['claim-1'] if ids is None else ids,
                    assertions=[dict(scope='session', key='meeting:demo:date', value=day, kind='scenario_story')])

    transport, cases = FakeTransport(), []
    def guard():
        return ReviewedClient(transport, context, evidence_catalog=catalog, identity_reviewer=identity,
                              session_ids=['synthetic-session'], state_store=state)

    def expect_block(name, action):
        before = transport.calls
        try:
            action()
        except QualityBlocked as exc:
            cases.append(dict(name=name, passed=transport.calls == before, expected='BLOCK before transport',
                              actual='BLOCK', reasons=exc.report.errors))
        else:
            cases.append(dict(name=name, passed=False, expected='BLOCK', actual='unexpected acceptance'))

    good = identity.assess('synthetic-target')
    cases.append(dict(name='Reviewed name + company evidence', passed=good['status'] == 'supported_match',
                      expected='supported_match, not proof of existence', actual=good['status']))
    result = ambiguous.assess('synthetic-target')
    cases.append(dict(name='Two same-name public candidates', passed=result['status'] == 'ambiguous',
                      expected='ambiguous', actual=result['status']))
    client = guard()
    expect_block('Invented claim ID', lambda: client.send_message(message, review=review(message, ['invented'])))
    client.send_message(message, review=review(message))
    cases.append(dict(name='Approved synthetic message', passed=transport.calls == 1,
                      expected='one fake submission', actual=f'{transport.calls} fake submission'))
    next_message = dict(message, body='Meeting Thursday. Layout reviewer', channel='sms', idempotency_key='synthetic-key-2')
    expect_block('Contradictory date after controller restart', lambda: guard().send_message(next_message, review=review(next_message, [], 'Thursday')))
    incomplete = check_coverage(message, review(message), dict(content_sha256=content_digest(message), complete=True, segments=[]), catalog)
    cases.append(dict(name='Incomplete independent critic output', passed=not incomplete.passed,
                      expected='BLOCK', actual='BLOCK' if not incomplete.passed else 'unexpected acceptance', reasons=incomplete.errors))
    transport.timeout = True
    pending = dict(message, idempotency_key='synthetic-key-3')
    try:
        guard().send_message(pending, review=review(pending))
    except TimeoutError:
        pass
    resumed = guard()
    expect_block('Uncertain send remains blocked after restart', lambda: resumed.send_message(next_message, review=review(next_message, [], 'Thursday')))
    resumed.reconcile_acknowledgement('synthetic-session', 'synthetic-key-3', dict(message_id='synthetic-reconciled', events=[]))
    cases.append(dict(name='Original-key acknowledgement reconciliation', passed=not guard().review_snapshot()['unresolved_sessions'],
                      expected='no unresolved request', actual='reconciled fake response'))
    evidence = dict(synthetic=True, real_api_contacts=0, model_requests=0,
                    all_expectations_matched=all(c['passed'] for c in cases), cases=cases,
                    limits='Synthetic sources, fake transport and fixed clock. No real identity, live integration or official outcome established.')
    (output/'evidence.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    (output/'sample-inputs.json').write_text(json.dumps(dict(context=context, sources=[source], claims=[claim],
                                                         scenarios=scenarios, profiles=profiles, identity_records=[record],
                                                         message=message, review=review(message)), indent=2), encoding='utf-8')
    cards = ''.join('<section><h2>'+escape(c['name'])+'</h2><p><b>'+('PASS' if c['passed'] else 'FAIL')+'</b> — '+
                    escape(c['actual'])+'</p><p>Expected: '+escape(c['expected'])+'</p><ul>'+''.join('<li>'+escape(e)+'</li>' for e in c.get('reasons', []))+'</ul></section>' for c in cases)
    html = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\';style-src \'unsafe-inline\'">'
            '<title>Person 5 safety walkthrough — synthetic</title><style>body{font:17px/1.6 system-ui;background:#101a2a;color:#edf2fa;'
            'max-width:980px;margin:40px auto;padding:0 24px}header,section{padding:20px;border:1px solid #50627b;border-radius:12px;margin:18px 0}'
            'header{background:#243752}h1{font-size:30px}h2{font-size:21px}b{color:#9ee6c0}li{overflow-wrap:anywhere}</style>'
            '<header><h1>Person 5: quality and evidence</h1><p>SYNTHETIC OFFLINE WALKTHROUGH · ZERO REAL CONTACTS</p><p>'+escape(evidence['limits'])+'</p></header>'+cards+
            '<footer><p>A supported identity match is evidence, not proof. Critic classifications may be wrong. Team send paths must explicitly adopt the guard.</p></footer></html>')
    (output/'index.html').write_text(html, encoding='utf-8')
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build_hardening_demo(args.output)
    print(json.dumps(result, indent=2))
    return 0 if result['all_expectations_matched'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
