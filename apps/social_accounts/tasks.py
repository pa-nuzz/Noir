import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def publish_scheduled_posts():
    from .models import SocialPost
    from .services import SocialService

    now = timezone.now()
    due = SocialPost.objects.filter(status='scheduled', scheduled_at__lte=now).select_related('user', 'account')
    for post in due:
        service = SocialService(post.user)
        try:
            service.publish_post(post.id)
            logger.info(f"Scheduled post {post.id} published.")
        except Exception as e:
            logger.exception(f"Failed to publish scheduled post {post.id}: {e}")


@shared_task
def sync_post_analytics(post_id):
    from .models import SocialPost
    from .services import SocialService

    try:
        post = SocialPost.objects.get(id=post_id)
        service = SocialService(post.user)
        service.fetch_analytics(post_id)
    except SocialPost.DoesNotExist:
        logger.warning(f"Post {post_id} not found for analytics sync.")
