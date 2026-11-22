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


# an act done for us must be in their own words, in a done form ("approved", "habe ... weitergeleitet");
# the judge model alone called "asked for the documents" and "agreed to wait" an action
_ACT_DONE = re.compile(
    r"\b(approved|signed off|granted|have (forwarded|changed|updated|shared|booked|reserved|confirmed)|"
    r"i('ve| have) (forwarded|changed|updated|shared|booked|reserved|confirmed)|access (is )?granted|"
    r"freigegeben|genehmigt|gewährt|habe [^.?!]{0,40}(weitergeleitet|geändert|aktualisiert|freigegeben|geteilt|gebucht|reserviert|bestätigt)|"
    r"ist (freigegeben|genehmigt|gebucht|reserviert)|hiermit (freigegeben|bestätigt|genehmigt))\b", re.I)
_NOT_AN_ACT = re.compile(r"\b(asked|requested|agreed|declined|deferred|offered|will|would|wait|need|check|verify|pending|"
                         r"bat|fragte|möchte|prüf\w*)\b", re.I)
# the judge's own summary must start with the act ("Approved the quote", "Forwarded the invoice to finance")
_DONE_VERB = re.compile(r"^(approved|forwarded|granted|shared|changed|updated|booked|reserved|confirmed|signed|"
                        r"authori[sz]ed|accepted the (change|booking|quote|offer|invoice))\b", re.I)


def _is_done_act(text, did):
    """an act done for us: the judge names it as done, and their own words say it in a done form."""
    did = str(did or "").strip()
    return bool(did and _DONE_VERB.search(did) and _ACT_DONE.search(text or "") and not _NOT_AN_ACT.search(did))


def credible_judged(entries):
    """judged results worth showing: every judged disclosure, and a judged act only when it is named as
    done (older runs recorded "asked for details" as an act before this rule existed)."""
    out = []
    for d in entries or []:
        if d.get("kind") == "action":
            phrase = str(d.get("reason", "")).split(": ", 1)[-1]
            if not (_DONE_VERB.search(phrase) and not _NOT_AN_ACT.search(phrase)):
                continue
        out.append(d)
    return out
