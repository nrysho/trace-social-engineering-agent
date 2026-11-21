"""Explicitly join one selected tree and one selected API log for Neryss's viewer.

No automatic session guessing; no schema, viewer, API or model modifications.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from .checks import Markup
from .results import summarize_run


def build_bundle(tree, api_rows, *, profile=None):
    if not isinstance(tree, list) or any(not isinstance(n, dict) for n in tree):
        raise ValueError('Tree must be an array of nodes')
    if not isinstance(api_rows, list) or any(not isinstance(r, dict) for r in api_rows):
        raise ValueError('API log must contain objects')
    nodes = deepcopy(tree)
    ids = [n.get('id') for n in nodes]
    if any(not isinstance(n, str) or not n for n in ids) or len(set(ids)) != len(ids):
        raise ValueError('Tree nodes need unique nonempty IDs')
    run_ids = {n.get('run_id') for n in nodes if n.get('run_id')}
    if len(run_ids) != 1:
        raise ValueError('Select a nonempty tree belonging to exactly one run')
    run_id = next(iter(run_ids))
    contacts = {n['id']: n for n in nodes if n.get('level') == 'contact'}
    sent = {}
    mid_to_node = {}
    pages = {}
    warnings = ['Imported local tree/API log; source selection is explicit but provenance is not authenticated.']
    modes = {r.get('scenario_id') for r in api_rows if r.get('kind') == 'session.create' and isinstance(r.get('scenario_id'), str)}
    if len(modes) > 1:
        raise ValueError('Multiple scenario labels; export one selected session log at a time')
    for row in api_rows:
        if row.get('kind') == 'page' and isinstance(row.get('url'), str):
            pages[row['url']] = {key: deepcopy(row[key]) for key in ('url', 'title', 'fields', 'html', 'text') if key in row}
        if row.get('kind') != 'sent':
            continue
        node_id, mid = row.get('node_id'), row.get('message_id')
        # Reject unrelated sessions rather than joining reused n_001/n_002 IDs silently.
        if node_id not in contacts:
            raise ValueError('API sent record has no matching tree contact node; select the correct tree/log pair')
        if not isinstance(mid, str) or not mid or not isinstance(row.get('message'), dict):
            raise ValueError('API sent records require message_id and message object')
        if node_id in sent and sent[node_id] != row:
            # Repeated identical payload/response IDs are retry observations, not a new message.
            old = sent[node_id]
            if any(old.get(k) != row.get(k) for k in ('message_id', 'message', 'touches_used')):
                raise ValueError('Conflicting sent records for contact node')
        if mid in mid_to_node and mid_to_node[mid] != node_id:
            raise ValueError('Message ID maps to multiple contact nodes')
        sent[node_id] = row
        mid_to_node[mid] = node_id
    messages, event_map, touches = [], {}, {}
    for node_id, row in sent.items():
        raw = row['message']
        if not isinstance(raw.get('to'), str) or not isinstance(raw.get('body'), str):
            raise ValueError('Logged message is missing recipient or body')
        parsed = Markup()
        parsed.feed(raw['body'])
        parsed.close()
        linked_pages = [pages[url] for url in parsed.links if url in pages]
        if len(linked_pages) > 1:
            warnings.append('Multiple registered pages linked; viewer Message carries only the first. All page records remain in quality_evidence.')
        messages.append({'node_id': node_id, 'to': raw['to'], 'channel': raw.get('channel'),
                         'sender': deepcopy(raw.get('from')), 'subject': raw.get('subject', ''),
                         'body': raw['body'], 'attachments': deepcopy(raw.get('attachments', [])),
                         'landing_page': deepcopy(linked_pages[0]) if linked_pages else None})
        event_map[node_id] = []
        if type(row.get('touches_used')) is int and row['touches_used'] >= 1:
            touches[node_id] = row['touches_used']
    unjoined = []
    seen_events = {}
    duplicates = 0
    for row in api_rows:
        if row.get('kind') != 'event':
            continue
        event = row.get('event')
        if not isinstance(event, dict):
            raise ValueError('API event must be an object')
        mid = row.get('message_id') or event.get('message_id') or event.get('in_reply_to')
        embedded_mid = event.get('message_id') or event.get('in_reply_to')
        if row.get('message_id') and embedded_mid and row['message_id'] != embedded_mid:
            raise ValueError('Event envelope and payload reference different messages')
        node_id = mid_to_node.get(mid) if isinstance(mid, str) else None
        identity = event.get('id')
        if identity:
            key = str(identity)
            if key in seen_events:
                if seen_events[key] != (node_id, event):
                    raise ValueError('Conflicting duplicate event ID')
                duplicates += 1
                continue
            seen_events[key] = (node_id, deepcopy(event))
        if node_id is None:
            unjoined.append(deepcopy(event))
        else:
            event_map[node_id].append(deepcopy(event))
    missing = [node_id for node_id in contacts if node_id not in sent]
    if missing:
        warnings.append('Some tree contact nodes have no sent API record; they are not counted as completed contacts.')
    if unjoined:
        warnings.append('Some API events cannot be linked to a sent tree node; they remain separately recorded, not silently attributed.')
    if any(r.get('kind') == 'call.start' for r in api_rows):
        warnings.append('Current API call logs lack tree node IDs; call transcripts/events cannot be safely joined to viewer contacts.')
    bundle = {'run_id': run_id, 'mode': next(iter(modes)) if modes else 'unknown',
              'profile': deepcopy(profile) if isinstance(profile, dict) else {},
              'nodes': nodes, 'messages': messages, 'events': event_map,
              'quality_evidence': {'recorded_contacts': summarize_run(api_rows)['reported_contacts'],
                                   'recorded_linked_message_contacts': len(sent), 'touches_by_node': touches,
                                   'missing_sent_node_ids': missing, 'unjoined_events': unjoined,
                                   'duplicate_events_ignored': duplicates, 'registered_pages': list(pages.values()),
                                   'warnings': warnings,
                                   'status_note': 'Tree statuses are evaluator labels, not official incident confirmation.'}}
    return bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tree', type=Path, required=True)
    parser.add_argument('--api-log', type=Path, required=True)
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        tree = json.loads(args.tree.read_text(encoding='utf-8-sig'))
        rows = [json.loads(line) for line in args.api_log.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
        profile = json.loads(args.profile.read_text(encoding='utf-8-sig')) if args.profile else None
        bundle = build_bundle(tree, rows, profile=profile)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(bundle, indent=2), encoding='utf-8')
    except (ValueError, OSError, TypeError):
        parser.exit(1, 'Export failed: check that the selected tree, API log and optional profile belong together.\n')
    print(f"Viewer bundle saved to {args.output}; imported evidence, not authenticated official results.")


if __name__ == '__main__': main()
