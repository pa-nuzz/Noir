from celery import shared_task
from django.db import models


@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def deliver_webhook(self, endpoint_id, event_type, payload):
    from .models import WebhookEndpoint, WebhookDelivery

    try:
        endpoint = WebhookEndpoint.objects.get(id=endpoint_id, is_active=True)
    except WebhookEndpoint.DoesNotExist:
        return

    delivery = WebhookDelivery.objects.create(
        endpoint=endpoint,
        event_type=event_type,
        payload=payload,
        status='pending',
    )

    result = delivery.execute()

    if result == 'retrying':
        raise self.retry(countdown=delivery.retry_delay(), max_retries=delivery.max_attempts)

    return result


@shared_task
def retry_failed_deliveries():
    from django.utils import timezone
    from .models import WebhookDelivery

    now = timezone.now()
    pending = WebhookDelivery.objects.filter(
        status__in=('failed', 'retrying'),
        next_retry_at__lte=now,
        attempt_count__lt=models.F('max_attempts'),
    )
    for delivery in pending:
        deliver_webhook.delay(delivery.endpoint_id, delivery.event_type, delivery.payload)
