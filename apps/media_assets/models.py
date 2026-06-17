import os
import uuid

from django.conf import settings
from django.db import models

from core.models import AuditMixin
from core.tenant import TenantManager


class MediaFolder(AuditMixin):
    objects = TenantManager()
    name = models.CharField(max_length=255)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subfolders')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='asset_folders')
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, null=True, blank=True, related_name='media_folders')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('name', 'parent', 'user')

    def __str__(self):
        return self.name

    def get_path(self):
        if self.parent:
            return f"{self.parent.get_path()}/{self.name}"
        return self.name


class MediaTag(AuditMixin):
    name = models.CharField(max_length=100)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='media_tags')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('name', 'user')
        ordering = ['name']

    def __str__(self):
        return self.name


class MediaAsset(AuditMixin):
    objects = TenantManager()
    FILE_TYPE_CHOICES = [
        ('image', 'Image'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('document', 'Document'),
        ('other', 'Other'),
    ]

    STORAGE_CHOICES = [
        ('local', 'Local Storage'),
        ('s3', 'Amazon S3'),
        ('r2', 'Cloudflare R2'),
        ('minio', 'MinIO'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='media_assets_new')
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, null=True, blank=True, related_name='media_assets')
    folder = models.ForeignKey(MediaFolder, on_delete=models.SET_NULL, null=True, blank=True, related_name='assets')
    file = models.FileField(upload_to='media_assets/%Y/%m/%d/')
    thumbnail = models.FileField(upload_to='media_assets/thumbnails/', blank=True)
    file_type = models.CharField(max_length=20, choices=FILE_TYPE_CHOICES, blank=True)
    storage_backend = models.CharField(max_length=20, choices=STORAGE_CHOICES, default='local')
    storage_path = models.CharField(max_length=500, blank=True)

    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=100, blank=True)
    file_size = models.BigIntegerField(default=0)
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    duration = models.FloatField(null=True, blank=True)
    thumbnail_path = models.CharField(max_length=500, blank=True)

    title = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    alt_text = models.TextField(blank=True)
    tags = models.ManyToManyField(MediaTag, blank=True, related_name='assets')

    is_optimized = models.BooleanField(default=False)
    is_processing = models.BooleanField(default=False)
    auto_tags = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    usage_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.original_filename

    def save(self, *args, **kwargs):
        if not self.file_type:
            self.file_type = self._detect_file_type()
        if not self.original_filename and self.file.name:
            self.original_filename = os.path.basename(self.file.name)
        if not self.storage_path:
            self.storage_path = self.file.name if self.file else ''
        super().save(*args, **kwargs)

    def _detect_file_type(self):
        ext = os.path.splitext(self.original_filename or self.file.name or '')[1].lower()
        image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp', '.avif'}
        video_exts = {'.mp4', '.mov', '.avi', '.webm', '.mkv', '.wmv', '.flv'}
        audio_exts = {'.mp3', '.wav', '.ogg', '.aac', '.flac', '.wma'}
        document_exts = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.csv'}
        if ext in image_exts:
            return 'image'
        if ext in video_exts:
            return 'video'
        if ext in audio_exts:
            return 'audio'
        if ext in document_exts:
            return 'document'
        return 'other'
