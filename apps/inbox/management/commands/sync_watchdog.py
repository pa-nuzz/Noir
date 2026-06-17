import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Reset inboxes stuck in syncing status for more than 5 minutes'

    def handle(self, *args, **options):
        from apps.inbox.models import EmailInbox

        threshold = timezone.now() - timedelta(minutes=5)
        stuck = EmailInbox.objects.filter(
            last_sync_status='syncing',
            last_synced_at__lt=threshold,
        )

        count = 0
        for inbox in stuck:
            inbox.last_sync_status = 'error'
            inbox.last_sync_error = 'Sync timed out after 5 minutes. Click sync to retry.'
            inbox.save(update_fields=['last_sync_status', 'last_sync_error'])
            logger.warning(
                f'Reset stuck sync for inbox {inbox.id} ({inbox.email_address})')
            count += 1

        if count:
            self.stdout.write(f'Reset {count} stuck inbox(es)')
        else:
            self.stdout.write('No stuck inboxes found')
