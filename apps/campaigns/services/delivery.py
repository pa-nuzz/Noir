import logging
import smtplib
import ssl
import re
import random
import time
from urllib.parse import quote_plus
from uuid import uuid4
from datetime import datetime

logger = logging.getLogger(__name__)

from django.db.models import Count, F
from django.urls import reverse
from django.utils import timezone
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formatdate, make_msgid

from apps.campaigns.models import EmailEngagement
from apps.campaigns import constants as C

from .content import sanitize_html


# ──────────────────────────────────────────────
#  HTML → plain-text conversion
# ──────────────────────────────────────────────

def _html_to_text(html_body: str) -> str:
    if not html_body:
        return ''
    text = re.sub(r'<[^>]+>', '', html_body)
    text = re.sub(r'\n\s*\n+', '\n\n', text)
    return text.strip()


# ──────────────────────────────────────────────
#  Tracking
# ──────────────────────────────────────────────

def _inject_link_tracking(html_body: str, tracking_token: str, base_url: str) -> str:
    if not html_body:
        return ''

    click_base = f"{base_url}{reverse('campaigns:track_click', kwargs={'token': tracking_token})}"

    def _replace_href(match):
        quote_char = match.group(1)
        original_url = (match.group(2) or '').strip()
        if not original_url.startswith(('http://', 'https://')):
            return match.group(0)
        tracked = f"{click_base}?next={quote_plus(original_url)}"
        return f"href={quote_char}{tracked}{quote_char}"

    pattern = re.compile(r'href\s*=\s*(["\'])(.*?)\1', re.IGNORECASE)
    return pattern.sub(_replace_href, html_body)


def _inject_open_pixel(html_body: str, tracking_token: str, base_url: str) -> str:
    open_url = f"{base_url}{reverse('campaigns:track_open', kwargs={'token': tracking_token})}"
    pixel = f'<img src="{open_url}" width="1" height="1" alt="" style="display:block;opacity:0;max-height:0;max-width:0;" />'
    return f"{html_body}\n{pixel}" if html_body else pixel


def _embed_cid_images(msg_root, html_body, campaign):
    cid_refs = set(re.findall(r'cid:([\w.-]+)', html_body))
    if not cid_refs:
        return
    template = campaign.template
    if not template:
        return

    def _attach(cid, file_field):
        if cid not in cid_refs:
            return
        if not file_field:
            return
        try:
            with open(file_field.path, 'rb') as f:
                img_data = f.read()
            mime = MIMEImage(img_data)
            mime.add_header('Content-ID', f'<{cid}>')
            mime.add_header('Content-Disposition', 'inline', filename=cid)
            mime.add_header('X-Attachment-Id', cid)
            msg_root.attach(mime)
        except (FileNotFoundError, OSError, IOError):
            logger.warning(f"Failed to embed CID image {cid}: file not found or unreadable")

    # Embed header_logo / footer_logo
    _attach('header_logo', template.header_logo)
    _attach('footer_logo', template.footer_logo)

    # Embed TemplateImage objects referenced via cid:name
    for img in template.images.filter(cid_name__in=cid_refs):
        _attach(img.cid_name, img.image)


def _attach_campaign_files(msg_root, campaign):
    """Attach campaign files. If no attachments, returns msg_root unchanged.
    If attachments exist, wraps in multipart/mixed and attaches files."""
    if not campaign.pk:
        return msg_root
    attachments_qs = campaign.attachments.all()
    if not attachments_qs:
        return msg_root

    outer = MIMEMultipart('mixed')
    # Copy headers from inner to outer
    for h in msg_root.keys():
        outer[h] = msg_root[h]
    outer.attach(msg_root)

    for att in attachments_qs:
        if not att.file:
            continue
        try:
            with open(att.file.path, 'rb') as f:
                file_data = f.read()
            part = MIMEApplication(file_data)
            part.add_header(
                'Content-Disposition', 'attachment',
                filename=att.original_filename or 'attachment',
            )
            outer.attach(part)
        except (FileNotFoundError, OSError, IOError):
            continue

    return outer


def update_campaign_unique_open_count(campaign) -> None:
    unique_opens = campaign.engagements.filter(opened_at__isnull=False).aggregate(count=Count('id'))['count'] or 0
    campaign.open_count = unique_opens
    campaign.save(update_fields=['open_count', 'updated_at'])


# ──────────────────────────────────────────────
#  Variable context & replacement
# ──────────────────────────────────────────────

def _build_variable_context(recipient_email: str, recipient_context: dict = None) -> dict:
    context = {}
    if recipient_context and recipient_email:
        context = dict(recipient_context.get(recipient_email, {}))
    try:
        from apps.contacts.models import Contact
        contact = Contact.objects.filter(email=recipient_email).first()
        if contact:
            context.setdefault('first_name', contact.first_name or '')
            context.setdefault('last_name', contact.last_name or '')
            context.setdefault('email', contact.email)
            for cfv in contact.custom_values.all():
                context.setdefault(cfv.field.name, cfv.value)
    except Exception:
        logger.debug(f"Failed to load contact context for {recipient_email}")
    context.setdefault('first_name', 'there')
    context.setdefault('last_name', '')
    context.setdefault('email', recipient_email)
    context.setdefault('company_name', 'our team')
    context.setdefault('client_name', 'Valued Customer')
    context.setdefault('voucher', 'your discount')
    context.setdefault('subject', 'Your Email')
    context.setdefault('month', datetime.now().strftime('%B %Y'))
    context.setdefault('year', str(datetime.now().year))
    return context


def replace_variables(text: str, recipient_email: str, recipient_context: dict = None) -> str:
    if not text:
        return text
    has_double = '{{' in text
    has_single = '{' in text
    if not has_double and not has_single:
        return text
    context = _build_variable_context(recipient_email, recipient_context)
    result = text
    for key, val in context.items():
        result = result.replace('{{ ' + key + ' }}', str(val)).replace('{{' + key + '}}', str(val))
        result = result.replace('{ ' + key + ' }', str(val)).replace('{' + key + '}', str(val))
    return result


# ──────────────────────────────────────────────
#  HTML structure helpers
# ──────────────────────────────────────────────

def _is_full_html(html_body: str) -> bool:
    return bool(re.search(r'<html[^>]*>', html_body, re.IGNORECASE)) and \
           bool(re.search(r'<body[^>]*>', html_body, re.IGNORECASE))


DEFAULT_LOGO_URL = 'https://cdn.jsdelivr.net/gh/anomalyco/mailflow-assets@main/logo.png'


def _render_header_footer_html(template) -> tuple:
    header_text = (template.header_text or '').strip() if template else ''
    footer_text = (template.footer_text or '').strip() if template else ''
    has_header_logo = bool(template and template.header_logo)
    has_footer_logo = bool(template and template.footer_logo)

    header_html = ''
    if has_header_logo or header_text or not template:
        header_html = (
            '<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" '
            'style="border-collapse:collapse">'
            '<tr><td style="text-align:center;padding:20px 30px;border-bottom:1px solid ' + C.EMAIL_BORDER_COLOR + ';">'
        )
        if has_header_logo:
            header_html += (
                '<img src="cid:header_logo" alt="" '
                'style="display:block;outline:none;border:0;'
                'max-height:' + str(C.HEADER_LOGO_MAX_HEIGHT) + 'px;'
                'max-width:100%;height:auto;width:auto;'
                'margin:0 auto 8px" />'
            )
        elif not template:
            header_html += (
                '<img src="' + DEFAULT_LOGO_URL + '" alt="MailFlow" '
                'style="display:block;outline:none;border:0;'
                'max-height:40px;max-width:100%;height:auto;width:auto;'
                'margin:0 auto 8px" />'
            )
        if header_text:
            escaped = header_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            header_html += (
                f'<p style="font-family:{C.EMAIL_FONT_FAMILY};font-size:13px;color:{C.EMAIL_TEXT_MUTED};margin:4px 0 0;'
                f'line-height:{C.EMAIL_LINE_HEIGHT}">{escaped}</p>'
            )
        header_html += '</td></tr></table>'

    footer_html = ''
    if has_footer_logo or footer_text:
        unsub = '{{unsubscribe_url}}'
        footer_html = (
            '<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" '
            'style="border-collapse:collapse">'
            '<tr><td style="text-align:center;padding:20px 30px;border-top:1px solid ' + C.EMAIL_BORDER_COLOR + ';'
            f'font-family:{C.EMAIL_FONT_FAMILY};font-size:12px;color:{C.EMAIL_TEXT_LIGHT};">'
        )
        if has_footer_logo:
            footer_html += (
                '<img src="cid:footer_logo" alt="" '
                'style="display:block;outline:none;border:0;'
                'max-height:' + str(C.FOOTER_LOGO_MAX_HEIGHT) + 'px;'
                'max-width:100%;height:auto;width:auto;'
                'margin:0 auto 8px" />'
            )
        if footer_text:
            escaped = footer_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            footer_html += (
                f'<p style="margin:4px 0;line-height:{C.EMAIL_LINE_HEIGHT}">{escaped}</p>'
            )
        footer_html += (
            f'<p style="margin:12px 0 0;font-size:11px">'
            f'<a href="{unsub}" style="color:{C.EMAIL_TEXT_LIGHT};text-decoration:underline">'
            f'Unsubscribe</a></p>'
        )
        footer_html += '</td></tr></table>'

    return header_html, footer_html


def _inject_into_body(html_body: str, injection: str) -> str:
    m = re.search(r'(<body[^>]*>)', html_body, re.DOTALL | re.IGNORECASE)
    if m:
        return html_body.replace(m.group(1), m.group(1) + '\n' + injection + '\n')
    return injection + '\n' + html_body


def _append_to_body(html_body: str, injection: str) -> str:
    m = re.search(r'(</body>)', html_body, re.DOTALL | re.IGNORECASE)
    if m:
        return html_body.replace(m.group(1), '\n' + injection + '\n' + m.group(1))
    return html_body + '\n' + injection


# ──────────────────────────────────────────────
#  ✦  UNIFIED RENDERING PIPELINE  ✦
# ──────────────────────────────────────────────

def render_html(
    body_html: str,
    template,
    recipient_email: str = None,
    recipient_context: dict = None,
    include_tracking: bool = False,
    base_url: str = '',
    resolve_cids: bool = True,
):
    """
    Core single pipeline — used for BOTH preview and send.

    Always returns (rendered_html, plain_text, tracking_token_or_None).
    """
    tracking_token = None
    html_body = (body_html or '').strip()
    if not html_body:
        return '', '', None

    # 1. Detect full HTML or fragment
    if not _is_full_html(html_body):
        html_body = (
            '<!DOCTYPE html>\n'
            '<html>\n'
            '<head><meta charset="UTF-8"></head>\n'
            '<body>\n' + html_body + '\n</body>\n</html>'
        )

    # 2. Inject header / footer inside <body>
    header_html, footer_html = _render_header_footer_html(template)
    if header_html:
        html_body = _inject_into_body(html_body, header_html)
    if footer_html:
        html_body = _append_to_body(html_body, footer_html)

    # 3. Replace placeholders (body + header/footer text all covered)
    if recipient_email:
        html_body = replace_variables(html_body, recipient_email, recipient_context)

    # 4. Sanitize (remove dangerous tags; preserve email-structural tags)
    html_body = sanitize_html(html_body)

    # 5. Build plain-text fallback
    plain_text = _html_to_text(html_body)

    # 6. Fix images for email compatibility
    html_body = re.sub(
        r'<img\s(?![^>]*style=)',
        '<img style="display:block;outline:none;border:0;max-width:100%;height:auto" ',
        html_body,
        flags=re.IGNORECASE,
    )

    # 7. Ensure <body> has proper inline styles for email clients
    html_body = re.sub(
        r'(<body(?:(?!style=)[^>])*)>',
        lambda m: (
            m.group(1)
            + ' style="margin:0;padding:0;background-color:#f4f4f5;'
            + 'font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',Roboto,Helvetica,Arial,sans-serif;'
            + 'line-height:1.6;color:#1e293b"'
            + '>'
        ),
        html_body,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # 8. Tracking (send only)
    if include_tracking and base_url:
        # Use simple UUID tokens for tracking
        tracking_token = uuid4().hex
        html_body = _inject_link_tracking(html_body, tracking_token, base_url)
        html_body = _inject_open_pixel(html_body, tracking_token, base_url)

    # 9. Resolve CID images (if requested and we have a template)
    if resolve_cids and template and template.images.exists():
        # Replace cid: references with actual URLs
        cid_refs = template.get_all_cid_names()
        for img in template.images.filter(cid_name__in=cid_refs):
            if img.image:
                try:
                    html_body = html_body.replace(f'cid:{img.cid_name}', img.image.url)
                except Exception:
                    pass
        
        # Handle header/footer logo CID refs
        if template.header_logo:
            try:
                html_body = html_body.replace('cid:header_logo', template.header_logo.url)
            except Exception:
                pass
        
        if template.footer_logo:
            try:
                html_body = html_body.replace('cid:footer_logo', template.footer_logo.url)
            except Exception:
                pass
        
        # Strip remaining unresolved cid: refs to avoid CSP violations
        html_body = re.sub(r'cid:\S+', '', html_body)

    # 10. Resolve unsubscribe link placeholder
    if tracking_token and base_url:
        unsub_url = f'{base_url}/unsubscribe/{tracking_token}/'
        html_body = html_body.replace('{{unsubscribe_url}}', unsub_url)
        plain_text = plain_text.replace('{{unsubscribe_url}}', unsub_url)
    else:
        html_body = html_body.replace('{{unsubscribe_url}}', '#')
        plain_text = plain_text.replace('{{unsubscribe_url}}', '#')

    return html_body, plain_text, tracking_token


def _render_email_html(campaign, recipient_email=None, include_tracking=True, base_url=''):
    """Campaign convenience wrapper around render_html."""
    body = campaign.body_html or ''
    template = campaign.template
    ctx = campaign.recipient_context or {}
    return render_html(body, template, recipient_email, ctx, include_tracking, base_url)


# ──────────────────────────────────────────────
#  Send implementations
# ──────────────────────────────────────────────

def _build_mime_message(html_body, plain_text, subject, from_header, to_email, reply_to, campaign_id=None):
    """Build a multipart/related MIME message with all required headers."""
    # Extract domain from from_header for Message-ID
    domain = 'mailflow.ai'
    m = re.search(r'@([^>]+)', from_header)
    if m:
        domain = m.group(1).strip().lower()

    msg_root = MIMEMultipart('related')
    msg_root['Subject'] = subject
    msg_root['From'] = from_header
    msg_root['To'] = to_email
    msg_root['Message-ID'] = make_msgid(domain=domain)
    msg_root['Date'] = formatdate(localtime=True)
    msg_root['MIME-Version'] = '1.0'
    # Headers for inbox placement (avoid Promotions tab)
    msg_root['X-Priority'] = C.EMAIL_PRIORITY
    msg_root['Importance'] = C.EMAIL_IMPORTANCE
    msg_root['X-Mailer'] = C.EMAIL_MAILER
    if campaign_id:
        msg_root['Feedback-ID'] = f'{campaign_id}:{domain}'
    if reply_to:
        msg_root['Reply-To'] = reply_to

    msg_alternative = MIMEMultipart('alternative')
    msg_root.attach(msg_alternative)
    if plain_text:
        msg_alternative.attach(MIMEText(plain_text, 'plain'))
    if html_body:
        msg_alternative.attach(MIMEText(html_body, 'html'))
    return msg_root


def _get_smtp_connection(sender):
    if sender.smtp_port == 465:
        return smtplib.SMTP_SSL(sender.smtp_host, sender.smtp_port, timeout=20)
    client = smtplib.SMTP(sender.smtp_host, sender.smtp_port, timeout=20)
    if sender.use_tls:
        client.starttls(context=ssl.create_default_context())
    return client


def _send_single_recipient(
    recipient, subject, body_html, variant_obj,
    campaign, sender, template, ctx, from_header, reply_to,
    smtp_password, base_url,
):
    """Send one email and record engagement. Returns (True, None) or (False, error_msg)."""
    from django.db import models
    subject_rendered = replace_variables(subject, recipient, ctx)
    html_out, text_out, tracking_token = render_html(
        body_html=body_html, template=template,
        recipient_email=recipient, recipient_context=ctx,
        include_tracking=True, base_url=base_url,
    )
    if not html_out:
        return False, 'No HTML content generated.'
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with _get_smtp_connection(sender) as server:
                server.login(sender.username, smtp_password)
                msg = _build_mime_message(
                    html_out, text_out, subject_rendered,
                    from_header, recipient, reply_to,
                    campaign_id=campaign.id,
                )
                _embed_cid_images(msg, html_out or '', campaign)
                msg = _attach_campaign_files(msg, campaign)
                server.sendmail(from_header, [recipient], msg.as_string())
            
            EmailEngagement.objects.create(
                campaign=campaign, campaign_variant=variant_obj,
                recipient_email=recipient, tracking_token=tracking_token,
            )
            if variant_obj:
                variant_obj.sent_count = models.F('sent_count') + 1
                variant_obj.save(update_fields=['sent_count'])
            if sender.send_delay_seconds > 0:
                time.sleep(sender.send_delay_seconds)
            return True, None
            
        except smtplib.SMTPAuthenticationError:
            raise ValueError(
                "Gmail authentication failed. You must use an App Password, not your regular "
                "Gmail password. Generate one at: https://myaccount.google.com/apppasswords"
            )
        except smtplib.SMTPRecipientsRefused as exc:
            return False, f"Recipient refused: {exc}"
        except (smtplib.SMTPException, ConnectionError, OSError) as e:
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) + 1
                logger.warning(f"Send attempt {attempt + 1} failed for {recipient}: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                return False, f"Failed after {max_retries} attempts: {str(e)}"
    
    return False, "Unknown error occurred"


def send_campaign_with_smtp(campaign, base_url: str, recipients_override=None):
    from django.db import models
    sender = campaign.sender
    if not sender:
        raise ValueError('Select a sender profile before sending.')

    recipients = recipients_override if recipients_override is not None else campaign.get_recipient_list()
    recipients = [email.strip().lower() for email in recipients if email and email.strip()]
    if not recipients:
        raise ValueError('Add at least one recipient email before sending.')

    sender.reset_daily_quota_if_needed()
    available_quota = max(sender.daily_limit - sender.emails_sent_today, 0)
    if available_quota == 0:
        raise ValueError('Sender daily limit reached. Increase limit or wait until next reset.')

    # Build job list
    jobs = []
    if campaign.is_ab_test:
        variants = list(campaign.variants.all().order_by('label'))
        if len(variants) < 2:
            raise ValueError('A/B test campaigns must have at least 2 variants created.')
        var_a, var_b = variants[0], variants[1]

        if campaign.ab_test_status == 'pending':
            total_count = len(recipients)
            count_a = max(1, int(total_count * var_a.percentage / 100))
            count_b = max(1, int(total_count * var_b.percentage / 100))
            random.shuffle(recipients)
            for r in recipients[:count_a]:
                jobs.append((r, var_a.subject, var_a.body_html, var_a))
            for r in recipients[count_a:count_a + count_b]:
                jobs.append((r, var_b.subject, var_b.body_html, var_b))
            campaign.ab_test_status = 'running'
            campaign.save(update_fields=['ab_test_status', 'updated_at'])
            try:
                from apps.campaigns.tasks import evaluate_ab_test_winner
                evaluate_ab_test_winner.apply_async(
                    (campaign.id, campaign.workspace_id), countdown=campaign.ab_test_duration_hours * 3600
                )
            except Exception:
                logger.warning(f"Failed to schedule ab_test evaluation for campaign {campaign.id}")
        elif campaign.ab_test_status == 'running':
            raise ValueError(
                'A/B test is currently running. Please wait for the test to complete '
                'or end the test manually in the analytics dashboard to deliver the winner.'
            )
        elif campaign.ab_test_status == 'completed':
            winner = campaign.winner_variant or var_a
            sent_emails = set(campaign.engagements.values_list('recipient_email', flat=True))
            for r in recipients:
                if r not in sent_emails:
                    jobs.append((r, winner.subject, winner.body_html, winner))
    else:
        for r in recipients:
            jobs.append((r, campaign.subject, campaign.body_html, None))

    jobs = jobs[:available_quota]
    if not jobs:
        return 0, 0, "No unsent recipients within quota limits."

    smtp_password = sender.get_password()
    if not smtp_password:
        raise ValueError('Could not decrypt SMTP password for this sender. Re-save sender credentials.')

    from_name = (campaign.from_name or sender.display_name or '').strip()
    from_header = f'{from_name} <{sender.from_email}>' if from_name else sender.from_email
    ctx = campaign.recipient_context or {}
    template = campaign.template

    sent_count = 0
    failed_count = len(recipients) - len(jobs)
    last_error = None

    for recipient, subj, body, variant_obj in jobs:
        ok, err = _send_single_recipient(
            recipient, subj, body, variant_obj,
            campaign, sender, template, ctx, from_header,
            campaign.reply_to or sender.from_email,
            smtp_password, base_url,
        )
        if ok:
            sent_count += 1
        else:
            failed_count += 1
            last_error = err

    from apps.senders.models import Sender
    Sender.objects.filter(id=sender.id).update(
        emails_sent_today=F('emails_sent_today') + sent_count,
        last_reset_date=timezone.now().date()
    )
    sender.refresh_from_db()
    return sent_count, failed_count, last_error


def send_test_email_with_smtp(campaign, test_email: str):
    sender = campaign.sender
    if not sender:
        raise ValueError('Select a sender profile before sending a test email.')

    recipient = (test_email or '').strip().lower()
    if not recipient:
        raise ValueError('Provide a test email address.')

    smtp_password = sender.get_password()
    if not smtp_password:
        raise ValueError('Could not decrypt SMTP password for this sender. Re-save sender credentials.')

    ctx = campaign.recipient_context or {}

    html_out, text_out, _ = _render_email_html(
        campaign=campaign,
        recipient_email=recipient,
        include_tracking=False,
    )

    if not html_out and not text_out:
        raise ValueError('Message content is required before sending a test email.')

    from_name = (campaign.from_name or sender.display_name or '').strip()
    from_header = f'{from_name} <{sender.from_email}>' if from_name else sender.from_email
    reply_to = campaign.reply_to or sender.from_email

    sender.reset_daily_quota_if_needed()
    available_quota = max(sender.daily_limit - sender.emails_sent_today, 0)
    if available_quota == 0:
        raise ValueError('Sender daily limit reached. Increase limit or wait until next reset.')

    subject = replace_variables(campaign.subject or 'Test Campaign', recipient, ctx)

    with _get_smtp_connection(sender) as server:
        server.login(sender.username, smtp_password)
        msg = _build_mime_message(html_out, text_out, f'[TEST] {subject}', from_header, recipient, reply_to)
        _embed_cid_images(msg, html_out or '', campaign)
        msg = _attach_campaign_files(msg, campaign)
        server.sendmail(from_header, [recipient], msg.as_string())

    sender.emails_sent_today += 1
    sender.last_reset_date = timezone.now().date()
    sender.save(update_fields=['emails_sent_today', 'last_reset_date'])
