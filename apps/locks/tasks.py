import logging

from celery import shared_task
from django.db import close_old_connections
from django.utils import timezone

from core.tenant import tenant_context
from apps.workspaces.models import Workspace
from .models import EditLock

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=30, retry_backoff_max=300, max_retries=5)
def release_expired_locks(self):
    """Release expired edit locks across all workspaces.

    Uses bind=True and autoretry_for to handle stale DB connections gracefully.
    Calls close_old_connections() before iterating to ensure fresh connections.
    """
    close_old_connections()

    total_released = 0
    for workspace in Workspace.objects.all().only('id', 'name'):
        try:
            with tenant_context(workspace):
                close_old_connections()
                expired = EditLock.objects.filter(expires_at__lte=timezone.now())
                count = expired.count()
                if count:
                    expired.delete()
                    logger.info(f"Released {count} expired edit lock(s) for workspace {workspace.name}.")
                    total_released += count
        except Exception as e:
            logger.warning(f"Error releasing locks for workspace {workspace.id}: {e}")
            close_old_connections()
            continue

    return total_released
