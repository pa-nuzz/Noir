import logging
from celery import shared_task

from core.tenant import tenant_context
from apps.workspaces.models import Workspace

logger = logging.getLogger(__name__)


@shared_task
def sync_inbox_task(inbox_id: int, password: str = '', workspace_id: int = None):
    from .models import EmailInbox
    from .services.sync import sync_inbox

    if workspace_id:
        try:
            workspace = Workspace.objects.get(pk=workspace_id)
        except Workspace.DoesNotExist:
            logger.warning(f"Workspace {workspace_id} not found — skipping sync")
            return 0
    else:
        workspace = None

    with tenant_context(workspace):
        try:
            inbox = EmailInbox.objects.get(id=inbox_id, is_active=True)
        except EmailInbox.DoesNotExist:
            logger.warning(f"Inbox {inbox_id} not found or inactive — skipping sync")
            return 0

        pwd = password or inbox.get_token()
        if not pwd:
            logger.warning(f"No password available for inbox {inbox_id} — skipping sync")
            inbox.last_sync_status = 'error'
            inbox.last_sync_error = 'No password stored'
            inbox.save(update_fields=['last_sync_status', 'last_sync_error'])
            return 0

        try:
            count = sync_inbox(inbox, pwd)
        except Exception as exc:
            logger.exception("Sync failed for inbox %s", inbox.id)
            inbox.last_sync_status = 'error'
            inbox.last_sync_error = str(exc)[:1000]
            inbox.save(update_fields=['last_sync_status', 'last_sync_error'])
            return 0

        logger.info("Synced inbox %s: %s new message(s)", inbox.email_address, count)

        if count > 0:
            process_auto_replies_for_inbox.delay(inbox_id, workspace_id)

        return count


@shared_task
def sync_all_inboxes_task():
    from .models import EmailInbox
    from .services.sync import sync_inbox

    for workspace in Workspace.objects.all():
        with tenant_context(workspace):
            inboxes = EmailInbox.objects.filter(is_active=True)
            total = 0
            for inbox in inboxes:
                try:
                    password = inbox.get_token()
                    count = sync_inbox(inbox, password or '')
                    total += count
                    if count > 0:
                        process_auto_replies_for_inbox.delay(inbox.id, workspace.id)
                except Exception as e:
                    logger.error(f"Error syncing inbox {inbox.id}: {e}")

            logger.info(f"Synced {inboxes.count()} inboxes: {total} new message(s) for workspace {workspace.name}")
    return total


@shared_task
def process_auto_replies_for_inbox(inbox_id: int, workspace_id: int = None):
    from .models import EmailMessage, EmailInbox
    from apps.intelligence.services.auto_reply import process_auto_reply

    if workspace_id:
        try:
            workspace = Workspace.objects.get(pk=workspace_id)
        except Workspace.DoesNotExist:
            logger.warning(f"Auto-reply: workspace {workspace_id} not found — skipping")
            return 0
    else:
        workspace = None

    with tenant_context(workspace):
        try:
            inbox = EmailInbox.objects.get(id=inbox_id, is_active=True)
        except EmailInbox.DoesNotExist:
            logger.warning(f"Auto-reply: inbox {inbox_id} not found — skipping")
            return 0

        recent_messages = EmailMessage.objects.filter(
            thread__inbox=inbox,
            is_incoming=True,
        ).select_related('thread', 'thread__inbox').order_by('-received_at')[:20]

        processed = 0
        for msg in recent_messages:
            try:
                if process_auto_reply(msg.id):
                    processed += 1
            except Exception as e:
                logger.error(f"Auto-reply error for message {msg.id}: {e}")

        logger.info(f"Auto-reply: processed {processed} messages for inbox {inbox.email_address}")
        return processed


@shared_task
def process_auto_reply_for_message(message_id: int, workspace_id: int = None):
    from apps.intelligence.services.auto_reply import process_auto_reply

    if workspace_id:
        try:
            workspace = Workspace.objects.get(pk=workspace_id)
        except Workspace.DoesNotExist:
            logger.warning(f"Auto-reply: workspace {workspace_id} not found — skipping")
            return False
    else:
        workspace = None

    with tenant_context(workspace):
        try:
            success = process_auto_reply(message_id)
            if success:
                logger.info(f"Auto-reply created for message {message_id}")
            return success
        except Exception as e:
            logger.error(f"Auto-reply task failed for message {message_id}: {e}")
            return False
