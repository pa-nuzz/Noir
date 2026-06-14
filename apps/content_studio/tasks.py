import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def auto_generate_variations(content_item_id):
    from .models import ContentItem
    from .services import ContentService

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
