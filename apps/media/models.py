import os

from django.conf import settings
from django.db import models


def asset_upload_path(instance, filename):
    folder = instance.folder.name_slug if instance.folder else 'root'
    return os.path.join('media_assets', str(instance.user.id), folder, filename)


class MediaFolder(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='media_folders')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True, related_name='children')
    name = models.CharField(max_length=255)
    name_slug = models.SlugField(max_length=255)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'parent', 'name')
        ordering = ['name']

    def __str__(self):
        if self.parent:
            return f"{self.parent.name}/{self.name}"
        return self.name


class MediaAsset(models.Model):
    FILE_TYPE_CHOICES = [
        ('image', 'Image'),
        ('video', 'Video'),
        ('document', 'Document'),
        ('audio', 'Audio'),
        ('other', 'Other'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='media_assets')
    folder = models.ForeignKey(MediaFolder, on_delete=models.SET_NULL, blank=True, null=True, related_name='assets')

    file = models.FileField(upload_to=asset_upload_path)
    thumbnail = models.ImageField(upload_to='media_assets/thumbnails/', blank=True, null=True)
    filename = models.CharField(max_length=500)
    file_type = models.CharField(max_length=20, choices=FILE_TYPE_CHOICES, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    file_size = models.BigIntegerField(default=0)
    width = models.IntegerField(blank=True, null=True)
    height = models.IntegerField(blank=True, null=True)

    ai_tags = models.JSONField(default=list, blank=True, help_text='AI-generated tags')
    ai_description = models.TextField(blank=True, help_text='AI-generated image description')
    alt_text = models.CharField(max_length=500, blank=True, help_text='Manual alt text for accessibility')

    is_optimized = models.BooleanField(default=False, help_text='Has been processed (resized/compressed/WebP)')
    storage_url = models.URLField(blank=True, help_text='CDN/cloud storage URL after upload')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.filename

    @property
    def extension(self):
        _, ext = os.path.splitext(self.filename)
        return ext.lower()

    @property
    def size_display(self):
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        else:
            return f"{self.file_size / (1024 * 1024):.1f} MB"
