import html
import re
from typing import Set

from apps.intelligence.ml_model import predict_spam_score


# Allowed HTML tags for email content
ALLOWED_TAGS: Set[str] = {
    'p', 'br', 'strong', 'b', 'em', 'i', 'u', 'a', 'ul', 'ol', 'li',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'div', 'img',
    'html', 'head', 'body', 'meta', 'title', 'style', 'table', 'tr', 'td',
    'th', 'thead', 'tbody', 'tfoot', 'col', 'colgroup', 'caption',
    'hr', 'sub', 'sup', 'pre', 'code', 'blockquote', 'figure', 'figcaption',
}

# Allowed attributes per tag
ALLOWED_ATTRIBUTES: dict[str, Set[str]] = {
    'a': {'href', 'title', 'target'},
    'img': {'src', 'alt', 'width', 'height'},
    'meta': {'charset', 'name', 'content'},
    'table': {'cellpadding', 'cellspacing', 'border', 'width'},
    'tr': {'valign'},
    'td': {'valign', 'colspan', 'rowspan', 'width', 'style'},
    'th': {'valign', 'colspan', 'rowspan'},
    '*': {'class', 'style', 'id', 'align'}
}

# Dangerous protocols to block
DANGEROUS_PROTOCOLS: Set[str] = {
    'javascript:', 'data:', 'vbscript:', 'file:', 'about:', 'chrome:', 'javascript'
}


def sanitize_html(raw_html: str) -> str:
    """
    Sanitize HTML content for email safety.
    Removes dangerous tags, attributes, and protocols.
    Falls back to HTML escaping if content is suspicious.
    """
    if not raw_html:
        return ''

    # Check for dangerous protocols in href/src attribute values
    if re.search(r'(href|src)\s*=\s*["\'][^"\']*(javascript|data|vbscript|file|about):', raw_html, re.IGNORECASE):
        return html.escape(raw_html)

    # Remove script tags and event handlers completely
    raw_html = re.sub(r'<script[^>]*>.*?</script>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
    raw_html = re.sub(r'on\w+\s*=\s*["\'][^"\']*["\']', '', raw_html, flags=re.IGNORECASE)
    raw_html = re.sub(r'on\w+\s*=\s*[^\s>]+', '', raw_html, flags=re.IGNORECASE)

    # Remove iframe, object, embed, form, input tags
    raw_html = re.sub(r'<(iframe|object|embed|form|input|textarea|button)[^>]*>.*?</\1>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
    raw_html = re.sub(r'<(iframe|object|embed|form|input|textarea|button)[^/]*/?>', '', raw_html, flags=re.IGNORECASE)

    # Remove any tag not in allowed list
    def clean_tag(match: re.Match) -> str:
        tag_content = match.group(1)
        is_closing = tag_content.startswith('/')
        if is_closing:
            tag_name = tag_content[1:].lower().rstrip('/')
            if tag_name not in ALLOWED_TAGS:
                return ''
            return f'</{tag_name}>'
        tag_parts = tag_content.split(None, 1)
        tag_name = tag_parts[0].lower().rstrip('/')

        if tag_name not in ALLOWED_TAGS:
            return ''

        # Clean attributes
        if len(tag_parts) > 1:
            attrs_str = tag_parts[1]
            cleaned_attrs = []

            # Find all attributes
            attr_pattern = r'(\w+)\s*=\s*["\']([^"\']*)["\']'
            for attr_match in re.finditer(attr_pattern, attrs_str):
                attr_name = attr_match.group(1).lower()
                attr_value = attr_match.group(2)

                allowed_for_tag = ALLOWED_ATTRIBUTES.get(tag_name, set())
                allowed_global = ALLOWED_ATTRIBUTES.get('*', set())

                if attr_name in allowed_for_tag or attr_name in allowed_global:
                    # Check for dangerous protocols in href/src
                    if attr_name in ('href', 'src'):
                        attr_value_lower = attr_value.lower()
                        if any(proto in attr_value_lower for proto in DANGEROUS_PROTOCOLS):
                            continue
                    if attr_name == 'style':
                        cleaned_attrs.append(f'{attr_name}="{attr_value}"')
                    else:
                        cleaned_attrs.append(f'{attr_name}="{html.escape(attr_value)}"')

            if cleaned_attrs:
                return f'<{tag_name} {" ".join(cleaned_attrs)}>'

        return f'<{tag_name}>'

    # Clean opening and self-closing tags (exclude closing tags — handled below)
    raw_html = re.sub(r'<(?!\/)([^>]+)>', clean_tag, raw_html)

    # Remove any remaining closing tags for disallowed elements
    def clean_close_tag(match: re.Match) -> str:
        tag_name = match.group(1).lower()
        if tag_name in ALLOWED_TAGS:
            return match.group(0)
        return ''

    raw_html = re.sub(r'</(\w+)>', clean_close_tag, raw_html)

    return raw_html.strip()


def text_to_html(text: str) -> str:
    if not text:
        return ''
    lines = [line.strip() for line in text.splitlines()]
    blocks = [f"<p>{html.escape(line)}</p>" for line in lines if line]
    return '\n'.join(blocks)


def apply_campaign_spam_signals(campaign_obj) -> None:
    content = f"{campaign_obj.subject} {campaign_obj.body_text}"
    try:
        score = predict_spam_score(content)
        campaign_obj.spam_score = score
        if score >= 75:
            campaign_obj.spam_risk = 'high'
        elif score >= 45:
            campaign_obj.spam_risk = 'medium'
        else:
            campaign_obj.spam_risk = 'low'
    except Exception:
        pass


def merge_recipient_emails(existing_recipient_emails: str, list_emails: list[str]) -> str:
    existing = [email.strip() for email in (existing_recipient_emails or '').split(',') if email.strip()]
    merged = list(dict.fromkeys(existing + list_emails))
    return ', '.join(merged)
