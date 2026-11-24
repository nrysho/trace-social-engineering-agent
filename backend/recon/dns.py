"""dns signals: mail provider and saas vendors from a company domain.

- mx records -> the mail provider (google workspace, microsoft 365) for a login pretext
- spf include: entries -> saas vendors the company uses, each its own pretext lead
- queried over dns-over-https, so no extra dependency; facts are authoritative
"""
import requests

from core.schemas import Fact

DOH = "https://dns.google/resolve"
TIMEOUT = 15

# spf include hosts -> the vendor behind them. extend as we see more.
SPF_VENDORS = {
    "google.com": "Google Workspace",
    "outlook.com": "Microsoft 365",
    "protection.outlook.com": "Microsoft 365",
    "sendgrid.net": "SendGrid",
    "mailgun.org": "Mailgun",
    "amazonses.com": "Amazon SES",
    "salesforce.com": "Salesforce",
    "zendesk.com": "Zendesk",
    "mktomail.com": "Marketo",
    "hubspotemail.net": "HubSpot",
    "pphosted.com": "Proofpoint",
    "mimecast.com": "Mimecast",
    "mandrillapp.com": "Mailchimp (Mandrill)",
    "servers.mcsv.net": "Mailchimp",
    "zoho.com": "Zoho",
    "qualtrics.com": "Qualtrics",
}


def _source(domain, rtype):
    # a real, clickable url that shows the same record we read
    return f"https://dns.google/resolve?name={domain}&type={rtype}"


def _answers(domain, rtype):
    r = requests.get(DOH, params={"name": domain, "type": rtype}, timeout=TIMEOUT)
    r.raise_for_status()
    return [a.get("data", "") for a in r.json().get("Answer", [])]


def facts(domain):
    # a fact for the mail provider, plus one per saas vendor found in spf
    out = []
    mx = " ".join(_answers(domain, "MX")).lower()
    provider = ("Google Workspace" if "google" in mx else
                "Microsoft 365" if ("outlook" in mx or "microsoft" in mx) else None)
    if provider:
        out.append(Fact(
            category="vendors_and_tools",
            value=f"{domain} uses {provider} for email",
            source_url=_source(domain, "MX"),
            source_title=f"MX records for {domain}",
            confidence=0.95,
            verified=True,  # authoritative dns, directly checkable
        ))
    seen = set()
    for rec in _answers(domain, "TXT"):
        rec = rec.strip('"')
        if not rec.lower().startswith("v=spf1"):
            continue
        for token in rec.split():
            if not token.startswith("include:"):
                continue
            host = token.split(":", 1)[1]
            for key, name in SPF_VENDORS.items():
                if key in host and name not in seen and name != provider:
                    seen.add(name)
                    out.append(Fact(
                        category="vendors_and_tools",
                        value=f"{domain} sends mail via {name} (spf include)",
                        source_url=_source(domain, "TXT"),
                        source_title=f"SPF record for {domain}",
                        confidence=0.85,
                        verified=True,
                    ))
    return out
