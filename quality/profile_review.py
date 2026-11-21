"""Read-only structural evidence checks for Sherwin's shared Profile handoff."""
import math
from urllib.parse import urlsplit
from .checks import QualityReport
from .integration import plain


def review_profile(profile):
    from schemas import FACT_CATEGORIES
    data = plain(profile)
    report = QualityReport()
    if not isinstance(data.get('name'), str) or not data['name'].strip():
        report.errors.append('Profile name missing')
    facts = data.get('facts', [])
    if not isinstance(facts, list):
        report.errors.append('Profile facts must be a list')
        return report
    if not facts:
        report.warnings.append('No facts supplied; structural validity is not completed research evidence')
    for index, fact in enumerate(facts, 1):
        prefix = f'Fact {index}'
        if not isinstance(fact, dict):
            report.errors.append(prefix + ': expected fact object')
            continue
        if fact.get('category') not in FACT_CATEGORIES:
            report.errors.append(prefix + ': unknown shared fact category')
        if not isinstance(fact.get('value'), str) or not fact['value'].strip():
            report.errors.append(prefix + ': fact value missing')
        confidence = fact.get('confidence', 0)
        if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            report.errors.append(prefix + ': confidence must be finite and between 0 and 1')
        if type(fact.get('verified', False)) is not bool:
            report.errors.append(prefix + ': verified flag must be boolean')
        supporting = fact.get('supporting_urls', [])
        if not isinstance(supporting, list):
            report.errors.append(prefix + ': supporting URLs must be a list')
            supporting = []
        hosts = set()
        for url in [fact.get('source_url')] + supporting:
            try:
                if not isinstance(url, str):
                    raise ValueError()
                parsed = urlsplit(url)
                if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
                    raise ValueError()
                hosts.add(parsed.hostname.lower().removeprefix('www.'))
            except ValueError:
                report.errors.append(prefix + ': invalid or missing evidence URL')
        if fact.get('verified') is True and len(hosts) < 2:
            report.warnings.append(prefix + ': marked verified but fewer than two distinct source hosts recorded')
    report.warnings.append('Structural checks do not verify factual truth or source independence; no search or fetch was performed.')
    report.errors = list(dict.fromkeys(report.errors))
    return report
