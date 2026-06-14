from django.core.management.base import BaseCommand

from apps.campaigns.services import run_scheduled_campaigns


class Command(BaseCommand):
    help = 'Process scheduled campaigns that are due for sending.'

    def handle(self, *args, **options):
        result = run_scheduled_campaigns()
        self.stdout.write(
            self.style.SUCCESS(
                'Scheduled campaigns run complete: '
                f"due={result['due']} processed={result['processed']} sent={result['sent']} failed={result['failed']}"
            )
        )
