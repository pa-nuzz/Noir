from django.conf import settings
from django.utils import timezone

from apps.campaigns.models import Campaign

from .delivery import send_campaign_with_smtp


def run_scheduled_campaigns():
    now = timezone.now()
    due_campaigns = Campaign.objects.filter(
        status='scheduled',
        scheduled_at__isnull=False,
        scheduled_at__lte=now,
    ).select_related('sender', 'user')

    total_due = due_campaigns.count()
    processed = 0
    sent = 0
    failed = 0

    for campaign in due_campaigns:
        processed += 1
        campaign.status = 'sending'
        campaign.total_recipients = len(campaign.get_recipient_list())
        campaign.save(update_fields=['status', 'total_recipients', 'updated_at'])
        try:
            base_url = (settings.TRACKING_BASE_URL or '').rstrip('/')
            if not base_url:
                raise ValueError('TRACKING_BASE_URL is not configured.')

            sent_count, failed_count, _ = send_campaign_with_smtp(campaign, base_url)
            campaign.sent_count = (campaign.sent_count or 0) + sent_count
            campaign.bounce_count = (campaign.bounce_count or 0) + failed_count
            campaign.status = 'sent' if campaign.sent_count > 0 else 'failed'
            campaign.save(update_fields=['sent_count', 'bounce_count', 'status', 'updated_at'])
            sent += sent_count
            failed += failed_count
        except Exception:
            campaign.status = 'failed'
            campaign.save(update_fields=['status', 'updated_at'])
            failed += 1

    return {
        'due': total_due,
        'processed': processed,
        'sent': sent,
        'failed': failed,
    }
