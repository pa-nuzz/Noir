from django.contrib import admin

from .models import MediaAsset, MediaFolder


@admin.register(MediaFolder)
class MediaFolderAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'parent', 'created_at']
    list_filter = ['user']
    search_fields = ['name']


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = ['filename', 'file_type', 'file_size', 'folder', 'user', 'is_optimized', 'created_at']
    list_filter = ['file_type', 'is_optimized']
    search_fields = ['filename', 'ai_tags', 'ai_description', 'alt_text']
