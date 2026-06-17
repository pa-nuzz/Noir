import logging
import os

from django.core.management.base import BaseCommand, CommandError
from django.core.files.base import ContentFile

from apps.media_assets.models import MediaAsset, MediaFolder
from apps.media_assets.storage import MinIOStorage, LocalStorage

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Migrate existing local media assets to MinIO storage'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be migrated without actually doing it',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompt',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Number of assets to process in each batch (default: 50)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        batch_size = options['batch_size']

        local_assets = MediaAsset.objects.filter(
            storage_backend='local',
            storage_path__isnull=False
        ).exclude(storage_path='')

        self.stdout.write(f'Found {local_assets.count()} local assets to migrate to MinIO.')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - no files will be moved'))

        if not force and not dry_run:
            confirm = input('Proceed with migration? (yes/no): ')
            if confirm.lower() != 'yes':
                self.stdout.write('Migration cancelled.')
                return

        try:
            minio_storage = MinIOStorage()
            minio_storage.test_connection()
        except Exception as e:
            raise CommandError(f'Cannot connect to MinIO: {e}')

        local_storage = LocalStorage()
        migrated = 0
        failed = 0

        for asset in local_assets.iterator(chunk_size=batch_size):
            try:
                if not asset.storage_path:
                    self.stdout.write(f'Skipping asset {asset.id}: no storage path')
                    continue

                local_file_path = asset.storage_path

                if not local_storage.exists(local_file_path):
                    if asset.file and asset.file.name and os.path.exists(asset.file.path):
                        local_file_path = asset.file.name
                    else:
                        self.stdout.write(f'Skipping asset {asset.id}: file not found at {asset.storage_path}')
                        failed += 1
                        continue

                file_data = local_storage.open(local_file_path).read()
                content_type = asset.mime_type or 'application/octet-stream'

                new_path = minio_storage.save(
                    local_file_path,
                    ContentFile(file_data, name=os.path.basename(local_file_path)),
                    content_type=content_type,
                )

                asset.storage_path = new_path
                asset.storage_backend = 'minio'
                asset.save(update_fields=['storage_path', 'storage_backend'])

                migrated += 1
                self.stdout.write(f'Migrated: {asset.original_filename} -> {new_path}')

            except Exception as e:
                failed += 1
                logger.exception(f'Failed to migrate asset {asset.id}')
                self.stdout.write(self.style.ERROR(f'Failed to migrate asset {asset.id}: {e}'))

        self.stdout.write(self.style.SUCCESS(
            f'Migration complete: {migrated} migrated, {failed} failed'
        ))
