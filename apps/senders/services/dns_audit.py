"""
DNS & Email Reputation Audit Service.

Performs live DNS checks for SPF, DKIM, DMARC, MX, and rDNS (PTR)
using Cloudflare's DNS-over-HTTPS (DoH) API — no system DNS dependencies.
All checks are synchronous HTTP requests, safe for request-scoped use.
"""
import logging
import re
import socket
import httpx

logger = logging.getLogger(__name__)

# Cloudflare DoH endpoint — fast, reliable, no auth required
_DOH_URL = "https://cloudflare-dns.com/dns-query"
_TIMEOUT = 8.0


def _doh_query(name: str, record_type: str) -> list[str]:
    """
    Query Cloudflare DoH and return a flat list of record data strings.
    Returns an empty list on any error.
    """
    try:
        resp = httpx.get(
            _DOH_URL,
            params={"name": name, "type": record_type},
            headers={"Accept": "application/dns-json"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        answers = data.get("Answer") or []
        # TXT records include quotes — strip them for easier parsing
        return [a.get("data", "").strip('"') for a in answers if a.get("type") is not None]
    except Exception as exc:
        logger.debug(f"[DNS Audit] DoH query failed for {name} {record_type}: {exc}")
        return []


def _check_spf(domain: str) -> dict:
    """
    Check if a valid SPF TXT record exists on the domain.
    Returns status, value, and human-readable advice.
    """
    records = _doh_query(domain, "TXT")
    spf_records = [r for r in records if r.startswith("v=spf1")]

    desc = "SPF is a DNS record that lists which email servers are allowed to send email from your domain. Without it, spammers can forge emails that look like they're from you."

    if not spf_records:
        return {
            "check": "SPF",
            "description": desc,
            "status": "fail",
            "value": None,
            "advice": "No SPF record found. Add a DNS TXT record like: v=spf1 include:_spf.yourprovider.com ~all",
        }

    if len(spf_records) > 1:
        return {
            "check": "SPF",
            "description": desc,
            "status": "warning",
            "value": spf_records[0],
            "advice": f"Multiple SPF records found ({len(spf_records)}). Only one is allowed — remove duplicates.",
        }

    value = spf_records[0]
    # Warn if SPF uses +all (dangerous — allows anyone to send)
    if "+all" in value:
        return {
            "check": "SPF",
            "description": desc,
            "status": "warning",
            "value": value,
            "advice": 'SPF record uses "+all" which is extremely permissive. Change to "~all" or "-all".',
        }

    return {
        "check": "SPF",
        "description": desc,
        "status": "pass",
        "value": value,
        "advice": "SPF record is correctly configured.",
    }


def _check_dmarc(domain: str) -> dict:
    """Check DMARC policy at _dmarc.<domain>."""
    dmarc_domain = f"_dmarc.{domain}"
    records = _doh_query(dmarc_domain, "TXT")
    dmarc_records = [r for r in records if r.startswith("v=DMARC1")]

    desc = "DMARC tells email providers (like Gmail or Outlook) what to do with emails that fail SPF or DKIM checks. You can set it to monitor, quarantine, or reject suspicious messages."

    if not dmarc_records:
        return {
            "check": "DMARC",
            "description": desc,
            "status": "fail",
            "value": None,
            "advice": "No DMARC record found. Add: v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@yourdomain.com",
        }

    value = dmarc_records[0]
    policy_match = re.search(r"p=(\w+)", value)
    policy = policy_match.group(1).lower() if policy_match else "none"

    if policy == "none":
        return {
            "check": "DMARC",
            "description": desc,
            "status": "warning",
            "value": value,
            "advice": 'DMARC policy is "p=none" (monitoring only). Upgrade to "p=quarantine" or "p=reject" for full protection.',
        }

    return {
        "check": "DMARC",
        "description": desc,
        "status": "pass",
        "value": value,
        "advice": f'DMARC is configured with policy "{policy}". Great protection.',
    }


def _check_dkim(domain: str, selector: str = "default") -> dict:
    """
    Check DKIM for a given selector (defaults to 'default').
    Tries common selectors if 'default' not found.
    """
    common_selectors = [selector, "google", "s1", "s2", "mail", "key1", "dkim"]
    found_selector = None
    value = None

    for sel in common_selectors:
        dkim_domain = f"{sel}._domainkey.{domain}"
        records = _doh_query(dkim_domain, "TXT")
        dkim_records = [r for r in records if "v=DKIM1" in r or "p=" in r]
        if dkim_records:
            found_selector = sel
            value = dkim_records[0]
            break

    desc = "DKIM adds a digital signature to every email you send. The recipient's email provider checks this signature against a public key in your DNS to verify the email really came from your domain."

    if not found_selector:
        return {
            "check": "DKIM",
            "description": desc,
            "status": "fail",
            "value": None,
            "advice": "No DKIM record found for common selectors. Configure DKIM with your email provider and publish the TXT record.",
        }

    return {
        "check": "DKIM",
        "description": desc,
        "status": "pass",
        "value": f"[selector: {found_selector}] {value[:60]}...",
        "advice": f'DKIM record found using selector "{found_selector}".',
    }


def _check_mx(domain: str) -> dict:
    """Check MX records for the domain."""
    records = _doh_query(domain, "MX")

    desc = "MX records tell the internet where to deliver emails sent to your domain. You need these if you want to receive replies or have anyone email you at @yourdomain.com."

    if not records:
        return {
            "check": "MX",
            "description": desc,
            "status": "warning",
            "value": None,
            "advice": "No MX records found. Recipients cannot reply to this domain.",
        }

    # Return only the first 3 for brevity
    short = ", ".join(records[:3])
    return {
        "check": "MX",
        "description": desc,
        "status": "pass",
        "value": short,
        "advice": f"{len(records)} MX record(s) found. Domain accepts inbound email.",
    }


def _check_rdns(smtp_host: str) -> dict:
    """
    Check reverse DNS (PTR) for the SMTP host IP.
    Uses stdlib since this isn't a domain lookup — it requires the actual IP.
    """
    desc = "rDNS (also called PTR record) is like a reverse phonebook — it looks up the hostname behind your SMTP server's IP address. Spam filters use this to check if your server is who it claims to be."

    try:
        ip = socket.gethostbyname(smtp_host)
        hostname, _, _ = socket.gethostbyaddr(ip)
        value = f"{ip} → {hostname}"
        parts = smtp_host.split(".")
        host_suffix = parts[-2] + "." + parts[-1] if len(parts) >= 2 else smtp_host
        if smtp_host.lower() in hostname.lower() or hostname.lower().endswith(host_suffix):
            return {
                "check": "rDNS (PTR)",
                "description": desc,
                "status": "pass",
                "value": value,
                "advice": "Reverse DNS correctly points to your sending hostname.",
            }
        return {
            "check": "rDNS (PTR)",
            "description": desc,
            "status": "warning",
            "value": value,
            "advice": f'rDNS hostname "{hostname}" does not match SMTP host "{smtp_host}". Mismatches can trigger spam filters.',
        }
    except socket.herror:
        return {
            "check": "rDNS (PTR)",
            "description": desc,
            "status": "fail",
            "value": smtp_host,
            "advice": "No reverse DNS record (PTR) found for SMTP host IP. Many spam filters penalize missing rDNS.",
        }
    except Exception as exc:
        return {
            "check": "rDNS (PTR)",
            "description": desc,
            "status": "warning",
            "value": smtp_host,
            "advice": f"Could not resolve SMTP host for rDNS check: {exc}",
        }


def audit_sender_dns(domain: str, smtp_host: str = None, dkim_selector: str = "default") -> dict:
    """
    Run a full DNS reputation audit for a sender domain.

    Args:
        domain: The sender's email domain (e.g. "yourdomain.com").
        smtp_host: Optional SMTP server hostname for rDNS check.
        dkim_selector: DKIM selector prefix to probe (default: "default").

    Returns:
        dict with keys:
            - domain (str)
            - checks (list[dict]): individual check results
            - overall_status (str): "pass" | "warning" | "fail"
            - score (int): 0–100 health score
    """
    checks = []
    checks.append(_check_spf(domain))
    checks.append(_check_dmarc(domain))
    checks.append(_check_dkim(domain, dkim_selector))
    checks.append(_check_mx(domain))

    if smtp_host:
        checks.append(_check_rdns(smtp_host))

    # Calculate score: each check = 20 points (or 25 if no rDNS)
    per_check = 100 // len(checks)
    score = 0
    for c in checks:
        if c["status"] == "pass":
            score += per_check
        elif c["status"] == "warning":
            score += per_check // 2

    # Clamp
    score = min(score, 100)

    # Overall status
    statuses = [c["status"] for c in checks]
    if "fail" in statuses:
        overall = "fail"
    elif "warning" in statuses:
        overall = "warning"
    else:
        overall = "pass"

    return {
        "domain": domain,
        "checks": checks,
        "overall_status": overall,
        "score": score,
    }
