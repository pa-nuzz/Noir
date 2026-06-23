from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.content_studio.models import ContentItem
from apps.workspaces.models import WorkspaceMembership


class Command(BaseCommand):
    help = 'Assign a workspace to ContentItem records that have workspace=NULL'

    def handle(self, *args, **options):
        orphans = ContentItem.objects.filter(
            Q(workspace__isnull=True) | Q(workspace=None)
        )
        total = orphans.count()
        self.stdout.write(f'Found {total} orphaned items')

        updated = 0
        skipped = 0
        for item in orphans:
            membership = (
                WorkspaceMembership.objects
                .filter(user=item.user)
                .select_related('workspace')
                .order_by('-role')
                .first()
            )
            if membership and membership.workspace:
                item.workspace = membership.workspace
                item.save(update_fields=['workspace'])
                updated += 1
            else:
                skipped += 1

        self.stdout.write(self.style.SUCCESS(f'Backfilled {updated} items (skipped {skipped} — no workspace membership found)'))
