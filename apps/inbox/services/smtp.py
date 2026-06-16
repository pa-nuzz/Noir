import imaplib
import logging
import smtplib
import ssl
import time
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, getaddresses, make_msgid

from django.db.models import F

from apps.senders.models import Sender
from apps.inbox.services.sync import IMAP_SERVERS, _find_sent_folder
from apps.workspaces.query_helpers import filter_by_context

logger = logging.getLogger(__name__)


class EmailSendError(Exception):
    """User-facing send failure."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


@dataclass
class SendResult:
    recipient: str
    message: MIMEMultipart


def parse_address_list(raw):
    return [addr for _, addr in getaddresses([raw or '']) if addr]


def send_draft_reply(draft, request, body, to_address='', cc_addresses='', bcc_addresses=''):
    if not body:
        raise EmailSendError('Draft has no content to send.')
    if not draft.original_message:
        raise EmailSendError('Original message not found.')

    to_list = parse_address_list(to_address) or [draft.original_message.from_email]
    cc_list = parse_address_list(cc_addresses)
    bcc_list = parse_address_list(bcc_addresses)
    to_list = [addr for addr in to_list if addr]
    if not to_list:
        raise EmailSendError('No recipient found.')

    sender, smtp_password = _get_ready_sender(request)
    subject = f"Re: {draft.thread.subject}" if draft.thread.subject else 'Re:'
    msg = _build_message(
        sender=sender,
        subject=subject,
        body=body,
        to_addresses=to_list,
        cc_addresses=cc_list,
        mailer='MailFlow AI',
    )

    recipients = [*to_list, *cc_list, *bcc_list]
    _send_via_smtp(sender, smtp_password, msg, recipients)
    Sender.objects.filter(pk=sender.pk).update(emails_sent_today=F('emails_sent_today') + 1)

    draft.status = 'sent'
    draft.save(update_fields=['status', 'updated_at'])
    _append_to_sent_folder(draft.thread.inbox, msg)

    return SendResult(recipient=', '.join(to_list), message=msg)


def send_test_draft(draft, request, body):
    if not body:
        raise EmailSendError('Draft has no content to send.')
    if not draft.original_message:
        raise EmailSendError('Original message not found.')
    if not request.user.email:
        raise EmailSendError('Your user account does not have an email address set.')

    sender, smtp_password = _get_ready_sender(request)
    subject = f"[TEST] Re: {draft.thread.subject}" if draft.thread.subject else '[TEST]'
    test_header = (
        "<div style='background:#fef3c7;border-left:4px solid #f59e0b;"
        "padding:12px;margin-bottom:20px;'>"
        "<strong>TEST EMAIL</strong> - This is a test copy. "
        "The original recipient will not receive this.</div>"
    )
    msg = _build_message(
        sender=sender,
        subject=subject,
        body=test_header + body,
        to_addresses=[request.user.email],
        cc_addresses=[],
        mailer='MailFlow AI (Test)',
    )

    _send_via_smtp(sender, smtp_password, msg, [request.user.email])
    Sender.objects.filter(pk=sender.pk).update(emails_sent_today=F('emails_sent_today') + 1)
    return SendResult(recipient=request.user.email, message=msg)


def _get_ready_sender(request):
    sender = filter_by_context(request, Sender.objects.filter(is_active=True)).first()
    if not sender:
        raise EmailSendError('No active SMTP sender found. Configure a sender first.')

    sender.reset_daily_quota_if_needed()
    if sender.is_limit_reached:
        raise EmailSendError(f'Daily sending limit ({sender.daily_limit}) reached for {sender.from_email}.')

    smtp_password = sender.get_password()
    if not smtp_password:
        raise EmailSendError('Could not decrypt sender password. Re-save sender credentials.')

    return sender, smtp_password


def _build_message(sender, subject, body, to_addresses, cc_addresses, mailer):
    domain = sender.from_email.split('@')[-1] if '@' in sender.from_email else 'mailflow.ai'
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"{sender.display_name} <{sender.from_email}>"
    msg['To'] = ', '.join(to_addresses)
    if cc_addresses:
        msg['Cc'] = ', '.join(cc_addresses)
    msg['Message-ID'] = make_msgid(domain=domain)
    msg['Date'] = formatdate(localtime=True)
    msg['MIME-Version'] = '1.0'
    msg['X-Priority'] = '3'
    msg['X-Mailer'] = mailer
    if sender.reply_to:
        msg['Reply-To'] = sender.reply_to
    msg.attach(MIMEText(body, 'html' if '<' in body else 'plain'))
    return msg


def _send_via_smtp(sender, smtp_password, msg, recipients, max_retries=3):
    recipients = [addr for addr in recipients if addr]
    if not recipients:
        raise EmailSendError('No recipient found.')

    for attempt in range(max_retries):
        try:
            if sender.smtp_port == 465:
                with smtplib.SMTP_SSL(sender.smtp_host, sender.smtp_port, timeout=30) as server:
                    server.login(sender.username, smtp_password)
                    server.sendmail(sender.from_email, recipients, msg.as_string())
            else:
                with smtplib.SMTP(sender.smtp_host, sender.smtp_port, timeout=30) as server:
                    server.ehlo()
                    if sender.use_tls:
                        server.starttls(context=ssl.create_default_context())
                        server.ehlo()
                    server.login(sender.username, smtp_password)
                    server.sendmail(sender.from_email, recipients, msg.as_string())
            return
        except smtplib.SMTPAuthenticationError as exc:
            error_text = str(exc)
            logger.warning("SMTP authentication failed for sender %s: %s", sender.id, exc)
            if '534' in error_text:
                raise EmailSendError(
                    'SMTP authentication failed: App Password required. For Gmail, create an App Password and use that instead of your regular password.'
                )
            raise EmailSendError('SMTP authentication failed: Invalid username or password. Please re-save your sender credentials in Settings.')
        except smtplib.SMTPRecipientsRefused as exc:
            logger.warning("SMTP recipient refused for sender %s: %s", sender.id, exc)
            recipient = next(iter(exc.recipients.keys()), 'recipient') if exc.recipients else 'recipient'
            raise EmailSendError(f'Recipient address rejected: {recipient}. Please verify the email address is correct.')
        except smtplib.SMTPServerDisconnected as exc:
            logger.warning("SMTP server disconnected for sender %s: %s", sender.id, exc)
            raise EmailSendError('SMTP server disconnected unexpectedly. Please check your connection settings and try again.')
        except (smtplib.SMTPException, ConnectionError, TimeoutError, OSError) as exc:
            logger.warning("SMTP send attempt %s failed for sender %s: %s", attempt + 1, sender.id, exc)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise EmailSendError(_friendly_send_error(str(exc)))


def _append_to_sent_folder(inbox, msg):
    inbox_password = inbox.get_token()
    if not inbox_password:
        return
    try:
        server_info = IMAP_SERVERS.get(inbox.provider)
        if not server_info:
            return
        host, port = server_info
        imap_conn = imaplib.IMAP4_SSL(host, port, timeout=20)
        try:
            imap_conn.login(inbox.email_address, inbox_password)
            sent_folder = _find_sent_folder(imap_conn)
            if sent_folder:
                raw_msg = msg.as_string()
                imap_conn.append(
                    sent_folder,
                    '\\Sent',
                    imaplib.Time2Internaldate(time.time()),
                    raw_msg.encode('utf-8'),
                )
        finally:
            imap_conn.logout()
    except Exception as exc:
        logger.warning("Could not append draft reply to IMAP sent folder for inbox %s: %s", inbox.id, exc)


def _friendly_send_error(error_text):
    lowered = (error_text or '').lower()
    if 'authentication' in lowered or 'auth' in lowered:
        return 'SMTP authentication failed. Please verify your credentials in Settings.'
    if 'connection' in lowered or 'timeout' in lowered:
        return 'SMTP connection timed out. Check your internet connection and SMTP server settings.'
    if 'tls' in lowered or 'ssl' in lowered:
        return 'TLS/SSL handshake failed. Try enabling or disabling TLS in your sender settings.'
    if 'recipient' in lowered:
        return 'Recipient address was rejected. Please verify the email address is correct.'
    return f'Failed to send email: {error_text}'
