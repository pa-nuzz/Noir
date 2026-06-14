import logging

from celery import shared_task
from django.utils import timezone

from .models import EditLock

logger = logging.getLogger(__name__)


@shared_task
def release_expired_locks():
    expired = EditLock.objects.filter(expires_at__lte=timezone.now())
    count = expired.count()
    if count:
        expired.delete()
        logger.info(f"Released {count} expired edit lock(s).")
    return count
