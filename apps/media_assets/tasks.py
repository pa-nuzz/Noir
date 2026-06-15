import logging

from celery import shared_task

from core.tenant import tenant_context
from apps.workspaces.models import Workspace

logger = logging.getLogger(__name__)


@shared_task
def process_asset(asset_id: int, workspace_id: int = None):
    from .models import MediaAsset
    from .services import MediaService

    if workspace_id:
        try:
            workspace = Workspace.objects.get(pk=workspace_id)
        except Workspace.DoesNotExist:
            logger.warning(f"Asset {asset_id} not found for processing: workspace {workspace_id} not found.")
            return
    else:
        workspace = None

    with tenant_context(workspace):
        try:
            asset = MediaAsset.objects.get(id=asset_id)
            service = MediaService(asset.user)
            service._post_process(asset)
            logger.info(f"Asset {asset_id} processed.")
        except MediaAsset.DoesNotExist:
            logger.warning(f"Asset {asset_id} not found for processing.")


@shared_task
def bulk_tag_assets(asset_ids: list, workspace_id: int = None):
    from .models import MediaAsset
    from .tagging import AutoTaggingService

    if workspace_id:
        try:
            workspace = Workspace.objects.get(pk=workspace_id)
        except Workspace.DoesNotExist:
            logger.warning(f"Bulk tag: workspace {workspace_id} not found.")
            return
    else:
        workspace = None

    with tenant_context(workspace):
        tagger = AutoTaggingService()
        for asset_id in asset_ids:
            try:
                asset = MediaAsset.objects.get(id=asset_id)
                tagger.auto_tag(asset)
            except MediaAsset.DoesNotExist:
                continue
