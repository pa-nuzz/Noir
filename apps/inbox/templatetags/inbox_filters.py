import hashlib
import re

from django import template

register = template.Library()


@register.filter
def hash_hue(value):
    """Return a deterministic HSL hue (0-360) from a string using its hash."""
    if not value:
        return 0
    digest = hashlib.md5(value.encode('utf-8')).hexdigest()
    return int(digest[:6], 16) % 360


@register.filter
def gravatar_url(value, size=40):
    """Return Gravatar URL for an email address."""
    if not value:
        return ''
    email_hash = hashlib.md5(value.strip().lower().encode('utf-8')).hexdigest()
    return f'https://www.gravatar.com/avatar/{email_hash}?s={size}&d=mp'


@register.filter
def sender_logo_url(value):
    """Return company favicon/logo URL proxied through our server."""
    if not value or '@' not in value:
        return ''
    domain = value.strip().lower().split('@')[1]
    # Only strip common email subdomain prefixes if the remaining domain has at least two parts
    stripped = re.sub(r'^(mail\.|email\.|inbox\.)', '', domain)
    if stripped.count('.') >= 1:
        domain = stripped
    if not domain or domain.count('.') < 1:
        return ''
    return f'/inbox/sender-logo/?domain={domain}'
