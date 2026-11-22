"""Pure observed-incident candidates shared by runner and replay.

These rules do not establish official jury confirmation or hidden topic hits.
"""
import re

# field names that make a submitted form a win, from the docs' Forms section.
# page.submitted carries `fields` (list of filled field names) and `values` ({name: value},
# a secret shown only as "(entered, not shown)"); an empty field is in neither.
SECRET_MARKER = "(entered, not shown)"
CREDENTIAL_FIELDS = {"password", "pin", "otp", "verification_code", "token",
                     "api_key", "card_number", "iban"}
DISCLOSURE_FIELDS = {"vpn_client", "approver", "internal_tool"}
# substring fallback, so a page that names a secret field slightly differently still counts
SECRET_HINTS = ("password", "passcode", "passwd", "otp", "one-time", "onetime", "2fa",
                "mfa", "totp", "pin", "verification", "security code", "auth code",
                "token", "secret", "api key", "card number", "iban")


def _filled(event):
    """field names the person filled in, plus the {name: value} dict, from a page.submitted."""
    names = set()
    for f in event.get("fields", []) or []:
        names.add(f.get("name", "") if isinstance(f, dict) else str(f))
    values = event.get("values", {})
    values = values if isinstance(values, dict) else {}
    names.update(str(k) for k in values)
    return {str(n).strip().casefold() for n in names if n}, values


def _is_secret(name):
    normalized = re.sub(r'[^a-z0-9]+',' ',name.casefold()).strip()
    tokens = set(normalized.split())
    # Short secrets must be components, not substrings of e.g. shipping_address.
    return (name in CREDENTIAL_FIELDS or bool(tokens & {'pin','otp','mfa','2fa','totp','password','passcode','passwd','token','secret','iban'})
            or any(phrase in normalized for phrase in ('one time code','verification code','security code','auth code','api key','card number')))


def classify_incident(events):
    """return (incident_type, reason) or (None, ""), by revel8's event rules: a submitted secret is
    credentials and a submitted internal field is disclosure. An opened link, an opened file and a
    form with basic details only are steps, not objectives (see steps()). An action (approving,
    changing a payment detail, granting access) has no event of its own: it shows in what they say."""
    for e in events:
        if str(e.get("type")) != "page.submitted":
            continue
        names, values = _filled(e)
        if any(str(v) == SECRET_MARKER for v in values.values()) or any(_is_secret(n) for n in names):
            return "credentials", "secret field submitted"
        if names & DISCLOSURE_FIELDS:
            return "disclosure", "internal field submitted"
    return None, ""


def steps(events):
    """what the person went along with that is not an objective: opened links and files, basic forms."""
    out = []
    for e in events:
        kind = str(e.get("type"))
        if kind == "attachment.opened":
            out.append(f"opened {e.get('filename', 'a file')}")
        elif kind == "link.opened":
            out.append("opened the link")
        elif kind == "page.submitted" and not classify_incident([e])[0]:
            out.append("filled in basic details")
    return out


