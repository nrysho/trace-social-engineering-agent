"""Bounded correction of complete message + review candidates. Never sends."""
from copy import deepcopy

from .checks import QualityReport
from .integration import checked_message, plain, QualityBlocked


def generate_reviewed(writer, guard, *, max_attempts=3, audit=None):
    if type(max_attempts) is not int or not 1 <= max_attempts <= 10:
        raise ValueError('max_attempts must be between 1 and 10')
    feedback, attempts = None, []
    for attempt in range(1, max_attempts + 1):
        candidate = writer(deepcopy(feedback))
        try:
            if not isinstance(candidate, dict) or set(candidate) != {'message', 'review'}:
                raise QualityBlocked(QualityReport(errors=['Writer must return message and review sidecar']))
            message = plain(candidate['message'])
            review = deepcopy(candidate['review'])
            checked_message(message, guard.context)
            report = guard.inspect_review(message, review)
        except QualityBlocked as exc:
            report = exc.report
        feedback = report.to_dict()
        attempts.append(dict(attempt=attempt, report=deepcopy(feedback)))
        if audit:
            audit(deepcopy(attempts[-1]))
        if report.passed:
            return dict(message=message, review=review, attempts=attempts)
    raise QualityBlocked(report)
