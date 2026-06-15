import logging

from celery import shared_task

from core.tenant import tenant_context
from apps.workspaces.models import Workspace

logger = logging.getLogger(__name__)


@shared_task
def auto_generate_variations(content_item_id: int, workspace_id: int = None):
    from .models import ContentItem
    from .services import ContentService

    if workspace_id:
        try:
            workspace = Workspace.objects.get(pk=workspace_id)
        except Workspace.DoesNotExist:
            logger.warning(f"Content item {content_item_id} not found: workspace {workspace_id} not found.")
            return
    else:
        workspace = None

    with tenant_context(workspace):
        try:
            item = ContentItem.objects.get(id=content_item_id)
            service = ContentService(item.user)
            tones = ['professional', 'casual', 'humorous', 'inspirational']
            for tone in tones:
                service.generate_content(
                    content_type=item.content_type,
                    prompt=item.source_prompt or item.title,
                    platform=item.platform,
                    tone=tone,
                )
            logger.info(f"Generated {len(tones)} variations for content {content_item_id}")
        except ContentItem.DoesNotExist:
            logger.warning(f"Content item {content_item_id} not found")
