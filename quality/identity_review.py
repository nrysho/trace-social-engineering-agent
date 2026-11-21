"""Review supplied identity evidence without searching or contacting anyone.

Supported match means reviewed evidence is consistent with a supplied profile,
not proof of existence, employment, ownership or source independence.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from .checks import normalized
from .claim_evidence import utc_time
from .identity import check_target
from .integration import plain, QualityBlocked


class IdentityReviewer:
    def __init__(self, scenarios, profiles, sources, records, *, clock=None, max_age_days=30, scenario_id='practice'):
        if scenario_id not in {'practice','eval'}:
            raise ValueError('Identity review requires an explicit supported scenario')
        self.scenario_id = scenario_id
        if not isinstance(profiles, dict) or not isinstance(sources, list) or not isinstance(records, list):
            raise ValueError('Explicit profiles, source snapshots and identity records required')
        if type(max_age_days) is not int or max_age_days < 1:
            raise ValueError('Positive source freshness policy required')
        self.scenarios, self.profiles, self.records = deepcopy((scenarios, profiles, records))
        self.sources = {}
        for source in deepcopy(sources):
            sid = source.get('source_id') if isinstance(source, dict) else None
            if not isinstance(sid, str) or not sid or sid in self.sources:
                raise ValueError('Unique nonempty source IDs required')
            self.sources[sid] = source
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.max_age = timedelta(days=max_age_days)

    def assess(self, target_id):
        errors, matches, uncertain, contradictions = [], set(), set(), []
        profile = plain(self.profiles.get(target_id, {}))
        try:
            authority = check_target(self.scenarios, target_id, scenario_id=self.scenario_id)
        except QualityBlocked as exc:
            authority = dict(passed=False, errors=exc.report.errors)
        errors.extend(authority['errors'])
        name, company = profile.get('name'), profile.get('company')
        official_name = (authority.get('target') or {}).get('name')
        if official_name and normalized(name or '').casefold() != normalized(official_name).casefold():
            errors.append('Profile name differs from the official target; aliases are not inferred')
        if not isinstance(name, str) or len(name.split()) < 2 or not isinstance(company, str) or not company.strip():
            errors.append('Full name and company anchor required; first-name matching is insufficient')
        valid_sources = []
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError('Identity clock must be timezone-aware')
        for record in self.records:
            if not isinstance(record, dict) or record.get('target_id') != target_id:
                continue
            candidate, status = record.get('candidate_id'), record.get('review_status')
            if not isinstance(candidate, str) or not candidate:
                errors.append('Identity record lacks public candidate ID')
                continue
            supports = record.get('supports')
            if not isinstance(supports, list) or not supports:
                uncertain.add(candidate)
                continue
            supported = True
            urls = []
            for support in supports:
                sid = support.get('source_id') if isinstance(support, dict) else None
                source = self.sources.get(sid) if isinstance(sid, str) else None
                try:
                    if source is None:
                        raise ValueError('Missing source snapshot')
                    parsed = urlsplit(source.get('url', ''))
                    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
                        raise ValueError('Invalid public source URL')
                    fetched = utc_time(source.get('retrieved_at'))
                    if fetched > now or now - fetched > self.max_age:
                        raise ValueError('Stale or future source retrieval time')
                    quote, text = support.get('quote'), source.get('text')
                    if not isinstance(quote, str) or not quote.strip() or not isinstance(text, str) or normalized(quote) not in normalized(text):
                        raise ValueError('Excerpt not found in source snapshot')
                    # Co-occurrence is a linkage requirement, never semantic proof.
                    anchors = [record.get('name'), record.get('company')]
                    if record.get('role'):
                        anchors.append(record['role'])
                    for anchor in anchors:
                        if not isinstance(anchor, str) or not anchor or normalized(anchor).casefold() not in normalized(quote).casefold():
                            raise ValueError('Full-name/company anchor absent from excerpt')
                    urls.append(source['url'])
                except (TypeError, ValueError):
                    supported = False
            if not supported:
                uncertain.add(candidate)
                continue
            if status == 'conflicting':
                contradictions.append(candidate)
            elif (status == 'supported' and normalized(record.get('name', '')).casefold() == normalized(name or '').casefold()
                  and normalized(record.get('company', '')).casefold() == normalized(company or '').casefold()
                  and (not profile.get('role') or normalized(record.get('role', '')).casefold() == normalized(profile['role']).casefold())):
                matches.add(candidate)
                valid_sources.extend(urls)
            elif status != 'different_person':
                uncertain.add(candidate)
        state = ('conflicting' if contradictions or errors else 'ambiguous' if len(matches) > 1 or uncertain
                 else 'supported_match' if len(matches) == 1 else 'insufficient_evidence')
        return dict(passed=authority['passed'] and state == 'supported_match', status=state,
                    authorised_target=authority['passed'], target_id=target_id,
                    matching_candidate_ids=sorted(matches), unresolved_candidate_ids=sorted(uncertain),
                    source_urls=sorted(set(valid_sources)), errors=errors,
                    public_identity_verified=None, person_exists=None,
                    warning='Supplied reviewed evidence only. A supported match is not proof; no matches never mean the person does not exist.')
