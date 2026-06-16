import base64
import logging
import re

import bleach
from bleach.css_sanitizer import CSSSanitizer

logger = logging.getLogger(__name__)

EMAIL_ALLOWED_TAGS = {
    'a', 'abbr', 'acronym', 'address', 'area', 'article', 'aside', 'b', 'blockquote', 'br',
    'caption', 'center', 'cite', 'code', 'col', 'colgroup', 'dd', 'del', 'details', 'div',
    'dl', 'dt', 'em', 'figcaption', 'figure', 'font', 'footer', 'h1', 'h2', 'h3', 'h4',
    'h5', 'h6', 'header', 'hr', 'i', 'img', 'ins', 'kbd', 'li', 'main', 'mark', 'ol',
    'p', 'pre', 's', 'section', 'small', 'span', 'strong', 'sub', 'summary', 'sup',
    'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr', 'u', 'ul',
}
EMAIL_ALLOWED_ATTRS = {
    '*': ['align', 'class', 'dir', 'height', 'lang', 'style', 'title', 'width'],
    'a': ['href', 'name', 'target', 'rel', 'title'],
    'img': ['alt', 'height', 'src', 'title', 'width'],
    'table': ['border', 'cellpadding', 'cellspacing', 'role', 'width'],
    'td': ['colspan', 'rowspan', 'width'],
    'th': ['colspan', 'rowspan', 'width'],
}
EMAIL_CSS_SANITIZER = CSSSanitizer(allowed_css_properties=[
    'background', 'background-color', 'border', 'border-bottom', 'border-collapse',
    'border-color', 'border-left', 'border-radius', 'border-right', 'border-spacing',
    'border-style', 'border-top', 'border-width', 'color', 'display', 'font',
    'font-family', 'font-size', 'font-style', 'font-weight', 'height', 'line-height',
    'margin', 'margin-bottom', 'margin-left', 'margin-right', 'margin-top', 'max-width',
    'min-width', 'padding', 'padding-bottom', 'padding-left', 'padding-right',
    'padding-top', 'text-align', 'text-decoration', 'vertical-align', 'white-space',
    'width',
])


def sanitize_email_html(html):
    return bleach.clean(
        html or '',
        tags=EMAIL_ALLOWED_TAGS,
        attributes=EMAIL_ALLOWED_ATTRS,
        protocols=['http', 'https', 'mailto', 'tel', 'data'],
        strip=True,
        css_sanitizer=EMAIL_CSS_SANITIZER,
    )


def render_email_for_display(body_html, body_text=None, inline_cids=None):
    """Render sanitized email content for a sandboxed iframe."""
    if not body_html and not body_text:
        return _get_empty_email_html()

    if body_html:
        try:
            html = body_html
            if inline_cids:
                for cid, uri in inline_cids.items():
                    html = html.replace(f'cid:{cid}', uri)

            html = re.sub(r'cid:([\w\.\-\+]+)', lambda m: f"/inbox/proxy-image/?cid={m.group(1)}", html)

            def proxy_external_images(match):
                full_tag = match.group(0)
                src_match = re.search(r'src\s*=\s*["\']([^"\']+)["\']', full_tag, flags=re.IGNORECASE)
                if src_match:
                    src = src_match.group(1)
                    if src.startswith(('http://', 'https://')) and not src.startswith('data:'):
                        encoded_src = base64.urlsafe_b64encode(src.encode()).decode()
                        full_tag = full_tag.replace(src, f"/inbox/proxy-image/?url={encoded_src}")
                return full_tag

            html = re.sub(r'<img\s+[^>]*>', proxy_external_images, html, flags=re.IGNORECASE)

            body_match = re.search(r'<body[^>]*>(.*?)</body>', html, flags=re.DOTALL | re.IGNORECASE)
            body_content = body_match.group(1) if body_match else html

            styles = ''
            head_match = re.search(r'<head[^>]*>(.*?)</head>', html, flags=re.DOTALL | re.IGNORECASE)
            if head_match:
                style_matches = re.findall(r'<style[^>]*>(.*?)</style>', head_match.group(1), flags=re.DOTALL | re.IGNORECASE)
                styles = ''.join(style_matches)

            body_content = sanitize_email_html(body_content)
            body_content = re.sub(
                r'<a\s+([^>]*href\s*=\s*["\']https?://[^"\']+["\'][^>]*)>',
                r'<a \1 target="_blank" rel="noopener noreferrer">',
                body_content,
                flags=re.IGNORECASE,
            )
            styles = EMAIL_CSS_SANITIZER.sanitize_css(styles) if styles else ''

            return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'self' data: https:; img-src 'self' data: https: blob:; style-src 'self' 'unsafe-inline';">
    <style>
        {styles}
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; padding: 0; background: #f4f4f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #1e293b; }}
        .email-container {{ max-width: 600px; margin: 0 auto; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
        .email-body {{ padding: 24px; }}
        img {{ max-width: 100% !important; height: auto !important; display: block; }}
        a {{ color: #6D28D9; text-decoration: underline; }}
        a[href^="tel"] {{ color: inherit; text-decoration: none; }}
        table {{ max-width: 100%; width: 100%; border-collapse: collapse; }}
        @media (max-width: 600px) {{ .email-container {{ border-radius: 0; }} .email-body {{ padding: 16px; }} }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="email-body">
            {body_content}
        </div>
    </div>
</body>
</html>'''
        except Exception:
            logger.exception("Error rendering email HTML")
            return _get_empty_email_html()

    escaped = body_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    paragraphs = escaped.split('\n\n')
    html_parts = []
    for paragraph in paragraphs:
        lines = paragraph.split('\n')
        html_parts.append('<p style="margin:0 0 1em 0;line-height:1.6">' + '<br>'.join(lines) + '</p>')
    body_text_html = ''.join(html_parts)

    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; padding: 0; background: #f4f4f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #1e293b; }}
        .email-container {{ max-width: 600px; margin: 0 auto; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
        .email-body {{ padding: 24px; }}
        p {{ margin: 0 0 1em 0; line-height: 1.6; }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="email-body">
            {body_text_html}
        </div>
    </div>
</body>
</html>'''


def _get_empty_email_html():
    return '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { margin: 0; padding: 40px 20px; background: #f4f4f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
        .empty { max-width: 400px; margin: 0 auto; text-align: center; padding: 40px 20px; background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
        .empty svg { color: #cbd5e1; margin-bottom: 16px; }
        .empty h3 { color: #1e293b; font-size: 18px; margin-bottom: 8px; }
        .empty p { color: #64748b; font-size: 14px; }
    </style>
</head>
<body>
    <div class="empty">
        <svg width="64" height="64" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
        <h3>No content available</h3>
        <p>This message has no readable content.</p>
    </div>
</body>
</html>'''
