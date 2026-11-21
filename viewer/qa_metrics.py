"""QA/craft additions to the existing viewer; no incident/touch calculations."""
from collections import Counter


def quality_summary(bundle):
    candidates, missing = {}, set()
    for kind, records in [('node',bundle.get('nodes',[])),('message',bundle.get('messages',[]))]:
        for index, record in enumerate(records):
            if kind == 'node' and record.get('level') not in {'contact','attempt'}:
                continue
            identity = record.get('node_id') if kind == 'message' else record.get('id')
            identity = identity or f'{kind}:{index}'
            qa = record.get('qa')
            if not isinstance(qa,dict) or type(qa.get('passed')) is not bool or any(
                    not isinstance(qa.get(key,[]),list) or any(not isinstance(v,str) for v in qa.get(key,[]))
                    for key in ('errors','warnings')):
                missing.add(identity)
                continue
            candidates.setdefault(identity,[]).append(qa)
    checked = blocked = warnings = bypassed = conflicts = 0
    reasons = Counter()
    for identity, reports in candidates.items():
        missing.discard(identity)
        if any(r != reports[0] for r in reports[1:]):
            conflicts += 1
            continue
        report = reports[0]
        if report.get('bypassed') is True:
            bypassed += 1
            continue
        checked += 1
        blocked += int(not report['passed'])
        warnings += int(bool(report.get('warnings')))
        reasons.update(set(report.get('errors',[])+report.get('warnings',[])))
    craft = [row for message in bundle.get('messages',[]) for row in message.get('craft',[])]
    scores = [row['local_total_0_8'] for row in craft if type(row.get('local_total_0_8')) is int and 0 <= row['local_total_0_8'] <= 8]
    return dict(checked=checked,blocked=blocked,warnings=warnings,bypassed=bypassed,
                missing_verdicts=len(missing),conflicting_verdicts=conflicts,
                blocked_percent=100*blocked/checked if checked else None,
                warning_percent=100*warnings/checked if checked else None,
                top_reasons=[dict(reason=reason,count=count) for reason,count in reasons.most_common(10)],
                local_craft_mean_0_8=sum(scores)/len(scores) if scores else None,
                craft_scored_items=len(scores),official_craft_score=None)


def by_version(bundles):
    groups = {}
    for bundle in bundles:
        version = str(bundle.get('agent_version') or (bundle.get('metrics') or {}).get('label') or 'unknown')
        groups.setdefault(version,[]).append(quality_summary(bundle))
    output = {}
    for version, runs in groups.items():
        counts = {key:sum(run[key] for run in runs) for key in ('checked','blocked','warnings','bypassed','missing_verdicts','conflicting_verdicts','craft_scored_items')}
        reasons = Counter()
        for run in runs:
            reasons.update({row['reason']:row['count'] for row in run['top_reasons']})
        checked, scored = counts['checked'], counts['craft_scored_items']
        output[version] = dict(counts, runs=len(runs),
            blocked_percent=100*counts['blocked']/checked if checked else None,
            warning_percent=100*counts['warnings']/checked if checked else None,
            top_reasons=[dict(reason=reason,count=count) for reason,count in reasons.most_common(10)],
            local_craft_mean_0_8=sum((run['local_craft_mean_0_8'] or 0)*run['craft_scored_items'] for run in runs)/scored if scored else None,
            official_craft_score=None)
    return output
