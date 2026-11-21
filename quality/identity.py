"""Separate simulator eligibility from public-name mentions. No search or sending."""
from copy import deepcopy
from datetime import datetime, timezone
import re
import unicodedata
from urllib.parse import urlsplit
from .checks import QualityReport
from .integration import QualityBlocked, validate_context


def _name(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split()) if isinstance(value, str) else ''


def scenario_metadata(scenarios, scenario_id='practice'):
    if scenario_id not in {'practice','eval'}:
        raise ValueError('Explicit practice or eval scenario required')
    if not isinstance(scenarios, list):
        raise QualityBlocked(QualityReport(errors=['Scenario response must be a list']))
    practice = [s for s in scenarios if isinstance(s, dict) and s.get('id') == scenario_id]
    if len(practice) != 1 or practice[0].get('open') is not True:
        raise QualityBlocked(QualityReport(errors=['Exactly one explicitly open selected scenario is required']))
    scenario = deepcopy(practice[0])
    targets = scenario.get('targets')
    if not isinstance(targets, list) or not targets:
        raise QualityBlocked(QualityReport(errors=['Practice scenario has no valid target list']))
    ids = []
    for target in targets:
        if not isinstance(target, dict) or not all(isinstance(target.get(k), str) and target[k].strip() for k in ('id', 'name')):
            raise QualityBlocked(QualityReport(errors=['Practice targets need nonempty ID and name fields']))
        ids.append(target['id'])
    if len(ids) != len(set(ids)):
        raise QualityBlocked(QualityReport(errors=['Duplicate target IDs in practice scenario']))
    return scenario


def practice_scenario(scenarios):
    return scenario_metadata(scenarios, 'practice')


def check_target(scenarios, target_id, *, expected_name=None, expected_company=None, scenario_id='practice'):
    scenario = scenario_metadata(scenarios, scenario_id)
    target = next((t for t in scenario['targets'] if t['id'] == target_id), None)
    errors = []
    if target is None:
        errors.append('Target ID is not listed by the supplied selected scenario')
    if expected_name is not None and (not _name(expected_name) or not target or _name(target['name']) != _name(expected_name)):
        errors.append('Selected profile name does not match the scenario target; do not infer aliases')
    if expected_company is not None and (not _name(expected_company) or _name(scenario.get('company')) != _name(expected_company)):
        errors.append('Selected profile company does not match scenario metadata')
    return {'passed': not errors, 'scenario': scenario_id, 'target': target, 'errors': errors,
            'source_scope': 'Supplied scenario response; authentic API retrieval belongs to the caller.',
            'public_identity_verified': None}


def context_from_practice(scenarios, context):
    """Replace hand-entered target IDs; never auto-approve sender/link domains."""
    validate_context(context)
    scenario = practice_scenario(scenarios)
    result = deepcopy(context)
    result['scenario_id'] = 'practice'
    result['authorized_targets'] = [t['id'] for t in scenario['targets']]
    result['target_snapshot'] = {'scenario': 'practice', 'company': scenario.get('company'),
                                 'targets': scenario['targets'],
                                 'recorded_at': datetime.now(timezone.utc).isoformat()}
    return result


def public_name_mentions(full_name, sources):
    """Inspect already collected public page text, not search results as proof.

    A full-name mention is not identity/role verification. Negative mentions,
    duplicated sources and same-name people require separate evidence review.
    """
    if not isinstance(full_name, str) or len(full_name.split()) < 2 or not isinstance(sources, list):
        raise ValueError('Provide a full name and source list')
    wanted = _name(full_name)
    matches, seen = [], set()
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get('text'), str):
            raise ValueError('Each source needs a URL and page text')
        url = source.get('url')
        if not isinstance(url, str):
            raise ValueError('Public source URL missing')
        parsed = urlsplit(url)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Public source URL must be an HTTP(S) page')
        if re.search(r'(?<!\w)' + re.escape(wanted) + r'(?!\w)', _name(source['text'])):
            key = (parsed.hostname.lower(), parsed.path.rstrip('/'), parsed.query)
            if key not in seen:
                matches.append({'url': url, 'full_name_mention': True})
                seen.add(key)
    return {'full_name': full_name, 'matching_sources': matches, 'mention_found': bool(matches),
            'public_identity_verified': None,
            'warning': 'Name mentions do not prove identity, employment, freshness or independent corroboration. No matches do not prove nonexistence.'}
