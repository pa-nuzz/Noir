import logging
from django.core.management.base import BaseCommand
from apps.trending.models import FeedItem
from apps.trending.services.summarizer import Summarizer

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Regenerate ai_summary for all FeedItems using the improved summarizer prompt and fallback'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Number of items to process per batch (default: 50)',
        )

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        summarizer = Summarizer()

        total = FeedItem.objects.filter(
            is_duplicate=False,
        ).exclude(
            content_cleaned__exact='',
            content_raw__exact='',
        ).count()

        self.stdout.write(f'Found {total} items to process')

        processed = 0
        updated = 0

        while True:
            items = list(FeedItem.objects.filter(
                is_duplicate=False,
            ).exclude(
                content_cleaned__exact='',
                content_raw__exact='',
            ).order_by('-trending_score')[processed:processed + batch_size])

            if not items:
                break

            for item in items:
                old_summary = item.ai_summary
                summarizer.summarize(item)
                item.save(update_fields=['ai_summary'])
                processed += 1

                if item.ai_summary != old_summary:
                    updated += 1

                if processed % 10 == 0:
                    self.stdout.write(f'  Processed {processed}/{total}')

            self.stdout.write(f'  Batch complete: {processed}/{total} processed, {updated} updated')

        self.stdout.write(self.style.SUCCESS(
            f'Done. {processed} items processed, {updated} summaries updated.'
        ))
