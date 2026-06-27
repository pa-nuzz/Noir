import logging
from django.core.management.base import BaseCommand
from apps.inbox.models import EmailInbox

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fix inboxes with broken/undecryptable tokens'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show what would be fixed without making changes')
        parser.add_argument('--inbox-id', type=int, help='Fix only a specific inbox ID')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        inbox_id = options.get('inbox_id')

        qs = EmailInbox.objects.all()
        if inbox_id:
            qs = qs.filter(id=inbox_id)

        fixed = 0
        for inbox in qs:
            token = inbox.get_token()
            if token is not None:
                self.stdout.write(f"  OK  {inbox.id:>3} {inbox.email_address}")
                continue

            if inbox.imap_password:
                self.stdout.write(f"  WARN {inbox.id:>3} {inbox.email_address} — imap_password set but get_token() returns None (key mismatch?)")
                continue

            if inbox.access_token:
                self.stdout.write(f"  FIX  {inbox.id:>3} {inbox.email_address} — clearing undecryptable access_token ({len(inbox.access_token)} chars)")
                if not dry_run:
                    inbox.access_token = ''
                    inbox.last_sync_status = 'error'
                    inbox.last_sync_error = 'No password stored. Reconnect to set a new password.'
                    inbox.save(update_fields=['access_token', 'last_sync_status', 'last_sync_error'])
                fixed += 1
            else:
                self.stdout.write(f"  OK  {inbox.id:>3} {inbox.email_address} — no token (needs connection)")

        if dry_run:
            self.stdout.write(f"\n{dry_run=}: {fixed} inboxes would be fixed")
        else:
            self.stdout.write(f"\n{fixed} inboxes fixed")
