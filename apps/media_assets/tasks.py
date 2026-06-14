import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def process_asset(asset_id):
    from .models import MediaAsset
    from .services import MediaService

    try:
        asset = MediaAsset.objects.get(id=asset_id)
        service = MediaService(asset.user)
        service._post_process(asset)
        logger.info(f"Asset {asset_id} processed.")
    except MediaAsset.DoesNotExist:
        logger.warning(f"Asset {asset_id} not found for processing.")


@shared_task
def bulk_tag_assets(asset_ids):
    from .models import MediaAsset
    from .tagging import AutoTaggingService

    tagger = AutoTaggingService()
    for asset_id in asset_ids:
        try:
            asset = MediaAsset.objects.get(id=asset_id)
            tagger.auto_tag(asset)
        except MediaAsset.DoesNotExist:
            continue
