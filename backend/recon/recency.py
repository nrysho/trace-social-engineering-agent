"""how fresh a fact is, from its date string.

- "present"/"current" -> 1.0; empty/unknown -> a neutral middle (undated facts)
- a parsed YYYY or YYYY-MM decays linearly from 1.0 (now) to a floor over ~3 years
- used to pick the current role, weight hooks, and score exposure recency
"""
import re
from datetime import datetime, timezone

DECAY_MONTHS = 36  # a fact this old is treated as least relevant (hits the floor)
FLOOR = 0.15       # very old facts still count a little
NEUTRAL = 0.5      # undated facts (interests, skills) sit in the middle


def _months_ago(date_str, now):
    m = re.search(r"(\d{4})(?:-(\d{1,2}))?", date_str)
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2)) if m.group(2) else 6  # mid-year if only a year
    return (now.year - year) * 12 + (now.month - month)


def weight(date_str, now=None):
    now = now or datetime.now(timezone.utc)
    d = (date_str or "").strip().lower()
    if d in ("present", "current", "now", "ongoing"):
        return 1.0
    months = _months_ago(d, now)
    if months is None:  # undated or unparseable
        return NEUTRAL
    if months <= 0:
        return 1.0
    frac = min(months / DECAY_MONTHS, 1.0)  # linear decay to the floor
    return round(1.0 - frac * (1.0 - FLOOR), 3)
