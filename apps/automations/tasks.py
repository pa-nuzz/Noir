import logging
from celery import shared_task

from core.tenant import tenant_context
from apps.workspaces.models import Workspace

logger = logging.getLogger(__name__)


@shared_task
def process_workflows_task():
    """
    Celery beat task that processes all active workflow enrollments
    whose next_execution_at has passed.
    """
    from .engine import process_workflow_enrollments

    for workspace in Workspace.objects.all():
        with tenant_context(workspace):
            processed = process_workflow_enrollments()
            if processed:
                logger.info(f"Automations: processed {processed} enrollment(s) for workspace {workspace.name}.")
    return processed
