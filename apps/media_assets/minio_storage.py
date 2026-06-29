"""
Django-compatible MinIO storage backend.
Replaces FileSystemStorage for all uploaded media files.
"""

import io
import logging
import mimetypes
import os
import re
from datetime import datetime
from urllib.parse import urlparse

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils import timezone

logger = logging.getLogger(__name__)


def _clean_value(value):
    """Clean environment variable values."""
    if not value:
        return value
    return value.strip().strip("'\"").strip()


def _safe_filename(name: str) -> str:
    """Make filename safe for all storage backends."""
    name = name or 'file'
    name = name.replace('\\', '/').split('/')[-1]
    name = re.sub(r'[^A-Za-z0-9._-]+', '_', name).strip('._')
    return name or 'file'


def _guess_content_type(name: str, fallback: str = None) -> str:
    """Guess content type from filename."""
    if fallback:
        return fallback
    ctype, _ = mimetypes.guess_type(name)
    return ctype or 'application/octet-stream'


class MinIODjangoStorage(Storage):
    """
    Django-compatible MinIO storage backend.
    
    This storage backend:
    - Stores ALL uploaded files in MinIO (no local filesystem)
    - Works in both DEBUG=True and DEBUG=False
    - Generates proper public URLs for files
    - Compatible with Django's FileField and ImageField
    """
    
    def __init__(self, prefix=None):
        """
        Initialize MinIO storage.
        
        Args:
            prefix: Optional prefix for all files. If not provided, uses MINIO_PATH_PREFIX.
        """
        import boto3
        from botocore.client import Config as BotoConfig
        
        # Validate required settings
        required = [
            ('MINIO_ENDPOINT_URL', settings.MINIO_ENDPOINT_URL),
            ('MINIO_BUCKET', settings.MINIO_BUCKET),
            ('MINIO_ACCESS_KEY', settings.MINIO_ACCESS_KEY),
            ('MINIO_SECRET_KEY', settings.MINIO_SECRET_KEY),
        ]
        missing = [name for name, val in required if not _clean_value(val)]
        if missing:
            raise ValueError(
                f"MinIO missing required settings: {', '.join(missing)}. "
                f"Check your .env file."
            )
        
        self.bucket = _clean_value(settings.MINIO_BUCKET)
        self.public_base = (settings.MINIO_PUBLIC_BASE_URL or '').rstrip('/')
        
        # Use provided prefix or fall back to MINIO_PATH_PREFIX
        custom_prefix = prefix or (_clean_value(settings.MINIO_PATH_PREFIX) or '').rstrip('/')
        
        # If MINIO_PATH_PREFIX is set, use it as the base prefix
        if custom_prefix:
            self.prefix = custom_prefix
        else:
            self.prefix = 'media'
        
        endpoint = _clean_value(settings.MINIO_ENDPOINT_URL) or None
        use_path_style = str(settings.MINIO_USE_PATH_STYLE).lower() in ('true', '1', 'yes')
        
        # Normalize endpoint
        endpoint = endpoint.strip().rstrip('/')
        parsed = urlparse(endpoint)
        hostname = parsed.hostname or ''
        bucket_clean = self.bucket.lower()
        
        if hostname.startswith(bucket_clean + '.'):
            hostname = hostname[len(bucket_clean) + 1:]
            port_part = f":{parsed.port}" if parsed.port else ""
            netloc = f"{hostname}{port_part}"
            endpoint = parsed._replace(netloc=netloc).geturl().rstrip('/')
        
        self._client = boto3.client(
            's3',
            endpoint_url=endpoint,
            region_name=_clean_value(settings.MINIO_REGION) or 'us-east-1',
            aws_access_key_id=_clean_value(settings.MINIO_ACCESS_KEY),
            aws_secret_access_key=_clean_value(settings.MINIO_SECRET_KEY),
            config=BotoConfig(
                signature_version='s3v4',
                s3={'addressing_style': 'path' if use_path_style else 'virtual'},
            ),
        )
    
    def _key(self, name):
        """Build the full MinIO key from the name."""
        if not name:
            return self.prefix
        name = name.lstrip('/')
        name = name.replace('\\', '/')
        if self.prefix and not name.startswith(self.prefix):
            return f"{self.prefix}/{name}"
        return name
    
    def _strip_prefix(self, key):
        """Strip the prefix from a key."""
        if self.prefix and key.startswith(self.prefix + '/'):
            return key[len(self.prefix) + 1:]
        if self.prefix and key == self.prefix:
            return ''
        return key
    
    def _object_exists(self, key):
        """Check if an object exists in MinIO."""
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False
    
    def _generate_unique_name(self, name):
        """Generate a unique name to avoid overwrites."""
        key = self._key(name)
        
        if not self._object_exists(key):
            return name
        
        base, ext = os.path.splitext(key)
        counter = 1
        while True:
            new_key = f"{base}_{counter}{ext}"
            if not self._object_exists(new_key):
                return self._strip_prefix(new_key)
            counter += 1
    
    # Django Storage required methods
    
    def _open(self, name, mode='rb'):
        """Open a file for reading."""
        key = self._key(name)
        try:
            obj = self._client.get_object(Bucket=self.bucket, Key=key)
            return io.BytesIO(obj['Body'].read())
        except Exception as e:
            raise FileNotFoundError(f"File '{name}' not found in MinIO: {e}")
    
    def _save(self, name, content, max_length=None):
        """
        Save content to MinIO.
        
        Args:
            name: The name to save the file as
            content: The file content (File object or bytes)
            max_length: Optional maximum length validation
            
        Returns:
            The name of the file that was saved
        """
        # Generate unique name if file exists
        name = self._generate_unique_name(name)
        key = self._key(name)
        
        # Read content data
        if hasattr(content, 'chunks'):
            data = b''.join(content.chunks())
            content_name = getattr(content, 'name', None)
            if content_name:
                content_name = os.path.basename(content_name)
            else:
                content_name = os.path.basename(name)
        elif hasattr(content, 'read'):
            data = content.read()
            content_name = getattr(content, 'name', None)
            if content_name:
                content_name = os.path.basename(content_name)
            else:
                content_name = os.path.basename(name)
            if hasattr(content, 'seek'):
                content.seek(0)
        else:
            data = content
            content_name = os.path.basename(name)
        
        # Determine content type
        content_type = _guess_content_type(content_name or name)
        
        # Save to MinIO
        self._client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        
        logger.info(f"Uploaded to MinIO: {key} ({len(data)} bytes)")
        return self._strip_prefix(key)
    
    def delete(self, name):
        """Delete a file from MinIO."""
        key = self._key(name)
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
            logger.info(f"Deleted from MinIO: {key}")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete from MinIO: {key} - {e}")
            return False
    
    def exists(self, name):
        """Check if a file exists in MinIO."""
        return self._object_exists(self._key(name))
    
    def url(self, name):
        """
        Generate a public URL for the file.
        
        For production, uses MINIO_PUBLIC_BASE_URL if configured.
        For development, generates a presigned URL.
        """
        key = self._key(name)
        
        if self.public_base:
            return f"{self.public_base}/{key}"
        
        # Generate presigned URL for development
        return self._client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket, 'Key': key},
            ExpiresIn=3600,
        )
    
    def get_accessed_time(self, name):
        """Get the last accessed time (not supported by MinIO, returns modified)."""
        return self.get_modified_time(name)
    
    def get_created_time(self, name):
        """Get the creation time (not supported by MinIO, returns modified)."""
        return self.get_modified_time(name)
    
    def get_modified_time(self, name):
        """Get the last modified time from MinIO."""
        key = self._key(name)
        try:
            response = self._client.head_object(Bucket=self.bucket, Key=key)
            last_modified = response.get('LastModified', timezone.now())
            return last_modified
        except Exception:
            return timezone.now()
    
    def get_available_name(self, name, max_length=None):
        """
        Return a filename that's available in storage.
        
        Since MinIO doesn't have real path limitations, we just ensure uniqueness.
        """
        if max_length and len(name) > max_length:
            name = name[:max_length]
        return self._generate_unique_name(name)
    
    def generate_filename(self, filename):
        """Generate a safe filename."""
        return _safe_filename(filename)
    
    def size(self, name):
        """Get the size of a file in MinIO."""
        key = self._key(name)
        try:
            response = self._client.head_object(Bucket=self.bucket, Key=key)
            return int(response.get('ContentLength', 0))
        except Exception:
            return 0
    
    def test_connection(self):
        """Test if MinIO connection is working."""
        try:
            self._client.head_bucket(Bucket=self.bucket)
            return True, ""
        except Exception as e:
            return False, str(e)


# Singleton instance for use as Django's default storage
_default_storage = None


def get_default_storage():
    """Get the default MinIO storage instance."""
    global _default_storage
    if _default_storage is None:
        _default_storage = MinIODjangoStorage()
    return _default_storage