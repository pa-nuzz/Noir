import base64
import logging
import re

import bleach
from bleach.css_sanitizer import CSSSanitizer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowed HTML tags & attributes – keep SVG, picture and source for rich emails
# ---------------------------------------------------------------------------
EMAIL_ALLOWED_TAGS = {
    'a', 'abbr', 'acronym', 'address', 'area', 'article', 'aside', 'b', 'blockquote', 'br',
    'caption', 'center', 'cite', 'code', 'col', 'colgroup', 'dd', 'del', 'details', 'div',
    'dl', 'dt', 'em', 'figcaption', 'figure', 'font', 'footer', 'h1', 'h2', 'h3', 'h4',
    'h5', 'h6', 'header', 'hr', 'i', 'img', 'ins', 'kbd', 'li', 'main', 'mark', 'ol',
    'p', 'pre', 's', 'section', 'small', 'span', 'strong', 'sub', 'summary', 'sup',
    'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr', 'u', 'ul',
    'svg', 'picture', 'source',
}

EMAIL_ALLOWED_ATTRS = {
    '*': ['align', 'class', 'dir', 'height', 'lang', 'style', 'title', 'width', 'data-*'],
    'a': ['href', 'name', 'target', 'rel', 'title'],
    'img': [
        'alt', 'border', 'height', 'hspace', 'src', 'srcset', 'sizes',
        'style', 'title', 'vspace', 'width', 'loading', 'decoding', 'data-src',
    ],
    'source': ['srcset', 'type', 'media'],
    'table': ['bgcolor', 'border', 'cellpadding', 'cellspacing', 'role', 'width'],
    'td': ['bgcolor', 'colspan', 'rowspan', 'valign', 'width'],
    'th': ['bgcolor', 'colspan', 'rowspan', 'valign', 'width'],
}

# ---------------------------------------------------------------------------
# CSS sanitiser – wide range of layout properties for modern HTML emails
# ---------------------------------------------------------------------------
EMAIL_CSS_SANITIZER = CSSSanitizer(allowed_css_properties=[
    'background', 'background-color', 'background-image', 'background-position',
    'background-repeat', 'background-size',
    'border', 'border-bottom', 'border-collapse', 'border-color', 'border-left',
    'border-radius', 'border-right', 'border-spacing', 'border-style', 'border-top',
    'border-width', 'clear', 'color', 'cursor', 'display', 'float', 'font', 'font-family',
    'font-size', 'font-style', 'font-weight', 'height', 'line-height', 'list-style',
    'list-style-type', 'margin', 'margin-bottom', 'margin-left', 'margin-right',
    'margin-top', 'max-height', 'max-width', 'min-height', 'min-width', 'opacity',
    'overflow', 'overflow-x', 'overflow-y', 'padding', 'padding-bottom', 'padding-left',
    'padding-right', 'padding-top', 'position', 'top', 'right', 'bottom', 'left',
    'z-index', 'object-fit', 'object-position', 'table-layout', 'text-align',
    'text-decoration', 'text-indent', 'text-transform', 'vertical-align', 'visibility',
    'white-space', 'width', 'word-break', 'word-wrap',
])


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _proxy_url(url: str) -> str:
    """Encode an external URL for the image proxy endpoint."""
    encoded = base64.urlsafe_b64encode(url.encode()).decode()
    return f"/inbox/proxy-image/?url={encoded}"


def _proxy_tag_sources(match):
    """Proxy external src and srcset URLs in an <img> or <source> tag."""
    tag = match.group(0)

    # Handle src attribute
    src_match = re.search(r'src\s*=\s*["\']([^"\']+)["\']', tag, flags=re.IGNORECASE)
    if src_match:
        src = src_match.group(1)
        if src.startswith(('http://', 'https://')) and not src.startswith('data:'):
            tag = tag.replace(src, _proxy_url(src))

    # Handle srcset attribute – may contain multiple comma-separated URLs
    srcset_match = re.search(r'srcset\s*=\s*["\']([^"\']+)["\']', tag, flags=re.IGNORECASE)
    if srcset_match:
        srcset = srcset_match.group(1)
        new_parts = []
        for entry in srcset.split(','):
            entry = entry.strip()
            if not entry:
                continue
            url_part, *desc = entry.split()
            if url_part.startswith(('http://', 'https://')) and not url_part.startswith('data:'):
                url_part = _proxy_url(url_part)
            new_parts.append(' '.join([url_part] + desc))
        new_srcset = ', '.join(new_parts)
        tag = re.sub(
            r'srcset\s*=\s*["\'][^"\']*["\']',
            f'srcset="{new_srcset}"',
            tag,
            flags=re.IGNORECASE,
        )

    return tag


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sanitize_email_html(html: str) -> str:
    """Sanitize HTML using Bleach with the extended allow-list."""
    return bleach.clean(
        html or '',
        tags=EMAIL_ALLOWED_TAGS,
        attributes=EMAIL_ALLOWED_ATTRS,
        protocols=['http', 'https', 'mailto', 'tel', 'data'],
        strip=True,
        css_sanitizer=EMAIL_CSS_SANITIZER,
    )


def render_email_for_display(body_html=None, body_text=None, inline_cids=None):
    """Render an email (HTML or plain-text) for sandboxed iframe display.

    * CID references are rewritten to the internal proxy endpoint.
    * All external ``src`` and ``srcset`` URLs are routed via ``/inbox/proxy-image/``.
    * Inline ``<style>`` blocks are extracted, sanitized and inlined.
    """
    if not body_html and not body_text:
        return _get_empty_email_html()

    # -------------------------------------------------------------------
    # HTML path – the rich, formatted version
    # -------------------------------------------------------------------
    if body_html:
        try:
            html = body_html

            # Resolve any CID placeholders supplied by the view
            if inline_cids:
                for cid, uri in inline_cids.items():
                    html = html.replace(f'cid:{cid}', uri)

            # Generic CID handling for images that embed "cid:…"
            html = re.sub(
                r'cid:([\w\.\-\+]+)',
                lambda m: f"/inbox/proxy-image/?cid={m.group(1)}",
                html,
            )

            # Proxy <img> and <source> tags (including those inside <picture>)
            html = re.sub(r'<img[^>]*>', _proxy_tag_sources, html, flags=re.IGNORECASE)
            html = re.sub(r'<source[^>]*>', _proxy_tag_sources, html, flags=re.IGNORECASE)

            # Extract any <style> blocks – they'll be sanitized separately
            head_match = re.search(
                r'<head[^>]*>(.*?)</head>', html, flags=re.DOTALL | re.IGNORECASE
            )
            styles = ''
            if head_match:
                style_matches = re.findall(
                    r'<style[^>]*>(.*?)</style>',
                    head_match.group(1),
                    flags=re.DOTALL | re.IGNORECASE,
                )
                styles = ''.join(style_matches)

            # Pull out the <body> content – if missing fall back to the whole HTML
            body_match = re.search(
                r'<body[^>]*>(.*?)</body>', html, flags=re.DOTALL | re.IGNORECASE
            )
            body_content = body_match.group(1) if body_match else html

            # Sanitize the body HTML
            body_content = sanitize_email_html(body_content)

            # Ensure links open in a new tab safely
            body_content = re.sub(
                r'<a\s+([^>]*href=["\'][^"\']+["\'][^>]*)>',
                r'<a \1 target="_blank" rel="noopener noreferrer">',
                body_content,
                flags=re.IGNORECASE,
            )

            # Sanitize extracted CSS styles
            styles = EMAIL_CSS_SANITIZER.sanitize_css(styles) if styles else ''

            # ---------------------------------------------------------------
            # Build final HTML document
            # ---------------------------------------------------------------
            return (
                '<!DOCTYPE html>\n'
                '<html>\n'
                '<head>\n'
                '    <meta charset="UTF-8">\n'
                '    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
                '    <meta http-equiv="Content-Security-Policy" content="default-src \'self\' data: https:; img-src \'self\' data: https: blob:; style-src \'self\' \'unsafe-inline\';">\n'
                '    <style>\n'
                f'        {styles}\n'
                '        * { box-sizing: border-box; }\n'
                '        html, body { margin:0; padding:0; background:#ffffff; font-family:-apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif; line-height:1.6; color:#1e293b; }\n'
                '        .email-wrapper { width:100%; background:#ffffff; }\n'
                '        img { max-width:100% !important; height:auto !important; }\n'
                '        a { color:#6D28D9; text-decoration:underline; }\n'
                '        a[href^="tel"] { color:inherit; text-decoration:none; }\n'
                '        table { max-width:100%; border-collapse:collapse; }\n'
                '        td, th { word-break:break-word; }\n'
                '        @media (max-width:600px) { .email-wrapper { padding:0 !important; } td, th { display:block !important; width:100% !important; } }\n'
                '    </style>\n'
                '</head>\n'
                '<body>\n'
                '    <div class="email-wrapper">\n'
                f'        {body_content}\n'
                '    </div>\n'
                '</body>\n'
                '</html>\n'
            )
        except Exception:
            logger.exception("Error rendering email HTML")
            return _get_empty_email_html()

    # -------------------------------------------------------------------
    # Plain-text fallback – simple styled paragraphs
    # -------------------------------------------------------------------
    escaped = body_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    paragraphs = escaped.split("\n\n")
    html_parts = []
    for paragraph in paragraphs:
        lines = paragraph.split("\n")
        html_parts.append(
            "<p style='margin:0 0 1em 0;line-height:1.6'>"
            + "<br>".join(lines)
            + "</p>"
        )
    body_text_html = "".join(html_parts)
    return (
        '<!DOCTYPE html>\n'
        '<html>\n'
        '<head>\n'
        '    <meta charset="UTF-8">\n'
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '    <style>\n'
        '        * { box-sizing:border-box; }\n'
        '        body { margin:0; padding:0; background:#f4f4f5; font-family:-apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif; line-height:1.6; color:#1e293b; }\n'
        '        .email-container { max-width:600px; margin:0 auto; background:#fff; border-radius:8px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,0.08); }\n'
        '        .email-body { padding:24px; }\n'
        '        p { margin:0 0 1em 0; line-height:1.6; }\n'
        '    </style>\n'
        '</head>\n'
        '<body>\n'
        '    <div class="email-container">\n'
        f'        <div class="email-body">{body_text_html}</div>\n'
        '    </div>\n'
        '</body>\n'
        '</html>\n'
    )


def _get_empty_email_html() -> str:
    """Fallback markup shown when an email has no renderable content."""
    return (
        '<!DOCTYPE html>\n'
        '<html>\n'
        '<head>\n'
        '    <meta charset="UTF-8">\n'
        '    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '    <style>\n'
        '        body { margin:0; padding:40px 20px; background:#f4f4f5; font-family:-apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; }\n'
        '        .empty { max-width:400px; margin:0 auto; text-align:center; padding:40px 20px; background:#fff; border-radius:8px; box-shadow:0 1px 3px rgba(0,0,0,0.08); }\n'
        '        .empty svg { color:#cbd5e1; margin-bottom:16px; }\n'
        '        .empty h3 { color:#1e293b; font-size:18px; margin-bottom:8px; }\n'
        '        .empty p { color:#64748b; font-size:14px; }\n'
        '    </style>\n'
        '</head>\n'
        '<body>\n'
        '    <div class="empty">\n'
        '        <svg width="64" height="64" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>\n'
        '        <h3>No content available</h3>\n'
        '        <p>This message has no readable content.</p>\n'
        '    </div>\n'
        '</body>\n'
        '</html>\n'
    )
