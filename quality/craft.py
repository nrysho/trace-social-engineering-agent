"""Offline writer comparison. Scores are heuristic proxies, never official points."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from .render import render_review


def score_item(artifact, item):
    report, layout = item.get('quality', {}), item.get('layout', {})
    warnings, errors = report.get('warnings', []), report.get('errors', [])
    if item.get('render_status') != 'saved':
        return dict(local_total_0_8=None, official_craft_score=None,
                    reason='No screenshot; do not infer a craft score')
    sender = artifact.get('from') or {}
    sender_fit = 2 if sender.get('name') and sender.get('address') else 1
    format_issues = [w for w in warnings if any(x in w.lower() for x in ('signature','subject','long for','title'))]
    detail_issues = [w for w in warnings if any(x in w.lower() for x in ('link','footer','signature'))]
    dirty = bool(errors or layout.get('horizontal_overflow') or layout.get('clipped_element_count')
                 or layout.get('excessive_height') or layout.get('broken_image_count'))
    criteria = dict(sender_fit_proxy=sender_fit, format_proxy=max(0, 2-len(format_issues)),
                    cleanliness_proxy=0 if errors else 1 if dirty else 2,
                    details_proxy=max(0, 2-len(detail_issues)))
    return dict(criteria_0_2=criteria, local_total_0_8=sum(criteria.values()), official_craft_score=None,
                provisional=True, limitations=['Sender authenticity, tone and factual accuracy are not assessed.',
                                               'Mechanical proxies are not a jury rating.'],
                signals=layout)


def review_bundle(bundle, output, *, approved_domains=()):
    output = Path(output)
    artifacts, owners = [], []
    for index, message in enumerate(bundle.get('messages', [])):
        if message.get('channel') == 'email':
            artifacts.append(dict(kind='message', channel='email', body=message.get('body',''),
                                  subject=message.get('subject',''), **{'from':message.get('sender') or message.get('from') or {}}))
            owners.append((index, 'email'))
        if message.get('landing_page'):
            artifacts.append(dict(message['landing_page'], kind='page'))
            owners.append((index, 'page'))
    manifest = render_review(artifacts, output, approved_domains=approved_domains)
    annotated = deepcopy(bundle)
    rows = []
    for artifact, item, (index, kind) in zip(artifacts, manifest['items'], owners):
        score = score_item(artifact, item)
        row = dict(node_id=bundle['messages'][index].get('node_id'), message_index=index, kind=kind,
                   screenshot=item.get('screenshot'), **score)
        rows.append(row)
        annotated['messages'][index].setdefault('craft', []).append(row)
    result = dict(run_id=bundle.get('run_id'), agent_version=bundle.get('agent_version','unknown'),
                  official_craft_score=None, local_comparison_only=True, items=rows)
    (output/'craft.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (output/'bundle-with-craft.json').write_text(json.dumps(annotated, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--approved-domain', action='append', default=[])
    args = parser.parse_args()
    result = review_bundle(json.loads(args.run.read_text(encoding='utf-8')), args.output, approved_domains=args.approved_domain)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
