"""Offline evidence summaries, never official adjudication of imported JSON.

python -m quality.cli report mock/tree.json --output output/quality/results
"""
from collections import Counter
from html import escape
import json

EVENTS = ('reply', 'link.opened', 'page.submitted', 'attachment.opened')


def _summarize_trace(run):
    if not isinstance(run, dict) or not isinstance(run.get('nodes', []), list):
        raise ValueError('Expected a run object with a nodes array')
    counts = Counter({key: 0 for key in EVENTS})
    seen = {}
    warnings = ['Imported/local record; this report does not authenticate simulator provenance or confirm official outcomes.']
    duplicates = 0
    missing_ids = 0
    observed = set()
    first_signal = None
    for node in run.get('nodes', []):
        if not isinstance(node, dict) or node.get('level') != 'reaction':
            continue
        outcome = node.get('outcome') or {}
        if not isinstance(outcome, dict) or not isinstance(outcome.get('events', []), list):
            raise ValueError('Reaction outcome.events must be an array')
        for event in outcome.get('events', []):
            if not isinstance(event, dict):
                raise ValueError('Each event must be an object')
            event_id = event.get('id')
            if event_id:
                identity = str(event_id)
                if identity in seen:
                    duplicates += 1
                    if event != seen[identity]:
                        warnings.append('Conflicting duplicate event ID; first occurrence retained.')
                    continue
                seen[identity] = event
            else:
                missing_ids += 1
            typ = event.get('type')
            if typ in counts:
                counts[typ] += 1
            signal = None
            if typ == 'attachment.opened':
                signal = 'action'
            if typ == 'page.submitted':
                fields = event.get('fields', [])
                if isinstance(fields, list) and {'email', 'password'}.issubset(str(f).lower() for f in fields):
                    signal = 'credential_submission'
            if signal:
                observed.add(signal)
                # Do not substitute contact-node ordinal or final run total for missing evidence.
                touches = outcome.get('touches_used')
                if first_signal is None:
                    first_signal = {'type': signal, 'event_id': event_id,
                                    'touches_used': touches if type(touches) is int and touches >= 1 else None}
    if missing_ids:
        warnings.append('Events without IDs counted per occurrence; deduplication cannot be guaranteed.')
    if first_signal and first_signal['touches_used'] is None:
        warnings.append('First observed incident signal lacks a recorded cumulative touch count.')
    contacts = run.get('contacts')
    if type(contacts) is not int or contacts < 0:
        contacts = None
        warnings.append('Reported contact count missing or invalid; not replaced with zero.')
    mode = run.get('mode', 'unknown')
    if mode == 'mock':
        warnings.append('SYNTHETIC: exclude this run from real performance results.')
    if run.get('official_outcome'):
        warnings.append('Claimed official_outcome in imported JSON is not authenticated.')
    return {'run_id': run.get('id', 'unknown'), 'target_id': run.get('target_id', 'unknown'),
            'reported_mode': mode, 'synthetic': True if mode == 'mock' else (False if mode in {'practice', 'scoring', 'eval'} else None), 'status': run.get('status', 'unknown'),
            'reported_contacts': contacts, 'event_counts': dict(counts),
            'duplicate_events_ignored': duplicates, 'events_without_ids': missing_ids,
            'observed_signals': sorted(observed), 'first_observed_signal': first_signal,
            'locally_reported_incident': run.get('incident_type'),
            'official_confirmed_incident': None, 'contacts_to_first_confirmed_incident': None,
            'topic_hits': None, 'official_craft_score': None, 'warnings': list(dict.fromkeys(warnings))}


def normalize_record(record):
    """Accept current main's tree array, chat.py JSONL rows, or legacy TRACE object."""
    warnings = []
    if isinstance(record, list):
        if not record or all(isinstance(n, dict) and 'level' in n for n in record):
            run = {'id': next((n.get('run_id') for n in record if n.get('run_id')), 'unknown'),
                   'mode': 'unknown', 'nodes': record}
            warnings.append('Tree-only export: mode and touch count are not established; text outcomes are not parsed as events.')
        else:
            reactions = []
            contacts = set()
            unkeyed = 0
            touch_by_message = {}
            scenarios = set()
            maximum = None
            for row in record:
                if not isinstance(row, dict):
                    raise ValueError('Log entries must be objects')
                kind = row.get('kind')
                if kind == 'session.create' and isinstance(row.get('scenario_id'), str):
                    scenarios.add(row['scenario_id'])
                if kind in {'sent', 'call', 'call.start'}:
                    identity = row.get('message_id' if kind == 'sent' else 'conversation_id')
                    if identity:
                        contacts.add(('message' if kind == 'sent' else 'call', str(identity)))
                    else:
                        unkeyed += 1
                    touches = row.get('touches_used')
                    if type(touches) is int and touches >= 1:
                        maximum = max(maximum or 0, touches)
                        if kind == 'sent' and identity:
                            if str(identity) in touch_by_message and touch_by_message[str(identity)] != touches:
                                warnings.append('Conflicting cumulative touch counts for message ID; timing withheld.')
                                touch_by_message[str(identity)] = None
                            else:
                                touch_by_message[str(identity)] = touches
            for row in record:
                if row.get('kind') == 'event':
                    event = row.get('event')
                    if not isinstance(event, dict):
                        raise ValueError('Event log entries require an event object')
                    mid = row.get('message_id') or event.get('message_id') or event.get('in_reply_to')
                    touches = touch_by_message.get(str(mid)) if mid else None
                    reactions.append({'level': 'reaction', 'outcome': {'events': [event], 'touches_used': touches}})
            mode = next(iter(scenarios)) if len(scenarios) == 1 else 'unknown'
            if len(scenarios) > 1:
                warnings.append('Multiple scenario labels in imported log; keep separate session files.')
            run = {'id': 'imported-api-or-chat-log', 'mode': mode,
                   'contacts': len(contacts) + unkeyed, 'nodes': reactions,
                   'recorded_cumulative_touch_max': maximum}
            warnings.append('Local API/chat log: recorded contacts only, not authoritative session total; call turns do not add touches.')
            if unkeyed:
                warnings.append('Contacts without IDs counted per occurrence; deduplication uncertain.')
    elif isinstance(record, dict):
        run = dict(record)
    else:
        raise ValueError('Expected run object, tree array or chat log entries')
    nodes = run.get('nodes', [])
    if not isinstance(nodes, list):
        raise ValueError('Run nodes must be an array')
    normalized = []
    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError('Tree nodes must be objects')
        entry = dict(node)
        if isinstance(entry.get('outcome'), str):
            if entry['outcome']:
                warnings.append('Text-only outcomes retained as notes, never counted as structured events.')
            entry['outcome'] = {}
        normalized.append(entry)
    run['nodes'] = normalized
    return run, warnings


def summarize_run(record):
    run, warnings = normalize_record(record)
    summary = _summarize_trace(run)
    summary['recorded_cumulative_touch_max'] = run.get('recorded_cumulative_touch_max')
    summary['warnings'] = list(dict.fromkeys(summary['warnings'] + warnings))
    return summary


def decision_records(record):
    if isinstance(record, list):
        nodes = record if all(isinstance(n, dict) and 'level' in n for n in record) else []
    else:
        nodes = record.get('nodes', [])
    records = []
    for n in nodes:
        if n.get('level') not in {'hook', 'approach', 'reaction'}:
            continue
        outcome = n.get('outcome') or {}
        records.append({'node_id': n.get('id'), 'level': n.get('level'),
                        'title': n.get('decision', n.get('title')), 'status': n.get('status'),
                        'recorded_reason': n.get('reasoning', n.get('explanation')) or None,
                        'evidence_refs': n.get('evidence', []),
                        'recorded_alternatives': n.get('rejected', n.get('alternatives', [])),
                        'recorded_next_action': outcome.get('next_action') if isinstance(outcome, dict) else None,
                        'recorded_outcome_note': outcome if isinstance(outcome, str) else None})
    return records


def report_html(summary, decisions):
    """Escaped offline report for a human reviewer; no scripts or external resources."""
    rows = ''.join(f'<li>{escape(k)}: {v}</li>' for k, v in summary['event_counts'].items())
    notes = ''.join(f'<li>{escape(w)}</li>' for w in summary['warnings'])
    records = ''.join('<section><h3>' + escape(str(d['title'] or 'Untitled decision')) + '</h3><p>Status: ' +
                      escape(str(d['status'])) + '</p><p>Recorded reason: ' +
                      escape(str(d['recorded_reason'] or 'Not recorded')) + '</p><pre>' +
                      escape(json.dumps(d['recorded_alternatives'], indent=2)) + '</pre></section>' for d in decisions)
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">'
            '<title>TRACE evidence report</title><style>body{max-width:900px;margin:32px auto;padding:0 24px;'
            'font:16px/1.6 Arial;color:#182633}section{border-top:1px solid #ccd2d8}pre{white-space:pre-wrap;'
            'overflow-wrap:anywhere}</style><h1>TRACE evidence report</h1><p>Run: ' +
            escape(str(summary['run_id'])) + ' | Reported mode: ' + escape(str(summary['reported_mode'])) +
            '</p><p>Reported contacts: ' + escape(str(summary['reported_contacts'])) +
            '</p><p>Duplicate event records ignored: ' + str(summary['duplicate_events_ignored']) +
            '</p><p>Official outcome and topic hits: not established</p><h2>Observed events</h2><ul>' + rows +
            '</ul><h2>Provenance and limits</h2><ul>' + notes + '</ul>' +
            ('<h2>Recorded decisions</h2>' + records if decisions else '') + '</html>')
