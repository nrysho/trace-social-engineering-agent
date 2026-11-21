"""Conservative story heuristics; no semantic truth or complete extraction claim."""
import re
from .checks import QualityReport, normalized


def declared_details(text):
    text = normalized(re.sub(r'<[^>]*>', ' ', text)).casefold()
    result = {}
    dates = set(re.findall(r'\b(?:20\d{2}-\d{2}-\d{2}|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b', text))
    if len(dates) == 1:
        result['date'] = next(iter(dates))
    times = set()
    for m in re.finditer(r'\b(\d{1,2}(?::\d{2})?)\s*(am|pm)?\s*[-\u2013\u2014]\s*(\d{1,2}(?::\d{2})?)\s*(am|pm)\b', text):
        times.add(f'{m[1]}{m[2] or m[4]}-{m[3]}{m[4]}')
    if len(times) == 1:
        result['time'] = next(iter(times))
    counts = set(re.findall(r'\b(\d+)\s+(?:students|attendees|participants|guests|people)\b', text))
    if len(counts) == 1:
        result['audience_count'] = next(iter(counts))
    return result


class StoryLedger:
    def __init__(self):
        self.values = {}

    def review(self, sid, story_id, text, declarations=None):
        report = QualityReport()
        fields = declared_details(text)
        fields.update(declarations or {})
        old = self.values.get((sid, story_id), {})
        for key, value in fields.items():
            if key in old and old[key] != value:
                detail = 'Story contradiction: ' + key
                if any(word in key.casefold() for word in ('date', 'time')):
                    report.errors.append(detail)
                else:
                    report.warnings.append(detail)
        return report

    def commit(self, sid, story_id, text, declarations=None):
        fields = declared_details(text)
        fields.update(declarations or {})
        self.values.setdefault((sid, story_id), {}).update(fields)


def profile_claim_checks(text, facts):
    report = QualityReport()
    text = normalized(re.sub(r'<[^>]*>', ' ', text)).casefold()
    for fact in facts:
        if not isinstance(fact, dict) or not isinstance(fact.get('value'), str):
            continue
        value = normalized(fact['value']).casefold()
        if not value or value not in text:
            continue
        if fact.get('verified') is not True:
            prefix = text[max(0, text.index(value)-50):text.index(value)]
            if re.search(r'\b(if|might|may|perhaps|unconfirmed|possibly)\b', prefix):
                report.warnings.append('Tentative use of an unverified profile fact')
            else:
                report.errors.append('Unverified profile fact stated as certain')
        elif not fact.get('source_url'):
            report.warnings.append('Verified flag lacks a source URL')
    if re.search(r"\byou(?: are|'re| recently)|\byour company\b", text):
        report.warnings.append('Inspect target assertions against verified profile facts; automatic extraction is incomplete')
    return report
