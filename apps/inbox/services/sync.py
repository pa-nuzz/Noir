import base64
import imaplib
import email
import logging
import re
from email.header import decode_header
from datetime import datetime, timedelta, timezone
from django.utils import timezone as django_timezone

from apps.inbox.models import EmailInbox, EmailThread, EmailMessage

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
                decoded = folder_data.decode(errors='replace') if isinstance(folder_data, bytes) else folder_data
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
        logger.warning(f"Unknown provider for inbox {inbox.id}: {inbox.provider}")
        return 0

    password = password or inbox.get_token()
    if not password:
        logger.warning(f"No password/token for inbox {inbox.id} ({inbox.email_address})")
        return 0

    host, port = server_info
    new_count = 0

    try:
        mail = imaplib.IMAP4_SSL(host, port)
        mail.login(inbox.email_address, password)
        
        # Sync incoming emails from INBOX
        select_status, select_data = mail.select('INBOX')
        if select_status != 'OK':
            error_msg = f"Failed to select INBOX folder: {select_data}"
            logger.error(f"IMAP SELECT failed for {inbox.email_address}: {select_status} {select_data}")
            mail.logout()
            inbox.last_sync_status = 'error'
            inbox.last_sync_error = error_msg
            inbox.last_synced_at = django_timezone.now()
            inbox.save(update_fields=['last_sync_status', 'last_sync_error', 'last_synced_at'])
            return 0
        since_date = (inbox.last_synced_at or (django_timezone.now() - timedelta(days=30))).strftime('%d-%b-%Y')
        search_criteria = f'SINCE {since_date}'
        status, message_ids = mail.search(None, search_criteria)
        if status != 'OK':
            mail.logout()
            return 0

        ids = message_ids[0].split() if message_ids[0] else []
        
        # Process incoming messages
        for mid in ids:
            try:
                status, msg_data = mail.fetch(mid, '(RFC822)')
                if status != 'OK':
                    continue
                for part in msg_data:
                    if isinstance(part, tuple):
                        raw = email.message_from_bytes(part[1])
                        _process_email(inbox, raw)
                        new_count += 1
            except Exception as e:
                logger.error(f"Error processing message {mid}: {e}")

        # Sync sent emails from SENT folder
        sent_folder = _find_sent_folder(mail)
        if sent_folder:
            select_status, select_data = mail.select(mail._quote(sent_folder))
            if select_status != 'OK':
                logger.warning(f"Failed to select SENT folder '{sent_folder}' for {inbox.email_address}: {select_status} {select_data}")
            else:
                status, message_ids = mail.search(None, search_criteria)
                if status == 'OK':
                    sent_ids = message_ids[0].split() if message_ids[0] else []
                    for mid in sent_ids:
                        try:
                            status, msg_data = mail.fetch(mid, '(RFC822)')
                            if status != 'OK':
                                continue
                            for part in msg_data:
                                if isinstance(part, tuple):
                                    raw = email.message_from_bytes(part[1])
                                    _process_email(inbox, raw, is_incoming=False)
                                    new_count += 1
                        except Exception as e:
                            logger.error(f"Error processing sent message {mid}: {e}")

        try:
            mail.close()
        except Exception:
            pass
        mail.logout()

        inbox.last_synced_at = django_timezone.now()
        inbox.last_sync_status = 'success'
        inbox.last_sync_error = ''
        inbox.save(update_fields=['last_synced_at', 'last_sync_status', 'last_sync_error'])

    except imaplib.IMAP4.error as e:
        error_msg = f"IMAP login failed: {str(e)}"
        logger.error(error_msg)
        inbox.last_sync_status = 'error'
        inbox.last_sync_error = error_msg
        inbox.last_synced_at = django_timezone.now()
        inbox.save(update_fields=['last_sync_status', 'last_sync_error', 'last_synced_at'])
    except Exception as e:
        error_msg = f"Sync error: {str(e)}"
        logger.error(error_msg)
        inbox.last_sync_status = 'error'
        inbox.last_sync_error = error_msg
        inbox.last_synced_at = django_timezone.now()
        inbox.save(update_fields=['last_sync_status', 'last_sync_error', 'last_synced_at'])

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
                        if img_data:
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

    if inline_images and body_html:
        for cid, data_uri in inline_images.items():
            body_html = body_html.replace(f'cid:{cid}', data_uri)

    snippet = (body_text or body_html or '')[:200]

    in_reply_to = msg.get('In-Reply-To', '').strip()
    references = msg.get('References', '').strip()
    thread_id = _build_thread_id(inbox, subject, from_email, in_reply_to, references)
    thread, _ = EmailThread.objects.get_or_create(
        inbox=inbox,
        thread_id=thread_id,
        defaults={
            'subject': subject,
            'snippet': snippet,
            'participants': [from_email],
            'message_count': 0,
            'last_message_at': received_at,
        },
    )

    if not _:
        thread.message_count = thread.messages.count()
        if received_at and (not thread.last_message_at or received_at > thread.last_message_at):
            thread.last_message_at = received_at
            thread.snippet = snippet
            thread.save()

    message_id = msg.get('Message-ID', f"{received_at.timestamp()}-{from_email}")
    EmailMessage.objects.get_or_create(
        thread=thread,
        message_id=message_id,
        defaults={
            'from_email': from_email,
            'from_name': from_name,
            'to_emails': [to_val],
            'subject': subject,
            'body_text': body_text,
            'body_html': body_html,
            'received_at': received_at,
            'is_incoming': is_incoming,
        },
    )


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
                result.append(part.decode(charset or 'utf-8', errors='replace'))
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
