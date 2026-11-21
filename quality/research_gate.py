"""Research readiness, not an assertion that supplied sources prove truth."""
import unicodedata
from urllib.parse import urlsplit
from .checks import QualityReport


def sourced_verified_facts(facts):
    if not isinstance(facts, list):
        return []
    result = []
    for fact in facts:
        if (not isinstance(fact, dict) or fact.get('verified') is not True or
                not isinstance(fact.get('value'), str) or not fact['value'].strip() or
                not isinstance(fact.get('source_url'), str)):
            continue
        try:
            url = urlsplit(fact.get('source_url', ''))
            if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password:
                continue
        except (TypeError, ValueError):
            continue
        result.append(fact)
    return result


def research_readiness(profile, target_id, target_name):
    report = QualityReport()
    def name(value):
        return ' '.join(unicodedata.normalize('NFKC', str(value or '')).casefold().split())
    if not isinstance(profile, dict):
        return QualityReport(errors=['Research profile must be an object'])
    if name(profile.get('name')) != name(target_name):
        report.errors.append('Research profile name differs from the official scenario target')
    if profile.get('target_id', target_id) != target_id:
        report.errors.append('Research profile target ID differs from the selected target')
    if not sourced_verified_facts(profile.get('facts')):
        report.errors.append('No verified facts with usable source URLs; stop and repair recon before contacting the target')
    report.warnings.append('Source metadata and verified flags are supplied evidence, not automatic proof of truth')
    return report
