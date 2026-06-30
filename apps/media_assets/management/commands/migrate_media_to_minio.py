"""
Management command to migrate existing media files from local filesystem to MinIO.

Usage:
    python manage.py migrate_media_to_minio [--dry-run] [--verify]

This command:
1. Scans all existing avatar files in media/avatars
2. Scans all MediaAsset files in media/media_assets
3. Uploads them to MinIO
4. Updates model references if necessary
5. Verifies upload success
6. Logs failures
"""

import glob
import logging
import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.management.base import BaseCommand
from django.core.management import call_command

from apps.media_assets.models import MediaAsset
from apps.media_assets.minio_storage import MinIODjangoStorage

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Migrate existing media files from local filesystem to MinIO'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be migrated without actually uploading',
        )
        parser.add_argument(
            '--verify',
            action='store_true',
            help='Verify existing MinIO uploads and report status',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        verify = options.get('verify', False)

        if verify:
            self.verify_existing_uploads()
            return

        self.stdout.write(self.style.WARNING('Starting media migration to MinIO...'))
        
        # Initialize MinIO storage
        try:
            minio_storage = MinIODjangoStorage()
            ok, err = minio_storage.test_connection()
            if not ok:
                self.stderr.write(self.style.ERROR(f'MinIO connection failed: {err}'))
                return
            self.stdout.write(self.style.SUCCESS('MinIO connection verified'))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Failed to initialize MinIO storage: {e}'))
            return

        # Migrate avatars (wrapped in try-except to handle corrupted local files)
        try:
            avatars_count = self.migrate_avatars(minio_storage, dry_run)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Avatar migration failed: {e}'))
            avatars_count = 0
        
        # Migrate media assets
        try:
            media_count = self.migrate_media_assets(minio_storage, dry_run)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Media asset migration failed: {e}'))
            media_count = 0
        
        # Summary
        self.stdout.write(self.style.SUCCESS(
            f'\nMigration complete!\n'
            f'  Avatars migrated: {avatars_count}\n'
            f'  Media assets migrated: {media_count}\n'
        ))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('This was a dry run. No files were actually uploaded.'))

    def migrate_avatars(self, minio_storage, dry_run=False):
        """Migrate avatar files from local filesystem to MinIO."""
        media_root = getattr(settings, 'MEDIA_ROOT', None)
        if not media_root:
            self.stderr.write(self.style.ERROR('MEDIA_ROOT not configured'))
            return 0

        avatars_dir = Path(media_root) / 'avatars'
        if not avatars_dir.exists():
            self.stdout.write(self.style.WARNING(f'Avatars directory does not exist: {avatars_dir}'))
            return 0

        # Find all image files in avatars directory
        avatar_patterns = ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.webp']
        avatar_files = []
        for pattern in avatar_patterns:
            avatar_files.extend(glob.glob(str(avatars_dir / pattern)))
            avatar_files.extend(glob.glob(str(avatars_dir / '**' / pattern), recursive=True))

        self.stdout.write(f'Found {len(avatar_files)} avatar files to migrate')

        migrated_count = 0
        for file_path in avatar_files:
            relative_path = Path(file_path).relative_to(avatars_dir.parent)
            minio_key = f'avatars/{Path(file_path).name}'
            
            self.stdout.write(f'  Processing: {minio_key}')
            
            if dry_run:
                self.stdout.write(f'    [DRY-RUN] Would upload to MinIO')
                migrated_count += 1
                continue
            
            # Check if already in MinIO
            if minio_storage.exists(minio_key):
                self.stdout.write(f'    Already exists in MinIO, skipping')
                continue
            
            try:
                # Read file and upload to MinIO
                with open(file_path, 'rb') as f:
                    content = File(f, name=os.path.basename(file_path))
                    saved_name = minio_storage.save(minio_key, content)
                    self.stdout.write(f'    Uploaded to MinIO: {saved_name}')
                    migrated_count += 1
            except Exception as e:
                self.stderr.write(f'    FAILED to upload {file_path}: {e}')
                logger.error(f'Failed to upload avatar {file_path}: {e}')

        # Update user avatar references
        users_with_avatars = User.objects.exclude(avatar='').exclude(avatar__isnull=True)
        for user in users_with_avatars:
            if user.avatar:
                avatar_name = user.avatar.name
                minio_path = f'avatars/{Path(avatar_name).name}'
                
                # Check if avatar exists in MinIO
                if not minio_storage.exists(minio_path):
                    try:
                        # Re-upload from the file reference
                        if hasattr(user.avatar, 'path'):
                            local_path = getattr(user.avatar, 'path', None)
                            # Skip corrupted/0-byte files
                            if local_path and os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                                with open(local_path, 'rb') as f:
                                    content = File(f, name=os.path.basename(user.avatar.name))
                                    saved_name = minio_storage.save(minio_path, content)
                                    self.stdout.write(f'  Updated user {user.id} avatar to: {saved_name}')
                            else:
                                self.stderr.write(f'  SKIPPED user {user.id} avatar: file missing or 0 bytes')
                        else:
                            self.stderr.write(f'  SKIPPED user {user.id} avatar: no local path available')
                    except Exception as e:
                        self.stderr.write(f'  FAILED to update avatar for user {user.id}: {e}')

        return migrated_count

    def migrate_media_assets(self, minio_storage, dry_run=False):
        """Migrate media asset files from local filesystem to MinIO."""
        media_root = getattr(settings, 'MEDIA_ROOT', None)
        if not media_root:
            self.stderr.write(self.style.ERROR('MEDIA_ROOT not configured'))
            return 0

        media_assets_dir = Path(media_root) / 'media_assets'
        if not media_assets_dir.exists():
            self.stdout.write(self.style.WARNING(f'Media assets directory does not exist: {media_assets_dir}'))
            return 0

        # Find all files in media_assets directory (excluding thumbnails)
        all_files = glob.glob(str(media_assets_dir / '**' / '*'), recursive=True)
        all_files = [f for f in all_files if os.path.isfile(f)]
        
        # Filter out thumbnail files (they'll be regenerated)
        non_thumb_files = [f for f in all_files if '/thumbnails/' not in f]
        
        self.stdout.write(f'Found {len(non_thumb_files)} media asset files to migrate')

        migrated_count = 0
        for file_path in non_thumb_files:
            relative_path = Path(file_path).relative_to(media_assets_dir.parent)
            
            # Determine storage path
            storage_path = f'media_assets/{relative_path}'
            
            self.stdout.write(f'  Processing: {storage_path}')
            
            if dry_run:
                self.stdout.write(f'    [DRY-RUN] Would upload to MinIO')
                migrated_count += 1
                continue
            
            # Check if already in MinIO
            if minio_storage.exists(storage_path):
                self.stdout.write(f'    Already exists in MinIO, skipping')
                continue
            
            try:
                # Read file and upload to MinIO
                with open(file_path, 'rb') as f:
                    content = File(f, name=os.path.basename(file_path))
                    saved_name = minio_storage.save(storage_path, content)
                    
                    # Update MediaAsset record if exists
                    filename = os.path.basename(file_path)
                    assets = MediaAsset.objects.filter(original_filename=filename)
                    for asset in assets:
                        if not asset.storage_path or asset.storage_backend != 'minio':
                            asset.storage_path = saved_name
                            asset.storage_backend = 'minio'
                            asset.save(update_fields=['storage_path', 'storage_backend'])
                            self.stdout.write(f'    Updated MediaAsset {asset.id} storage info')
                    
                    self.stdout.write(f'    Uploaded to MinIO: {saved_name}')
                    migrated_count += 1
            except Exception as e:
                self.stderr.write(f'    FAILED to upload {file_path}: {e}')
                logger.error(f'Failed to upload media asset {file_path}: {e}')

        return migrated_count

    def verify_existing_uploads(self):
        """Verify that existing files are correctly stored in MinIO."""
        self.stdout.write(self.style.WARNING('Verifying existing MinIO uploads...'))
        
        try:
            minio_storage = MinIODjangoStorage()
            ok, err = minio_storage.test_connection()
            if not ok:
                self.stderr.write(self.style.ERROR(f'MinIO connection failed: {err}'))
                return
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Failed to initialize MinIO storage: {e}'))
            return

        # Verify avatars
        users_with_avatars = User.objects.exclude(avatar='').exclude(avatar__isnull=True)
        avatar_ok = 0
        avatar_fail = 0
        
        for user in users_with_avatars:
            if user.avatar:
                # The avatar.name is the storage path
                avatar_name = user.avatar.name
                minio_path = f'avatars/{Path(avatar_name).name}'
                
                if minio_storage.exists(minio_path):
                    avatar_ok += 1
                else:
                    self.stderr.write(f'  Avatar MISSING for user {user.id}: {minio_path}')
                    avatar_fail += 1

        self.stdout.write(f'Avatar verification: {avatar_ok} OK, {avatar_fail} FAILED')

        # Verify media assets
        assets = MediaAsset.objects.exclude(storage_path='').exclude(storage_path__isnull=True)
        asset_ok = 0
        asset_fail = 0
        
        for asset in assets:
            if asset.storage_path:
                # storage_path should be the key in MinIO
                if minio_storage.exists(asset.storage_path):
                    asset_ok += 1
                else:
                    self.stderr.write(f'  MediaAsset MISSING: ID={asset.id}, path={asset.storage_path}')
                    asset_fail += 1

        self.stdout.write(f'MediaAsset verification: {asset_ok} OK, {asset_fail} FAILED')
        
        if avatar_fail == 0 and asset_fail == 0:
            self.stdout.write(self.style.SUCCESS('All files verified in MinIO!'))
        else:
            self.stdout.write(self.style.WARNING(
                f'Verification complete with {avatar_fail + asset_fail} missing files. '
                f'Run without --verify to migrate missing files.'
            ))