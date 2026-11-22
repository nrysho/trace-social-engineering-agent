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
                    report.warnings.append(detail)  # heuristic story check: logged, never blocks a contact
                else:
                    report.warnings.append(detail)
        return report

    def commit(self, sid, story_id, text, declarations=None):
        fields = declared_details(text)
        fields.update(declarations or {})
        self.values.setdefault((sid, story_id), {}).update(fields)


def profile_claim_checks(text, facts):
    report = QualityReport()
    if not isinstance(text,str):
        report.errors.append('Body must be text')
        return report
    if not isinstance(facts, list):
        report.errors.append('Profile facts must be a list')
        return report
    report.warnings.extend(operational_claim_checks(text, facts))  # heuristic: logged, never blocks
    text = normalized(re.sub(r'<[^>]*>', ' ', text)).casefold()
    from .research_gate import sourced_verified_facts
    supported_spans = []
    for verified in sourced_verified_facts(facts):
        claim = normalized(verified['value']).casefold().strip(' .')
        if claim:
            supported_spans.extend((m.start(),m.end()) for m in re.finditer(re.escape(claim),text))
    for fact in facts:
        if not isinstance(fact, dict) or not isinstance(fact.get('value'), str):
            continue
        value = normalized(fact['value']).casefold()
        if not value or value not in text:
            continue
        if fact.get('verified') is not True:
            # A company label alone is an entity mention, not an assertion of
            # employment, tools or another attribute. Do not block every message
            # containing the company name because recon supplied such a row.
            if fact.get('category') == 'company' and not re.search(
                    r'\b(is|are|uses?|using|has|have|employs?|works?|based|founded|raised|acquired)\b',value):
                continue
            for mention in re.finditer(r'(?<!\w)'+re.escape(value)+r'(?!\w)',text):
                if any(start <= mention.start() and mention.end() <= end for start,end in supported_spans):
                    continue
                prefix = text[max(0, mention.start()-50):mention.start()]
                if re.search(r'\b(if|might|may|perhaps|unconfirmed|possibly)\b', prefix):
                    report.warnings.append('Tentative use of an unverified profile fact')
                else:
                    report.warnings.append('Unverified profile fact stated as certain')  # heuristic: logged, never blocks
        elif not fact.get('source_url'):
            report.warnings.append('Verified flag lacks a source URL')
    if re.search(r"\byou(?: are|'re| recently)|\byour company\b", text):
        report.warnings.append('Inspect target assertions against verified profile facts; automatic extraction is incomplete')
    return report


def operational_claim_checks(text, facts):
    """Conservative operational-claim patterns, not general semantic fact checking.

    A matching assertion must reproduce a supplied verified/sourced claim.
    Rephrasing it as a neutral question is also permitted. Unrelated evidence
    cannot license a new claim about tools or systems. English/German coverage
    is deliberately limited; the optional reviewed sidecar is the stronger layer.
    """
    from .research_gate import sourced_verified_facts
    english = (r"\b(?:your (?:team|company|organisation|organization)|you(?:'re)?)\s+"
               r"(?:(?:already|currently|recently|still|heavily|typically)\s+)*"
               r"(?:(?:are|were|have|has)\s+)?"
               r"(?:use[sd]?|using|rel(?:y|ies)|depend[sd]?|run|running|switched|migrated|adopted|implemented)\b[^.!?;\n]*")
    german = r'\b(?:ihr (?:team|unternehmen)|sie)\s+(?:nutzen|nutzt|verwenden|verwendet|benutzen|benutzt|setzen|setzt)\b[^.!?;\n]*'
    def canonical(value):
        value = normalized(re.sub(r'<[^>]*>', ' ', value)).casefold().strip(' .!?;\n')
        value = re.sub(r"^(?:your (?:team|company|organisation|organization)|you|the company|company|team|they|ihr team|ihr unternehmen|sie)\s+", 'target ', value)
        return ' '.join(value.split())
    supported = {canonical(f['value']) for f in sourced_verified_facts(facts)}
    raw = re.sub(r'<(?:br\s*/?|/p|/div)>', '\n', text, flags=re.I)
    raw = re.sub(r'<[^>]*>', ' ', raw)
    for sentence in re.split(r'[.!?;\n]+', raw):
        sentence = normalized(sentence).casefold()
        if re.match(r'^\s*(?:do|does|did|could|can|would|which|what|how|whether|nutzen sie|verwenden sie|benutzen sie|k[oö]nnten sie)\b', sentence):
            continue
        for claim in re.findall(english, sentence) + re.findall(german, sentence):
            if canonical(claim) not in supported:
                return ['Unsupported operational assertion about the target; use an exact verified sourced fact or ask a neutral question']
    return []
