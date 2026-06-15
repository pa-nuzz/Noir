import logging

from celery import shared_task
from django.utils import timezone

from core.tenant import tenant_context
from apps.workspaces.models import Workspace
from .models import EditLock

logger = logging.getLogger(__name__)


@shared_task
def release_expired_locks():
    for workspace in Workspace.objects.all():
        with tenant_context(workspace):
            expired = EditLock.objects.filter(expires_at__lte=timezone.now())
            count = expired.count()
            if count:
                expired.delete()
                logger.info(f"Released {count} expired edit lock(s) for workspace {workspace.name}.")
    return count
