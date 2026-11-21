"""Offline evidence linkage, not web search or semantic truth verification."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from .checks import QualityReport, normalized
from .integration import plain


def utc_time(value):
    if not isinstance(value, str):
        raise ValueError('Explicit timezone-aware retrieval timestamp required')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timestamp needs a timezone')
    return result.astimezone(timezone.utc)


class EvidenceCatalog:
    """Owned by recon/review code, never populated from writer-supplied evidence.

    A supported status is an upstream review assertion, not a conclusion made by
    this class. Quotes must occur in retained source text. All text is inert data.
    """
    def __init__(self, sources, claims, *, max_age_days=30, clock=None):
        if type(max_age_days) is not int or max_age_days < 1:
            raise ValueError('Positive evidence freshness policy required')
        self.max_age = timedelta(days=max_age_days)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sources = self._index(sources, 'source_id')
        self.claims = self._index(claims, 'claim_id')

    @staticmethod
    def _index(records, key):
        if not isinstance(records, list):
            raise ValueError('Evidence records must be a list')
        result = {}
        for record in deepcopy(records):
            if not isinstance(record, dict) or not isinstance(record.get(key), str) or not record[key].strip():
                raise ValueError(f'Nonempty {key} required')
            if record[key] in result:
                raise ValueError(f'Duplicate {key}')
            result[record[key]] = record
        return result

    def review(self, target_id, content, claim_ids):
        report = QualityReport(warnings=[
            'Checks declared claims and evidence linkage only; not semantic truth, source independence, or completeness of claim extraction.'
        ])
        if not isinstance(claim_ids, list) or any(not isinstance(x, str) for x in claim_ids):
            report.errors.append('claim_ids must be a list of catalogue IDs')
            return report
        text = normalized(content)
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError('Evidence clock must be timezone-aware')
        for cid in dict.fromkeys(claim_ids):
            claim = self.claims.get(cid)
            if claim is None:
                report.errors.append(f'{cid}: unknown claim')
                continue
            if claim.get('target_id') != target_id:
                report.errors.append(f'{cid}: evidence belongs to a different target')
            if claim.get('review_status') != 'supported':
                report.errors.append(f'{cid}: claim is not reviewed as supported')
            wording = claim.get('text')
            if not isinstance(wording, str) or not wording.strip() or normalized(wording) not in text:
                report.errors.append(f'{cid}: approved wording absent; paraphrases require separate review')
            key, value = claim.get('fact_key'), claim.get('fact_value')
            if not isinstance(key, str) or not key or not isinstance(value, str) or not value:
                report.errors.append(f'{cid}: fact key/value missing')
            elif any(other.get('target_id') == target_id and other.get('fact_key') == key
                     and other.get('review_status') in {'supported', 'conflicted'}
                     and normalized(other.get('fact_value', '')) != normalized(value)
                     for other in self.claims.values()):
                report.errors.append(f'{cid}: unresolved conflicting evidence for {key}')
            supports = claim.get('supports')
            if not isinstance(supports, list) or not supports:
                report.errors.append(f'{cid}: supporting excerpts missing')
                continue
            for support in supports:
                if not isinstance(support, dict):
                    report.errors.append(f'{cid}: malformed support')
                    continue
                source_id = support.get('source_id')
                source = self.sources.get(source_id) if isinstance(source_id, str) else None
                if source is None:
                    report.errors.append(f'{cid}: unknown source')
                    continue
                try:
                    url = urlsplit(source.get('url', ''))
                    if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password:
                        raise ValueError('Bad evidence URL')
                    fetched = utc_time(source.get('retrieved_at'))
                    if fetched > now or now - fetched > self.max_age:
                        raise ValueError('Evidence retrieval timestamp is future or stale')
                except (TypeError, ValueError) as exc:
                    report.errors.append(f'{cid}: invalid source metadata ({exc})')
                quote = support.get('quote')
                if (not isinstance(quote, str) or not quote.strip()
                        or not isinstance(source.get('text'), str)
                        or normalized(quote) not in normalized(source['text'])):
                    report.errors.append(f'{cid}: supporting excerpt absent from retained source')
        return report


def profile_claim_candidates(profile, target_id):
    """Accept main and recon-osint Fact.date without changing shared schemas.

    generated_at and activity date are NOT source retrieval dates. Candidates
    remain blocked until source snapshots and review are supplied separately.
    """
    data = plain(profile)
    return [dict(claim_id=f'fact-{index}', target_id=target_id,
                 text=fact.get('value', ''), fact_key=fact.get('category', ''),
                 fact_value=fact.get('value', ''), source_url=fact.get('source_url'),
                 activity_date=fact.get('date', ''), review_status='needs_review', supports=[])
            for index, fact in enumerate(data.get('facts', []), 1) if isinstance(fact, dict)]
