"""detect the saas platforms a company uses, from its domain.

- dns txt verification tokens leak tools that once asked for a verification record
- a microsoft 365 realm check says definitively whether the tenant is on m365
- the homepage scripts and widgets reveal analytics, chat, payment and cms tools
each becomes a vendors_and_tools fact (a pretext lead); probes are authoritative.
"""
import re

import requests

from schemas import Fact

DOH = "https://dns.google/resolve"
TIMEOUT = 15
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

# a dns txt verification token (substring) -> the tool that asked for it
TXT_TOKENS = {
    "google-site-verification": "Google Workspace",
    "ms=": "Microsoft 365",
    "ms-domain-verification": "Microsoft 365",
    "docusign": "DocuSign",
    "adobe-idp-site-verification": "Adobe (enterprise SSO)",
    "adobe-sign-verification": "Adobe Sign",
    "atlassian-domain-verification": "Atlassian (Jira/Confluence)",
    "facebook-domain-verification": "Meta Business",
    "stripe-verification": "Stripe",
    "zoom-domain-verification": "Zoom",
    "zoom_verify": "Zoom",
    "dropbox-domain-verification": "Dropbox",
    "box-domain-verification": "Box",
    "miro-verification": "Miro",
    "notion-domain-verification": "Notion",
    "webexdomainverification": "Cisco Webex",
    "citrix-verification-code": "Citrix",
    "mongodb-site-verification": "MongoDB Atlas",
    "slack-domain-verification": "Slack",
    "canva-site-verification": "Canva",
    "workplace-domain-verification": "Meta Workplace",
    "asana-domain-verification": "Asana",
    "calendly": "Calendly",
    "zendeskverification": "Zendesk",
    "pardot": "Salesforce Pardot",
    "hubspot-developer-verification": "HubSpot",
    "status-page-domain-verification": "Atlassian Statuspage",
    "segment-site-verification": "Twilio Segment",
    "twilio-domain-verification": "Twilio",
    "klaviyo-site-verification": "Klaviyo",
    "shopify": "Shopify",
    "wix-domain-verification": "Wix",
    "openai-domain-verification": "OpenAI",
    "postman-domain-verification": "Postman",
    "figma-domain-verification": "Figma",
    "github-domain-verification": "GitHub",
    "okta-verification": "Okta",
    "onelogin": "OneLogin",
    "duo-verification": "Cisco Duo",
    "ping-identity": "Ping Identity",
    "workday": "Workday",
    "servicenow": "ServiceNow",
    "datadog": "Datadog",
    "sentry": "Sentry",
    "loom-verification": "Loom",
    "airtable": "Airtable",
    "1password-site-verification": "1Password",
    "atlassian-sending-domain-verification": "Atlassian",
}

# a substring in the homepage html -> the tool it belongs to
WEB_SIGNS = {
    "widget.intercom": "Intercom",
    "js.hs-scripts": "HubSpot",
    "js.hsforms": "HubSpot",
    "cdn.segment.com": "Twilio Segment",
    "googletagmanager.com": "Google Tag Manager",
    "google-analytics.com": "Google Analytics",
    "js.stripe.com": "Stripe",
    "js.driftt": "Drift",
    "static.zdassets": "Zendesk",
    "assets.calendly": "Calendly",
    "embed.typeform": "Typeform",
    "static.hotjar": "Hotjar",
    "cdn.heapanalytics": "Heap",
    "wp-content": "WordPress",
    "cdn.shopify": "Shopify",
    "static.parastorage": "Wix",
    "squarespace.com": "Squarespace",
    "assets.website-files.com": "Webflow",
    "tawk.to": "Tawk.to",
    "livechatinc": "LiveChat",
    "cdn.mxpnl": "Mixpanel",
    "widget.manychat": "ManyChat",
    "cdn.amplitude": "Amplitude",
    "js.sentry-cdn": "Sentry",
    "snap.licdn.com": "LinkedIn Insight",
}


def _txt(domain):
    try:
        r = requests.get(DOH, params={"name": domain, "type": "TXT"}, timeout=TIMEOUT)
        return [a.get("data", "").strip('"') for a in r.json().get("Answer", [])]
    except requests.RequestException:
        return []


def _m365(domain):
    # the realm endpoint reports Managed/Federated when a domain has an azure ad / entra tenant
    try:
        r = requests.get("https://login.microsoftonline.com/getuserrealm.srf",
                         params={"login": f"info@{domain}", "xml": "1"}, timeout=TIMEOUT)
        m = re.search(r"<NameSpaceType>(\w+)</NameSpaceType>", r.text)
        ns = m.group(1) if m else ""
        return ns if ns in ("Managed", "Federated") else ""
    except requests.RequestException:
        return ""


def _html(domain):
    for url in (f"https://www.{domain}", f"https://{domain}"):
        try:
            r = requests.get(url, headers=UA, timeout=TIMEOUT)
            if r.ok and "html" in r.headers.get("Content-Type", "").lower():
                return r.text
        except requests.RequestException:
            continue
    return ""


def facts(domain):
    # one vendors_and_tools fact per detected platform, deduped by tool name
    found = {}  # tool -> (value, source_url)

    txt_src = f"https://dns.google/resolve?name={domain}&type=TXT"
    for rec in _txt(domain):
        low = rec.lower()
        for token, tool in TXT_TOKENS.items():
            if token in low:
                found.setdefault(tool, (f"{domain} has a {tool} domain-verification record", txt_src))

    ns = _m365(domain)
    if ns:
        found["Microsoft 365 / Entra tenant"] = (f"{domain} has a Microsoft 365 / Entra ID tenant ({ns}); email provider shown separately by MX",
                                  f"https://login.microsoftonline.com/getuserrealm.srf?login=info@{domain}&xml=1")

    low = _html(domain).lower()
    for sign, tool in WEB_SIGNS.items():
        if sign in low:
            found.setdefault(tool, (f"{domain} website loads {tool}", f"https://www.{domain}"))

    return [Fact(category="vendors_and_tools", value=v, source_url=s,
                 source_title=f"tech stack: {domain}", confidence=0.85, verified=True)
            for tool, (v, s) in found.items()]
