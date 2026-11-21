"""Bounded JSON stdin adapter for the local Node practice proxy. No network."""
import json
import sys
from pathlib import Path
from .guarded_client import GuardedClient, LIVE_CHANNELS
from .integration import QualityBlocked, inspect_artifact, prepare_page, checked_turn
from .checks import QualityReport


def validate(request):
    # Policy is loaded from the repository, never accepted from a browser draft.
    playbook = json.loads((Path(__file__).resolve().parents[1] / 'senders.json').read_text(encoding='utf-8'))
    senders, links = set(), set()
    for item in playbook['pretexts'].values():
        domain = item['domain'].replace('{brand}', 'revel8').replace('{tld}', 'ai')
        senders.add(domain)
        if item.get('page'):
            links.add(item['page']['domain'].replace('{brand}', 'revel8').replace('{tld}', 'ai'))
    targets = request['targets']
    context = dict(simulation_only=True, scenario_id='practice',
                   authorized_targets=[t['id'] for t in targets],
                   target_names={t['id']: t['name'] for t in targets},
                   approved_sender_domains=sorted(senders), approved_link_hosts=sorted(links),
                   known_organisation_domains=['revel8.ai'], approved_sender_addresses=[])
    sid, operation, payload = request['sid'], request['operation'], request['payload']
    guard = GuardedClient(None, context, session_ids=[sid])
    guard.registered[sid] = set(request.get('registered', []))
    for text in request.get('history', []):
        guard.story.commit(sid, 'session', text)
    if operation == 'message':
        report = guard.check_message(dict(payload, session_id=sid, idempotency_key=request['key']))['report']
    elif operation == 'page':
        _, qa = prepare_page(payload, context)
        report = qa.to_dict()
    elif operation == 'start':
        qa = inspect_artifact(dict(kind='turn', say='Conversation start', channel=payload.get('channel')),
                              context, sender=payload.get('from') or {})
        if payload.get('to') not in context['authorized_targets'] or payload.get('channel') not in LIVE_CHANNELS:
            qa.errors.append('Conversation target/channel outside practice scope')
        if set(payload) - {'to', 'channel', 'from'}:
            qa.errors.append('Unknown conversation fields')
        report = qa.to_dict()
    elif operation == 'turn':
        checked_turn(payload, context)
        guard.conversations['current'] = sid
        report = guard.check_turn('current', payload.get('say'), sid=sid)
    else:
        raise ValueError('Unknown operation')
    return report


def main():
    try:
        raw = sys.stdin.buffer.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('Validation input too large')
        report = validate(json.loads(raw))
    except QualityBlocked as exc:
        report = exc.report.to_dict()
    except Exception:
        report = QualityReport(errors=['Quality validation unavailable or malformed input; no submission permitted']).to_dict()
    print(json.dumps(report))


if __name__ == '__main__':
    main()
