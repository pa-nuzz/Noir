import html

import nh3

from apps.intelligence.ml_model import predict_spam_score


ALLOWED_TAGS = frozenset({
    'p', 'br', 'strong', 'b', 'em', 'i', 'u', 'a', 'ul', 'ol', 'li',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'div', 'img',
    'html', 'head', 'body', 'meta', 'title', 'style', 'table', 'tr', 'td',
    'th', 'thead', 'tbody', 'tfoot', 'col', 'colgroup', 'caption',
    'hr', 'sub', 'sup', 'pre', 'code', 'blockquote', 'figure', 'figcaption',
})

ALLOWED_ATTRIBUTES = {
    'a': {'href', 'title', 'target'},
    'img': {'src', 'alt', 'width', 'height'},
    'meta': {'charset', 'name', 'content'},
    'table': {'cellpadding', 'cellspacing', 'border', 'width'},
    'tr': {'valign'},
    'td': {'valign', 'colspan', 'rowspan', 'width', 'style'},
    'th': {'valign', 'colspan', 'rowspan'},
}

GLOBAL_ATTRIBUTES = {'class', 'style', 'id', 'align'}

CLEAN_ATTRIBUTES = {
    tag: attrs | GLOBAL_ATTRIBUTES for tag, attrs in ALLOWED_ATTRIBUTES.items()
}
CLEAN_ATTRIBUTES.setdefault('*', GLOBAL_ATTRIBUTES)


def sanitize_html(raw_html: str) -> str:
    if not raw_html:
        return ''

    return nh3.clean(
        raw_html,
        tags=ALLOWED_TAGS,
        attributes=CLEAN_ATTRIBUTES,
        clean_content_tags=frozenset({'script'}),
    )


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
