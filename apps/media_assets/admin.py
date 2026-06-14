from django.contrib import admin

from .models import MediaAsset, MediaFolder, MediaTag


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = ('original_filename', 'file_type', 'user', 'file_size', 'created_at')
    list_filter = ('file_type', 'storage_backend')
    search_fields = ('original_filename', 'title', 'description')


@admin.register(MediaFolder)
class MediaFolderAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent', 'user', 'created_at')


@admin.register(MediaTag)
class MediaTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'user')
