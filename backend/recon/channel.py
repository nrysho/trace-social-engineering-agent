"""infer the target's likely contact channel from public signals.

- an explicit stated preference in the facts ("reach me on telegram") wins
- otherwise the platform the target actually posts on maps to its dm channel
- defaults to email, the one channel almost everyone reads
- this is a pre-contact best guess; the evaluator overwrites it once the target
  states a real preference in a session (e.g. "ping me on slack")
- values are revel8 channel ids, so the strategist can use the result directly
"""
from urllib.parse import urlsplit

from backend.recon import recency

# a platform the target is active on -> the channel to reach them there
PLATFORM_CHANNEL = [
    ("linkedin.", "linkedin_message"),
    ("x.com", "x_dm"),
    ("twitter.", "x_dm"),
    ("instagram.", "instagram_dm"),
    ("t.me", "telegram"),
    ("facebook.", "facebook_messenger"),
]
# an explicit "contact me on ..." phrase -> channel; worth far more than mere activity
KEYWORD_CHANNEL = [
    ("telegram", "telegram"), ("signal", "signal"), ("whatsapp", "whatsapp"),
    ("slack", "slack"), ("linkedin", "linkedin_message"), ("twitter", "x_dm"),
    ("e-mail", "email"), ("email", "email"),
]
INTENT = ("prefer", "reach me", "reach out", "contact me", "dm me", "message me", "ping me")
# categories that reflect the target's own activity, not press coverage about them
ACTIVE_CATS = ("recent_activity", "communication_style", "media", "interests")
DEFAULT = "email"
EXPLICIT_WEIGHT = 3.0  # a stated preference outweighs a few activity signals


def _host(url):
    return urlsplit(url).netloc.lower()


def infer(facts):
    # tally channel votes: stated preferences heavily, platform activity lightly
    votes = {}
    for f in facts:
        text = f.value.lower()
        w = recency.weight(f.date)
        if any(p in text for p in INTENT):  # the fact states how to reach them
            for kw, ch in KEYWORD_CHANNEL:
                if kw in text:
                    votes[ch] = votes.get(ch, 0) + EXPLICIT_WEIGHT * w
                    break
        if f.category in ACTIVE_CATS:  # they are active on this platform
            host = _host(f.source_url)
            for sub, ch in PLATFORM_CHANNEL:
                if sub in host:
                    votes[ch] = votes.get(ch, 0) + w
                    break
    if not votes:
        return DEFAULT
    return max(votes, key=votes.get)
