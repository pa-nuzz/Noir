import io
import logging
import mimetypes
import os
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import BinaryIO, Optional, Tuple
from urllib.parse import urlparse

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024


def _clean_value(value):
    if not value:
        return value
    value = value.strip().strip("'\"").strip()
    return value


def _normalize_s3_endpoint(endpoint_url, bucket, use_path_style):
    if not endpoint_url:
        return endpoint_url, use_path_style

    endpoint_url = endpoint_url.strip().rstrip('/')
    bucket_clean = _clean_value(bucket or '').lower()
    if not bucket_clean:
        return endpoint_url, use_path_style

    parsed = urlparse(endpoint_url)
    hostname = parsed.hostname or ''

    if hostname.startswith(bucket_clean + '.'):
        hostname = hostname[len(bucket_clean) + 1:]
        port_part = f":{parsed.port}" if parsed.port else ""
        netloc = f"{hostname}{port_part}"
        endpoint_url = parsed._replace(netloc=netloc).geturl().rstrip('/')

    return endpoint_url, use_path_style


def _slugify(value):
    value = str(value or '').lower().strip()
    value = re.sub(r'[^\w\s-]', '', value)
    value = re.sub(r'[-\s]+', '-', value).strip('-')
    return value or 'untitled'


class BaseStorage(ABC):
    backend_name = 'base'

    @abstractmethod
    def save(self, path: str, content, content_type: str = None) -> str:
        ...

    @abstractmethod
    def open(self, path: str) -> BinaryIO:
        ...

    @abstractmethod
    def delete(self, path: str) -> bool:
        ...

    @abstractmethod
    def exists(self, path: str) -> bool:
        ...

    @abstractmethod
    def size(self, path: str) -> int:
        ...

    @abstractmethod
    def url(self, path: str) -> str:
        ...

    def get_signed_url(self, path: str, expiration: int = 3600) -> str:
        return self.url(path)

    def test_connection(self) -> Tuple[bool, str]:
        try:
            probe_name = f"dia_probe_{timezone.now().timestamp()}.txt"
            probe_key = self.save("", ContentFile(b"ok", name=probe_name), content_type='text/plain')
            data = self.open(probe_key).read()
            self.delete(probe_key)
            if data == b"ok":
                return True, ""
            return False, "Probe round-trip failed"
        except Exception as exc:
            return False, str(exc)


def _safe_filename(name: str) -> str:
    name = name or 'file'
    name = name.replace('\\', '/').split('/')[-1]
    name = re.sub(r'[^A-Za-z0-9._-]+', '_', name).strip('._')
    return name or 'file'


def _guess_content_type(name: str, fallback: str = None) -> str:
    if fallback:
        return fallback
    ctype, _ = mimetypes.guess_type(name)
    return ctype or 'application/octet-stream'


class LocalStorage(BaseStorage):
    backend_name = 'local'

    def save(self, path, content, content_type=None):
        if hasattr(content, 'chunks'):
            data = b''.join(content.chunks())
        elif hasattr(content, 'read'):
            data = content.read()
            if hasattr(content, 'seek'):
                content.seek(0)
        else:
            data = content
        name = _safe_filename(getattr(content, 'name', os.path.basename(path)))
        full_path = f"{path}/{name}" if path and not path.endswith(name) else (path or name)
        if default_storage.exists(full_path):
            base, ext = os.path.splitext(full_path)
            counter = 1
            while default_storage.exists(f"{base}_{counter}{ext}"):
                counter += 1
            full_path = f"{base}_{counter}{ext}"
        saved = default_storage.save(full_path, ContentFile(data))
        return saved

    def open(self, path):
        return default_storage.open(path)

    def delete(self, path):
        if default_storage.exists(path):
            default_storage.delete(path)
            return True
        return False

    def exists(self, path):
        return default_storage.exists(path)

    def size(self, path):
        try:
            return default_storage.size(path)
        except Exception:
            return 0

    def url(self, path):
        return default_storage.url(path)


class GoogleDriveStorage(BaseStorage):
    backend_name = 'google_drive'
    CHUNK_SIZE = 5 * 1024 * 1024

    def __init__(self, config):
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        self.config = config
        self.folder_id = config.google_drive_folder_id
        self._scopes = settings.GOOGLE_DRIVE_OAUTH_SCOPES
        self._creds = None
        self._service = None
        self._request = Request()

    def _build_credentials(self):
        from google.oauth2.credentials import Credentials

        refresh_token = self.config.get_google_drive_refresh_token()
        if not refresh_token:
            raise RuntimeError("Google Drive refresh token is missing. Reconnect the account.")

        client_id = self.config.get_google_drive_client_id()
        client_secret = self.config.get_google_drive_client_secret()
        if not client_id or not client_secret:
            raise RuntimeError(
                "Google Drive OAuth credentials are not configured for this workspace. "
                "Save your Client ID and Client Secret in storage settings, then reconnect."
            )

        creds = Credentials(
            token=self.config.google_drive_access_token or None,
            refresh_token=refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=client_id,
            client_secret=client_secret,
            scopes=self._scopes,
        )
        if creds.expired or not creds.valid:
            creds.refresh(self._request)
            self.config.google_drive_access_token = creds.token or ''
            self.config.google_drive_token_expiry = creds.expiry
            self.config.save(update_fields=['google_drive_access_token', 'google_drive_token_expiry', 'updated_at'])
        self._creds = creds
        return creds

    def _service_cached(self):
        if self._service is None:
            from googleapiclient.discovery import build
            creds = self._build_credentials()
            self._service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        return self._service

    def save(self, path, content, content_type=None):
        from googleapiclient.http import MediaIoBaseUpload

        if hasattr(content, 'chunks'):
            data = b''.join(content.chunks())
            name = _safe_filename(getattr(content, 'name', os.path.basename(path)))
        elif hasattr(content, 'read'):
            data = content.read()
            if hasattr(content, 'seek'):
                content.seek(0)
            name = _safe_filename(getattr(content, 'name', os.path.basename(path)))
        else:
            data = content if isinstance(content, (bytes, bytearray)) else content.read()
            name = _safe_filename(os.path.basename(path))

        if len(data) > MAX_FILE_SIZE_BYTES:
            raise ValueError(f"File too large for Google Drive: {len(data)} bytes")

        ctype = _guess_content_type(name, content_type)
        service = self._service_cached()

        file_metadata = {
            'name': name,
            'parents': [self.folder_id] if self.folder_id else [],
        }

        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=ctype, resumable=True)
        uploaded = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,name,size,mimeType,webContentLink,webViewLink',
            supportsAllDrives=True,
        ).execute()

        file_id = uploaded.get('id')
        logger.info("Google Drive upload ok: %s (%s bytes)", file_id, uploaded.get('size'))
        return file_id

    def open(self, path):
        from googleapiclient.http import MediaIoBaseDownload

        service = self._service_cached()
        request = service.files().get_media(fileId=path, supportsAllDrives=True)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        buffer.seek(0)
        return buffer

    def delete(self, path):
        try:
            service = self._service_cached()
            service.files().delete(fileId=path, supportsAllDrives=True).execute()
            return True
        except Exception as exc:
            logger.warning("Drive delete failed for %s: %s", path, exc)
            return False

    def exists(self, path):
        try:
            service = self._service_cached()
            service.files().get(fileId=path, fields='id', supportsAllDrives=True).execute()
            return True
        except Exception:
            return False

    def size(self, path):
        try:
            service = self._service_cached()
            meta = service.files().get(fileId=path, fields='size', supportsAllDrives=True).execute()
            return int(meta.get('size') or 0)
        except Exception:
            return 0

    def url(self, path):
        return f"https://drive.google.com/uc?export=download&id={path}"

    def get_signed_url(self, path, expiration=3600):
        try:
            service = self._service_cached()
            meta = service.files().get(
                fileId=path,
                fields='webContentLink,webViewLink',
                supportsAllDrives=True,
            ).execute()
            return meta.get('webContentLink') or meta.get('webViewLink') or self.url(path)
        except Exception:
            return self.url(path)

    def test_connection(self) -> Tuple[bool, str]:
        try:
            service = self._service_cached()
            service.files().get(fileId=self.folder_id, fields='id', supportsAllDrives=True).execute()
            return True, ""
        except Exception as exc:
            return False, str(exc)


class S3CompatibleStorage(BaseStorage):
    backend_name = 's3_compatible'

    def __init__(self, config, user=None, workspace=None):
        import boto3
        from botocore.client import Config as BotoConfig

        self.config = config
        self.bucket = _clean_value(config.s3_bucket)
        self.public_base = (config.s3_public_base_url or '').rstrip('/')

        custom_prefix = _clean_value(config.s3_path_prefix or '')
        if custom_prefix:
            self.prefix = custom_prefix.rstrip('/')
        elif user and workspace:
            self.prefix = _compute_storage_prefix(user, workspace)
        else:
            workspace_folder = f"workspace_{config.workspace_id}" if config.workspace_id else ""
            self.prefix = workspace_folder

        endpoint = _clean_value(config.s3_endpoint_url) or None
        use_path_style = config.s3_use_path_style
        endpoint, use_path_style = _normalize_s3_endpoint(endpoint, self.bucket, use_path_style)

        self._client = boto3.client(
            's3',
            endpoint_url=endpoint,
            region_name=_clean_value(config.s3_region) or 'us-east-1',
            aws_access_key_id=_clean_value(config.get_s3_access_key()),
            aws_secret_access_key=_clean_value(config.get_s3_secret_key()),
            config=BotoConfig(
                signature_version='s3v4',
                s3={'addressing_style': 'path' if use_path_style else 'virtual'},
            ),
        )

    def _key(self, path):
        if not path:
            return self.prefix
        path = path.lstrip('/')
        if self.prefix and not path.startswith(self.prefix + '/'):
            return f"{self.prefix}/{path}"
        return path

    def _strip_prefix(self, key):
        if self.prefix and key.startswith(self.prefix + '/'):
            return key[len(self.prefix) + 1:]
        return key

    def save(self, path, content, content_type=None):
        if hasattr(content, 'chunks'):
            data = b''.join(content.chunks())
            name = _safe_filename(getattr(content, 'name', os.path.basename(path)))
        elif hasattr(content, 'read'):
            data = content.read()
            if hasattr(content, 'seek'):
                content.seek(0)
            name = _safe_filename(getattr(content, 'name', os.path.basename(path)))
        else:
            data = content if isinstance(content, (bytes, bytearray)) else content.read()
            name = _safe_filename(os.path.basename(path))

        full_key = self._key(f"{path}/{name}") if path and not path.endswith(name) else self._key(path or name)

        base, ext = os.path.splitext(full_key)
        counter = 1
        final_key = full_key
        while self._object_exists(final_key):
            final_key = f"{base}_{counter}{ext}"
            counter += 1

        ctype = _guess_content_type(name, content_type)
        self._client.put_object(
            Bucket=self.bucket,
            Key=final_key,
            Body=data,
            ContentType=ctype,
        )
        return self._strip_prefix(final_key)

    def _object_exists(self, key):
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def open(self, path):
        obj = self._client.get_object(Bucket=self.bucket, Key=self._key(path))
        return io.BytesIO(obj['Body'].read())

    def delete(self, path):
        try:
            self._client.delete_object(Bucket=self.bucket, Key=self._key(path))
            return True
        except Exception as exc:
            logger.warning("S3 delete failed for %s: %s", path, exc)
            return False

    def exists(self, path):
        return self._object_exists(self._key(path))

    def size(self, path):
        try:
            return int(self._client.head_object(Bucket=self.bucket, Key=self._key(path)).get('ContentLength', 0))
        except Exception:
            return 0

    def url(self, path):
        key = self._key(path)
        if self.public_base:
            return f"{self.public_base}/{key}"
        return self._client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket, 'Key': key},
            ExpiresIn=3600,
        )

    def get_signed_url(self, path, expiration=3600):
        if self.public_base:
            return f"{self.public_base}/{self._key(path)}"
        return self._client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket, 'Key': self._key(path)},
            ExpiresIn=expiration,
        )

    def test_connection(self) -> Tuple[bool, str]:
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except Exception:
            try:
                self._client.create_bucket(Bucket=self.bucket)
                logger.info("Created bucket %s", self.bucket)
            except Exception as create_err:
                return False, f"Cannot access bucket '{self.bucket}': {create_err}"

        try:
            probe_key = f"{self.prefix}/_dia_probe_{timezone.now().timestamp()}".lstrip('/')
            self._client.put_object(Bucket=self.bucket, Key=probe_key, Body=b"ok")
            obj = self._client.get_object(Bucket=self.bucket, Key=probe_key)
            data = obj['Body'].read()
            self._client.delete_object(Bucket=self.bucket, Key=probe_key)
            if data == b"ok":
                return True, ""
            return False, "Probe round-trip failed"
        except Exception as exc:
            return False, str(exc)


class DiaS3Storage(BaseStorage):
    backend_name = 'dia_s3'

    def __init__(self, user=None, workspace=None, workspace_id=None):
        import boto3
        from botocore.client import Config as BotoConfig

        required = [
            ('DIA_S3_ENDPOINT_URL', settings.DIA_S3_ENDPOINT_URL),
            ('DIA_S3_BUCKET', settings.DIA_S3_BUCKET),
            ('DIA_S3_ACCESS_KEY', settings.DIA_S3_ACCESS_KEY),
            ('DIA_S3_SECRET_KEY', settings.DIA_S3_SECRET_KEY),
        ]
        missing = [name for name, val in required if not _clean_value(val)]
        if missing:
            raise RuntimeError(f"DIA S3 missing required settings: {', '.join(missing)}. Check your .env file.")

        self.bucket = _clean_value(settings.DIA_S3_BUCKET)
        self.public_base = (settings.DIA_S3_PUBLIC_BASE_URL or '').rstrip('/')

        if user and workspace:
            self.prefix = _compute_storage_prefix(user, workspace)
        elif workspace_id:
            self.prefix = f"workspace_{workspace_id}"
        else:
            self.prefix = (_clean_value(settings.DIA_S3_PATH_PREFIX) or '').rstrip('/')

        endpoint = _clean_value(settings.DIA_S3_ENDPOINT_URL) or None
        use_path_style = str(settings.DIA_S3_USE_PATH_STYLE).lower() in ('true', '1', 'yes')
        endpoint, use_path_style = _normalize_s3_endpoint(endpoint, self.bucket, use_path_style)

        self._client = boto3.client(
            's3',
            endpoint_url=endpoint,
            region_name=_clean_value(settings.DIA_S3_REGION) or 'us-east-1',
            aws_access_key_id=_clean_value(settings.DIA_S3_ACCESS_KEY),
            aws_secret_access_key=_clean_value(settings.DIA_S3_SECRET_KEY),
            config=BotoConfig(
                signature_version='s3v4',
                s3={'addressing_style': 'path' if use_path_style else 'virtual'},
            ),
        )

    def _key(self, path):
        if not path:
            return self.prefix
        path = path.lstrip('/')
        if self.prefix and not path.startswith(self.prefix + '/'):
            return f"{self.prefix}/{path}"
        return path

    def _strip_prefix(self, key):
        if self.prefix and key.startswith(self.prefix + '/'):
            return key[len(self.prefix) + 1:]
        return key

    def save(self, path, content, content_type=None):
        if hasattr(content, 'chunks'):
            data = b''.join(content.chunks())
            name = _safe_filename(getattr(content, 'name', os.path.basename(path)))
        elif hasattr(content, 'read'):
            data = content.read()
            if hasattr(content, 'seek'):
                content.seek(0)
            name = _safe_filename(getattr(content, 'name', os.path.basename(path)))
        else:
            data = content if isinstance(content, (bytes, bytearray)) else content.read()
            name = _safe_filename(os.path.basename(path))

        full_key = self._key(f"{path}/{name}") if path and not path.endswith(name) else self._key(path or name)

        base, ext = os.path.splitext(full_key)
        counter = 1
        final_key = full_key
        while self._object_exists(final_key):
            final_key = f"{base}_{counter}{ext}"
            counter += 1

        ctype = _guess_content_type(name, content_type)
        self._client.put_object(
            Bucket=self.bucket,
            Key=final_key,
            Body=data,
            ContentType=ctype,
        )
        return self._strip_prefix(final_key)

    def _object_exists(self, key):
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def open(self, path):
        obj = self._client.get_object(Bucket=self.bucket, Key=self._key(path))
        return io.BytesIO(obj['Body'].read())

    def delete(self, path):
        try:
            self._client.delete_object(Bucket=self.bucket, Key=self._key(path))
            return True
        except Exception as exc:
            logger.warning("DIA S3 delete failed for %s: %s", path, exc)
            return False

    def exists(self, path):
        return self._object_exists(self._key(path))

    def size(self, path):
        try:
            return int(self._client.head_object(Bucket=self.bucket, Key=self._key(path)).get('ContentLength', 0))
        except Exception:
            return 0

    def url(self, path):
        key = self._key(path)
        if self.public_base:
            return f"{self.public_base}/{key}"
        return self._client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket, 'Key': key},
            ExpiresIn=3600,
        )

    def get_signed_url(self, path, expiration=3600):
        if self.public_base:
            return f"{self.public_base}/{self._key(path)}"
        return self._client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket, 'Key': self._key(path)},
            ExpiresIn=expiration,
        )

    def test_connection(self):
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except Exception:
            try:
                self._client.create_bucket(Bucket=self.bucket)
                logger.info("Created bucket %s", self.bucket)
            except Exception as create_err:
                return False, f"Cannot access bucket '{self.bucket}': {create_err}"

        try:
            probe_key = f"{self.prefix}/_dia_probe_{timezone.now().timestamp()}".lstrip('/')
            self._client.put_object(Bucket=self.bucket, Key=probe_key, Body=b"ok")
            obj = self._client.get_object(Bucket=self.bucket, Key=probe_key)
            data = obj['Body'].read()
            self._client.delete_object(Bucket=self.bucket, Key=probe_key)
            if data == b"ok":
                return True, ""
            return False, "Probe round-trip failed"
        except Exception as exc:
            return False, str(exc)


def _compute_storage_prefix(user, workspace):
    prefix = (_clean_value(settings.MINIO_PATH_PREFIX) or 'media').rstrip('/')
    return f"{prefix}/workspace_{workspace.id}"


class MinIOStorage(BaseStorage):
    backend_name = 'minio'

    def __init__(self, user=None, workspace=None, workspace_id=None):
        import boto3
        from botocore.client import Config as BotoConfig

        required = [
            ('MINIO_ENDPOINT_URL', settings.MINIO_ENDPOINT_URL),
            ('MINIO_BUCKET', settings.MINIO_BUCKET),
            ('MINIO_ACCESS_KEY', settings.MINIO_ACCESS_KEY),
            ('MINIO_SECRET_KEY', settings.MINIO_SECRET_KEY),
        ]
        missing = [name for name, val in required if not _clean_value(val)]
        if missing:
            raise RuntimeError(f"MinIO missing required settings: {', '.join(missing)}. Check your .env file.")

        self.bucket = _clean_value(settings.MINIO_BUCKET)
        self.public_base = (settings.MINIO_PUBLIC_BASE_URL or '').rstrip('/')

        if user and workspace:
            self.prefix = _compute_storage_prefix(user, workspace)
        elif workspace_id:
            self.prefix = f"workspace_{workspace_id}"
        else:
            self.prefix = (_clean_value(settings.MINIO_PATH_PREFIX) or '').rstrip('/')

        endpoint = _clean_value(settings.MINIO_ENDPOINT_URL) or None
        use_path_style = str(settings.MINIO_USE_PATH_STYLE).lower() in ('true', '1', 'yes')
        endpoint, use_path_style = _normalize_s3_endpoint(endpoint, self.bucket, use_path_style)

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

    def _key(self, path):
        if not path:
            return self.prefix
        path = path.lstrip('/')
        if self.prefix and not path.startswith(self.prefix + '/'):
            return f"{self.prefix}/{path}"
        return path

    def _strip_prefix(self, key):
        if self.prefix and key.startswith(self.prefix + '/'):
            return key[len(self.prefix) + 1:]
        return key

    def save(self, path, content, content_type=None):
        if hasattr(content, 'chunks'):
            data = b''.join(content.chunks())
            name = _safe_filename(getattr(content, 'name', os.path.basename(path)))
        elif hasattr(content, 'read'):
            data = content.read()
            if hasattr(content, 'seek'):
                content.seek(0)
            name = _safe_filename(getattr(content, 'name', os.path.basename(path)))
        else:
            data = content if isinstance(content, (bytes, bytearray)) else content.read()
            name = _safe_filename(os.path.basename(path))

        full_key = self._key(f"{path}/{name}") if path and not path.endswith(name) else self._key(path or name)
        full_key = full_key.replace('\\', '/')

        base, ext = os.path.splitext(full_key)
        counter = 1
        final_key = full_key
        while self._object_exists(final_key):
            final_key = f"{base}_{counter}{ext}"
            counter += 1

        ctype = _guess_content_type(name, content_type)
        self._client.put_object(
            Bucket=self.bucket,
            Key=final_key,
            Body=data,
            ContentType=ctype,
        )
        return self._strip_prefix(final_key)

    def _object_exists(self, key):
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def open(self, path):
        obj = self._client.get_object(Bucket=self.bucket, Key=self._key(path))
        return io.BytesIO(obj['Body'].read())

    def delete(self, path):
        try:
            self._client.delete_object(Bucket=self.bucket, Key=self._key(path))
            return True
        except Exception as exc:
            logger.warning("MinIO delete failed for %s: %s", path, exc)
            return False

    def exists(self, path):
        return self._object_exists(self._key(path))

    def size(self, path):
        try:
            return int(self._client.head_object(Bucket=self.bucket, Key=self._key(path)).get('ContentLength', 0))
        except Exception:
            return 0

    def url(self, path):
        key = self._key(path)
        if self.public_base:
            return f"{self.public_base}/{key}"
        return self._client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket, 'Key': key},
            ExpiresIn=3600,
        )

    def get_signed_url(self, path, expiration=3600):
        if self.public_base:
            return f"{self.public_base}/{self._key(path)}"
        return self._client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket, 'Key': self._key(path)},
            ExpiresIn=expiration,
        )

    def test_connection(self):
        try:
            self._client.head_bucket(Bucket=self.bucket)
        except Exception:
            try:
                self._client.create_bucket(Bucket=self.bucket)
                logger.info("Created MinIO bucket %s", self.bucket)
            except Exception as create_err:
                return False, f"Cannot access bucket '{self.bucket}': {create_err}"

        try:
            probe_key = f"{self.prefix}/_minio_probe_{timezone.now().timestamp()}".lstrip('/')
            self._client.put_object(Bucket=self.bucket, Key=probe_key, Body=b"ok")
            obj = self._client.get_object(Bucket=self.bucket, Key=probe_key)
            data = obj['Body'].read()
            self._client.delete_object(Bucket=self.bucket, Key=probe_key)
            if data == b"ok":
                return True, ""
            return False, "Probe round-trip failed"
        except Exception as exc:
            return False, str(exc)


class StorageService:
    def __init__(self, backend: BaseStorage, config=None):
        self.backend = backend
        self.config = config

    def save(self, path, content, content_type=None):
        return self.backend.save(path, content, content_type=content_type)

    def delete(self, path):
        return self.backend.delete(path)

    def url(self, path):
        return self.backend.url(path)

    def signed_url(self, path, expiration=3600):
        return self.backend.get_signed_url(path, expiration=expiration)

    def open(self, path):
        return self.backend.open(path)

    def exists(self, path):
        return self.backend.exists(path)

    def size(self, path):
        return self.backend.size(path)

    def test_connection(self):
        return self.backend.test_connection()

    @classmethod
    def for_user(cls, user) -> 'StorageService':
        from apps.workspaces.models import WorkspaceStorageConfig, get_or_create_personal_workspace
        workspace = get_or_create_personal_workspace(user)
        return cls.for_workspace(workspace, user=user)

    @classmethod
    def for_workspace(cls, workspace, user=None) -> 'StorageService':
        from apps.workspaces.models import WorkspaceStorageConfig

        config, _ = WorkspaceStorageConfig.objects.get_or_create(
            workspace=workspace,
            defaults={'backend': WorkspaceStorageConfig.BACKEND_MINIO},
        )

        # Enforce MinIO only - auto-migrate old configs
        if config.backend != WorkspaceStorageConfig.BACKEND_MINIO:
            config.backend = WorkspaceStorageConfig.BACKEND_MINIO
            config.save(update_fields=['backend'])

        if not settings.MINIO_BUCKET:
            raise ValueError("MINIO_BUCKET must be set in .env for MinIO storage")

        storage = MinIOStorage(user=user, workspace=workspace)
        ok, err = storage.test_connection()
        if not ok:
            raise ConnectionError(f"MinIO connection failed: {err}. Check your MinIO configuration.")

        return cls(storage, config=config)
