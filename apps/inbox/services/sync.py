from apps.inbox.models import EmailInbox, EmailMessage, EmailThread
import base64
import email
import imaplib
import logging
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.utils import getaddresses
from html.parser import HTMLParser

from django.db import transaction
from django.db.models import F
from django.utils import timezone as django_timezone


class _SnippetStripper(HTMLParser):
    """HTML parser that extracts clean text, ignoring style/script content."""

    def __init__(self):
        super().__init__()
        self._text = []
        self._skip = False
        self._skip_tags = {'style', 'script', 'noscript'}

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._skip = True

    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self._text.append(data)

    def get_text(self):
        return ''.join(self._text)


def clean_snippet(raw, max_length=120):
    """Strip HTML, CSS, scripts, and zero-width chars from text for preview."""
    if not raw:
        return ''
    parser = _SnippetStripper()
    try:
        parser.feed(raw)
        text = parser.get_text()
    except Exception:
        text = re.sub(r'<style[^>]*>.*?</style>', '',
                      raw, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<script[^>]*>.*?</script>', '',
                      text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)

    text = re.sub(r'\s+', ' ', text).strip()

    # Strip zero-width characters
    zero_width = re.compile(
        '[\u200b\u200c\u200d\u200e\u200f\u2028\u2029\u2060\u2061\u2062\u2063\u2064\ufeff]')
    text = zero_width.sub('', text)

    if len(text) > max_length:
        text = text[:max_length].rstrip() + '...'
    return text


logger = logging.getLogger(__name__)

IMAP_SERVERS = {
    'gmail': ('imap.gmail.com', 993),
    'outlook': ('outlook.office365.com', 993),
}


def _find_sent_folder(mail):
    """Find the Sent folder name dynamically from IMAP LIST response."""
    try:
        status, folders = mail.list()
        if status == 'OK':
            for folder_data in folders:
                decoded = folder_data.decode(errors='replace') if isinstance(
                    folder_data, bytes) else folder_data
                if '\\Sent' in decoded:
                    parts = decoded.split('"/"')
                    if len(parts) > 1:
                        name = parts[-1].strip().strip('"')
                        if name:
                            return name
    except Exception:
        pass
    return None


def sync_inbox(inbox: EmailInbox, password: str = '') -> int:
    """Fetch recent emails from an inbox via IMAP and store them.
    Returns the number of new messages fetched.
    """
    server_info = IMAP_SERVERS.get(inbox.provider)
    if not server_info:
        logger.warning(
            f"Unknown provider for inbox {inbox.id}: {inbox.provider}")
        return 0

    password = password or inbox.get_token()
    if not password:
        logger.warning(
            f"No password/token for inbox {inbox.id} ({inbox.email_address})")
        return 0

    host, port = server_info
    new_count = 0

    try:
        import socket
        mail = imaplib.IMAP4_SSL(host, port, timeout=30)
        mail.socket().settimeout(30)
        mail.login(inbox.email_address, password)

        # Sync incoming emails from INBOX
        select_status, select_data = mail.select('INBOX')
        if select_status != 'OK':
            logger.error(
                f"IMAP SELECT failed for {inbox.email_address}: {select_status} {select_data}")
            mail.logout()
            inbox.last_sync_status = 'error'
            inbox.last_sync_error = 'Could not open inbox folder. The account may not have any emails.'
            inbox.last_synced_at = django_timezone.now()
            inbox.save(update_fields=['last_sync_status',
                       'last_sync_error', 'last_synced_at'])
            return 0
        # Always search at least the last 30 days to ensure backlog sync and catch-up works perfectly.
        start_date = django_timezone.now() - timedelta(days=30)
        if inbox.last_synced_at and inbox.last_synced_at < start_date:
            # If last_synced_at is even older, search from last_synced_at but cap at 60 days to avoid performance issues
            max_backlog = django_timezone.now() - timedelta(days=60)
            if inbox.last_synced_at < max_backlog:
                start_date = max_backlog
            else:
                start_date = inbox.last_synced_at
        since_date = start_date.strftime('%d-%b-%Y')
        search_criteria = f'SINCE {since_date}'
        status, message_ids = mail.search(None, search_criteria)
        if status != 'OK':
            mail.logout()
            return 0

        ids = message_ids[0].split() if message_ids[0] else []
        ids.reverse()  # Process newest first so the user gets the latest emails immediately

        # Process incoming messages
        for mid in ids:
            if new_count >= 50:
                break
            try:
                # 1. Fetch Message-ID header first to check if we already have this message
                status, header_data = mail.fetch(mid, '(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])')
                if status == 'OK':
                    msg_id_val = None
                    for part in header_data:
                        if isinstance(part, tuple):
                            header_msg = email.message_from_bytes(part[1])
                            msg_id_val = header_msg.get('Message-ID')
                            if msg_id_val:
                                msg_id_val = msg_id_val.strip()
                                break
                    if msg_id_val:
                        from apps.inbox.models import EmailMessage
                        if EmailMessage.objects.filter(thread__inbox=inbox, message_id=msg_id_val).exists():
                            # Already imported, skip full fetch
                            continue

                # 2. Fetch full body if it's a new email
                status, msg_data = mail.fetch(mid, '(BODY.PEEK[])')
                if status != 'OK':
                    continue
                for part in msg_data:
                    if isinstance(part, tuple):
                        raw = email.message_from_bytes(part[1])
                        if _process_email(inbox, raw):
                            new_count += 1
            except Exception as e:
                logger.error(f"Error processing message {mid}: {e}")

        # Sync sent emails from SENT folder
        sent_folder = _find_sent_folder(mail)
        if sent_folder:
            select_status, select_data = mail.select(mail._quote(sent_folder))
            if select_status != 'OK':
                logger.warning(
                    f"Failed to select SENT folder '{sent_folder}' for {inbox.email_address}: {select_status} {select_data}")
            else:
                status, message_ids = mail.search(None, search_criteria)
                if status == 'OK':
                    sent_ids = message_ids[0].split() if message_ids[0] else []
                    sent_ids.reverse()  # Process newest first
                    for mid in sent_ids:
                        if new_count >= 50:
                            break
                        try:
                            # 1. Fetch Message-ID header first to check if we already have this message
                            status, header_data = mail.fetch(mid, '(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])')
                            if status == 'OK':
                                msg_id_val = None
                                for part in header_data:
                                    if isinstance(part, tuple):
                                        header_msg = email.message_from_bytes(part[1])
                                        msg_id_val = header_msg.get('Message-ID')
                                        if msg_id_val:
                                            msg_id_val = msg_id_val.strip()
                                            break
                                if msg_id_val:
                                    from apps.inbox.models import EmailMessage
                                    if EmailMessage.objects.filter(thread__inbox=inbox, message_id=msg_id_val).exists():
                                        # Already imported, skip full fetch
                                        continue

                            # 2. Fetch full body
                            status, msg_data = mail.fetch(mid, '(BODY.PEEK[])')
                            if status != 'OK':
                                continue
                            for part in msg_data:
                                if isinstance(part, tuple):
                                    raw = email.message_from_bytes(part[1])
                                    if _process_email(inbox, raw, is_incoming=False):
                                        new_count += 1
                        except Exception as e:
                            logger.error(
                                f"Error processing sent message {mid}: {e}")

        try:
            mail.close()
        except Exception:
            pass
        mail.logout()

        inbox.last_synced_at = django_timezone.now()
        inbox.last_sync_status = 'success'
        inbox.last_sync_error = ''
        inbox.save(update_fields=['last_synced_at',
                   'last_sync_status', 'last_sync_error'])

    except imaplib.IMAP4.error as e:
        err = str(e)
        logger.error(f"IMAP error for {inbox.email_address}: {err}")
        if 'authentication' in err.lower() or 'login' in err.lower() or 'invalid' in err.lower():
            error_msg = 'Login failed. Check your email and app password.'
        elif 'timeout' in err.lower() or 'connection' in err.lower():
            error_msg = 'Could not connect to the email server. Try again later.'
        else:
            error_msg = 'Sync failed. Check your inbox settings and try again.'
        inbox.last_sync_status = 'error'
        inbox.last_sync_error = error_msg
        inbox.last_synced_at = django_timezone.now()
        inbox.save(update_fields=['last_sync_status',
                   'last_sync_error', 'last_synced_at'])
    except Exception as e:
        err = str(e)
        logger.error(f"Sync error for {inbox.email_address}: {err}")
        if 'timeout' in err.lower() or 'connection' in err.lower():
            error_msg = 'Connection timed out. Try again later.'
        else:
            error_msg = 'Sync failed. Please try again.'
        inbox.last_sync_status = 'error'
        inbox.last_sync_error = error_msg
        inbox.last_synced_at = django_timezone.now()
        inbox.save(update_fields=['last_sync_status',
                   'last_sync_error', 'last_synced_at'])

    # Trigger inbox.synced webhook
    from apps.webhooks.utils import dispatch_webhook_event
    workspace_id = inbox.workspace_id
    if workspace_id:
        dispatch_webhook_event(
            workspace_id=workspace_id,
            event_type='inbox.synced',
            payload={
                'inbox_id': inbox.id,
                'email_address': inbox.email_address,
                'workspace_id': workspace_id,
                'provider': inbox.provider,
                'new_messages_count': new_count,
                'last_synced_at': inbox.last_synced_at.isoformat() if inbox.last_synced_at else None,
                'status': inbox.last_sync_status,
            }
        )

    return new_count


def _process_email(inbox, raw_message, is_incoming=True):
    msg = raw_message

    subject = _decode_header_value(msg.get('Subject', '(No Subject)'))
    from_val = msg.get('From', '')
    from_email, from_name = _parse_email(from_val)
    to_val = msg.get('To', '')
    cc_val = msg.get('Cc', '')
    bcc_val = msg.get('Bcc', '')
    date_str = msg.get('Date', '')

    received_at = _parse_date(date_str) or django_timezone.now()

    body_text = ''
    body_html = ''
    inline_images = {}

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            cdisp = str(part.get('Content-Disposition', ''))

            # Skip attachments (unless inline)
            if 'attachment' in cdisp and 'inline' not in cdisp:
                continue

            if ctype == 'text/plain':
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body_text = payload.decode('utf-8', errors='replace')
                except Exception as e:
                    logger.debug(f"Error decoding text/plain part: {e}")
                    body_text = ''
            elif ctype == 'text/html':
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        body_html = payload.decode('utf-8', errors='replace')
                except Exception as e:
                    logger.debug(f"Error decoding text/html part: {e}")
                    body_html = ''
            elif ctype.startswith('image/') and 'inline' in cdisp:
                cid = part.get('Content-ID', '')
                if cid:
                    cid = cid.strip('<>')
                    try:
                        img_data = part.get_payload(decode=True)
                        if img_data and len(img_data) <= 150 * 1024:
                            b64 = base64.b64encode(img_data).decode()
                            inline_images[cid] = f'data:{ctype};base64,{b64}'
                    except Exception as e:
                        logger.debug(f"Error processing inline image: {e}")
    else:
        # Non-multipart message - extract directly
        ctype = msg.get_content_type()
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                decoded = payload.decode('utf-8', errors='replace')
                if ctype == 'text/html':
                    body_html = decoded
                else:
                    body_text = decoded
        except Exception as e:
            logger.debug(f"Error decoding non-multipart message: {e}")

    # If we only got HTML, extract a clean text version for body_text
    if not body_text and body_html:
        body_text = clean_snippet(body_html, max_length=2000)

    if inline_images and body_html:
        for cid, data_uri in inline_images.items():
            body_html = body_html.replace(f'cid:{cid}', data_uri)

    snippet = clean_snippet(body_text or body_html or '', max_length=200)

    in_reply_to = msg.get('In-Reply-To', '').strip()
    references = msg.get('References', '').strip()
    thread_id = _build_thread_id(
        inbox, subject, from_email, in_reply_to, references)
    recipients = [addr for _, addr in getaddresses(
        [to_val, cc_val, bcc_val]) if addr]
    participants = sorted({addr for addr in [from_email, *recipients] if addr})
    message_id = msg.get(
        'Message-ID', f"{received_at.timestamp()}-{from_email}")

    with transaction.atomic():
        thread, thread_created = EmailThread.objects.get_or_create(
            inbox=inbox,
            thread_id=thread_id,
            defaults={
                'subject': subject,
                'snippet': snippet,
                'participants': participants,
                'message_count': 0,
                'last_message_at': received_at,
            },
        )

        _, message_created = EmailMessage.objects.get_or_create(
            thread=thread,
            message_id=message_id,
            defaults={
                'from_email': from_email,
                'from_name': from_name,
                'to_emails': recipients,
                'cc_emails': [addr for _, addr in getaddresses([cc_val]) if addr],
                'bcc_emails': [addr for _, addr in getaddresses([bcc_val]) if addr],
                'subject': subject,
                'body_text': body_text,
                'body_html': body_html,
                'received_at': received_at,
                'is_incoming': is_incoming,
            },
        )

        update_fields = []
        if message_created:
            EmailThread.objects.filter(pk=thread.pk).update(
                message_count=F('message_count') + 1)
            thread.message_count += 1
        merged_participants = sorted(
            set(thread.participants or []) | set(participants))
        if merged_participants != (thread.participants or []):
            thread.participants = merged_participants
            update_fields.append('participants')
        if received_at and (thread_created or not thread.last_message_at or received_at > thread.last_message_at):
            thread.last_message_at = received_at
            thread.snippet = snippet
            update_fields.extend(['last_message_at', 'snippet'])
        if update_fields:
            thread.save(update_fields=update_fields)

    return message_created


def _build_thread_id(inbox, subject, from_email, in_reply_to=None, references=None):
    import hashlib
    key = in_reply_to or references or f"{subject}:{from_email}"
    raw = f"{inbox.id}:{key}".encode('utf-8')
    return hashlib.md5(raw).hexdigest()[:20]


def _decode_header_value(val):
    if not val:
        return ''
    decoded_parts = decode_header(val)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            try:
                result.append(part.decode(
                    charset or 'utf-8', errors='replace'))
            except LookupError:
                result.append(part.decode('utf-8', errors='replace'))
        else:
            result.append(part)
    return ' '.join(result).strip()


def _parse_email(from_val):
    match = re.search(r'([^<]+)<([^>]+)>', from_val)
    if match:
        return match.group(2).strip(), match.group(1).strip()
    return from_val.strip(), ''


def _parse_date(date_str):
    if not date_str:
        return None
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None
