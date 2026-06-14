import logging
import os
from io import BytesIO

from django.core.files import File
from django.urls import reverse
from django.utils import timezone

from .models import MediaAsset, MediaFolder
from .processing import MediaProcessor
from .storage import StorageService
from .tagging import AutoTaggingService

logger = logging.getLogger(__name__)


class MediaService:
    def __init__(self, user):
        self.user = user
        self.storage = StorageService.for_user(user)
        self.processor = MediaProcessor()
        self.tagger = AutoTaggingService()

    def upload(self, uploaded_file, folder_id=None, title=None):
        folder = None
        if folder_id:
            folder = MediaFolder.objects.get(id=folder_id, user=self.user)

        date_prefix = f"media_assets/{timezone.now().strftime('%Y/%m/%d')}"
        content_type = getattr(uploaded_file, 'content_type', None) or None

        saved_path = self.storage.save(
            date_prefix,
            uploaded_file,
            content_type=content_type,
        )

        asset = MediaAsset(
            user=self.user,
            folder=folder,
            original_filename=uploaded_file.name,
            file_size=uploaded_file.size,
            mime_type=content_type or '',
            title=title or uploaded_file.name,
            storage_path=saved_path.replace('\\', '/'),
            storage_backend=self.storage.backend.backend_name,
            is_processing=True,
        )

        if self.storage.backend.backend_name == 'local':
            asset.file.name = saved_path
        else:
            asset.file.name = saved_path

        asset.save()

        self._post_process(asset)
        return asset

    def _post_process(self, asset):
        try:
            if asset.file_type == 'image' and self.storage.exists(asset.storage_path):
                dimensions = self.processor.get_dimensions_from_bytes(
                    self.storage.open(asset.storage_path).read()
                )
                if dimensions:
                    asset.width, asset.height = dimensions

                    thumb_io = self.processor.create_thumbnail_from_bytes(
                        self.storage.open(asset.storage_path).read()
                    )
                    if thumb_io:
                        thumb_name = f"thumb_{os.path.splitext(os.path.basename(asset.storage_path))[0]}.webp"
                        thumb_path = self.storage.save(
                            f"media_assets/thumbnails/{timezone.now().strftime('%Y/%m/%d')}",
                            File(thumb_io, name=thumb_name),
                            content_type='image/webp',
                        )
                        asset.thumbnail_path = thumb_path
                        if self.storage.backend.backend_name == 'local':
                            asset.thumbnail.name = thumb_path

            self.tagger.auto_tag(asset)
            asset.is_processing = False
            asset.is_optimized = True
            asset.save(update_fields=[
                'width', 'height', 'thumbnail_path',
                'is_processing', 'is_optimized', 'thumbnail',
            ])
        except Exception:
            logger.exception("Post-processing failed for asset %s", asset.id)
            asset.is_processing = False
            asset.save(update_fields=['is_processing'])

    def create_folder(self, name, parent_id=None):
        parent = None
        if parent_id:
            parent = MediaFolder.objects.get(id=parent_id, user=self.user)
        folder, _created = MediaFolder.objects.get_or_create(
            name=name, parent=parent, user=self.user
        )
        return folder

    def get_folder_tree(self):
        def _build_tree(parent=None):
            folders = MediaFolder.objects.filter(parent=parent, user=self.user)
            return [{
                'id': f.id,
                'name': f.name,
                'children': _build_tree(f),
                'asset_count': f.assets.count(),
            } for f in folders]
        return _build_tree()

    def search_assets(self, query, file_type=None, folder_id=None):
        from django.db.models import Q
        qs = MediaAsset.objects.filter(user=self.user)
        if query:
            qs = qs.filter(
                Q(title__icontains=query)
                | Q(original_filename__icontains=query)
                | Q(description__icontains=query)
                | Q(tags__name__icontains=query)
            )
        if file_type:
            qs = qs.filter(file_type=file_type)
        if folder_id:
            qs = qs.filter(folder_id=folder_id)
        return qs.distinct()

    def delete_asset(self, asset_id):
        asset = MediaAsset.objects.get(id=asset_id, user=self.user)
        if asset.storage_path:
            self.storage.delete(asset.storage_path)
        if asset.thumbnail_path:
            self.storage.delete(asset.thumbnail_path)
        asset.delete()

    def _proxy_url(self, asset, file_type='original'):
        return reverse('media_assets:serve_asset', args=[asset.id, file_type])

    def get_asset_url(self, asset):
        if self.storage.backend.backend_name == 'google_drive':
            return self._proxy_url(asset, 'original')
        if asset.storage_path:
            if self.storage.exists(asset.storage_path):
                url = self.storage.url(asset.storage_path)
                if url:
                    return url
        if asset.file and asset.file.name:
            if self.storage.exists(asset.file.name):
                return asset.file.url
        return ''

    def get_thumbnail_url(self, asset):
        if self.storage.backend.backend_name == 'google_drive':
            return self._proxy_url(asset, 'thumbnail')
        if asset.thumbnail_path:
            if self.storage.exists(asset.thumbnail_path):
                url = self.storage.url(asset.thumbnail_path)
                if url:
                    return url
        if asset.thumbnail and asset.thumbnail.name:
            if self.storage.exists(asset.thumbnail.name):
                return asset.thumbnail.url
        return self.get_asset_url(asset)
