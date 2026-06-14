from django.core.management.base import BaseCommand

from apps.billing.models import Plan


PLANS = [
    {
        'plan_id': 'free',
        'name': 'Free',
        'description': 'For individuals getting started',
        'price_monthly': 0,
        'price_yearly': 0,
        'sort_order': 0,
        'features': [
            'Up to 500 emails/month',
            '2 social accounts',
            '100 AI credits',
            '1 GB storage',
            '2 team seats',
        ],
    },
    {
        'plan_id': 'pro',
        'name': 'Pro',
        'description': 'For professionals and small teams',
        'price_monthly': 999,
        'price_yearly': 9990,
        'sort_order': 1,
        'features': [
            'Up to 10,000 emails/month',
            '10 social accounts',
            '1,000 AI credits',
            '50 GB storage',
            '10 team seats',
            'Priority support',
        ],
    },
    {
        'plan_id': 'enterprise',
        'name': 'Enterprise',
        'description': 'For organizations with custom needs',
        'price_monthly': 4999,
        'price_yearly': 49990,
        'sort_order': 2,
        'features': [
            'Unlimited emails',
            'Unlimited social accounts',
            'Unlimited AI credits',
            'Unlimited storage',
            'Unlimited team seats',
            'Dedicated support',
            'Custom integrations',
        ],
    },
]


class Command(BaseCommand):
    help = 'Seed plan tiers into the database'

    def handle(self, *args, **options):
        for data in PLANS:
            Plan.objects.update_or_create(
                plan_id=data['plan_id'],
                defaults=data,
            )
            self.stdout.write(self.style.SUCCESS(f"  Created plan: {data['name']}"))
        self.stdout.write(self.style.SUCCESS('Done seeding plans.'))
