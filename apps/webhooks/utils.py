import logging
from apps.webhooks.models import WebhookEndpoint

logger = logging.getLogger(__name__)

def dispatch_webhook_event(workspace_id, event_type, payload):
    """
    Find all active webhook endpoints for the given workspace,
    and deliver the payload asynchronously if they are subscribed
    to the specified event type.
    """
    if not workspace_id:
        return

    try:
        endpoints = WebhookEndpoint.objects.filter(workspace_id=workspace_id, is_active=True)
        for ep in endpoints:
            if not ep.events or event_type in ep.events:
                try:
                    ep.deliver(event_type, payload)
                except Exception as exc:
                    logger.error(
                        f"Failed to queue webhook delivery for endpoint {ep.id} "
                        f"({ep.url}): {exc}"
                    )
    except Exception as exc:
        logger.error(f"Error querying webhook endpoints for workspace {workspace_id}: {exc}")
