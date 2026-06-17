import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync a single inbox by ID via IMAP'

    def add_arguments(self, parser):
        parser.add_argument('inbox_id', type=int)

    def handle(self, *args, **options):
        inbox_id = options['inbox_id']
        from apps.inbox.models import EmailInbox
        from apps.inbox.services.sync import sync_inbox

        try:
            inbox = EmailInbox.objects.get(id=inbox_id)
        except EmailInbox.DoesNotExist:
            self.stderr.write(f'Inbox {inbox_id} not found')
            return

        password = inbox.get_token()
        if not password:
            inbox.last_sync_status = 'error'
            inbox.last_sync_error = 'No password stored. Please reconnect the inbox.'
            inbox.last_synced_at = timezone.now()
            inbox.save(update_fields=['last_sync_status',
                       'last_sync_error', 'last_synced_at'])
            self.stderr.write(f'No password for inbox {inbox_id}')
            return

        try:
            count = sync_inbox(inbox, password)
            self.stdout.write(f'Synced inbox {inbox_id}: {count} new messages')

            # Auto-reply to important incoming messages after sync
            try:
                from apps.inbox.models import EmailDraft, EmailMessage
                from apps.intelligence.services.auto_reply import \
                    process_auto_reply

                new_messages = EmailMessage.objects.filter(
                    thread__inbox=inbox,
                    is_incoming=True,
                    is_deleted=False,
                ).select_related('thread').order_by('-received_at')[:30]

                auto_replied = 0
                for msg in new_messages:
                    try:
                        if process_auto_reply(msg.id):
                            auto_replied += 1
                    except Exception:
                        continue

                if auto_replied:
                    self.stdout.write(
                        f'Auto-replied to {auto_replied} messages')
            except Exception as ar_err:
                logger.warning(f'Auto-reply post-sync error: {ar_err}')
        except Exception as e:
            logger.exception(f'Sync failed for inbox {inbox_id}: {e}')
            inbox.last_sync_status = 'error'
            inbox.last_sync_error = str(e)[:200]
            inbox.last_synced_at = timezone.now()
            inbox.save(update_fields=['last_sync_status',
                       'last_sync_error', 'last_synced_at'])
            self.stderr.write(f'Sync failed for inbox {inbox_id}: {e}')
