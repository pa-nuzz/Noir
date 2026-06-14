from django.contrib import admin

from .models import ContentApproval, ContentItem, ContentVersion


@admin.register(ContentItem)
class ContentItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'content_type', 'user', 'status', 'created_at')
    list_filter = ('content_type', 'status')
    search_fields = ('title', 'body')


@admin.register(ContentVersion)
class ContentVersionAdmin(admin.ModelAdmin):
    list_display = ('content_item', 'version_number', 'created_by', 'created_at')


@admin.register(ContentApproval)
class ContentApprovalAdmin(admin.ModelAdmin):
    list_display = ('content_item', 'reviewer', 'decision', 'created_at')
