import logging
from celery import shared_task
from django.db import models

from core.tenant import tenant_context
from apps.workspaces.models import Workspace

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def deliver_webhook(self, endpoint_id: int, event_type: str, payload: dict, workspace_id: int = None):
    from .models import WebhookEndpoint, WebhookDelivery

    if workspace_id:
        try:
            workspace = Workspace.objects.get(pk=workspace_id)
        except Workspace.DoesNotExist:
            logger.warning(f"Webhook delivery failed: workspace {workspace_id} not found.")
            return
    else:
        workspace = None

    with tenant_context(workspace):
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

    for workspace in Workspace.objects.all():
        with tenant_context(workspace):
            now = timezone.now()
            pending = WebhookDelivery.objects.filter(
                status__in=('failed', 'retrying'),
                next_retry_at__lte=now,
                attempt_count__lt=models.F('max_attempts'),
            )
            for delivery in pending:
                deliver_webhook.delay(delivery.endpoint_id, delivery.event_type, delivery.payload, workspace.id)
