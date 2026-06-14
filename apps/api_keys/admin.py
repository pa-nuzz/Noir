from django.contrib import admin

from .models import WorkspaceAPIKey


@admin.register(WorkspaceAPIKey)
class WorkspaceAPIKeyAdmin(admin.ModelAdmin):
    list_display = ['name', 'workspace', 'prefix', 'is_active', 'expires_at', 'last_used_at']
    list_filter = ['is_active', 'workspace']
    search_fields = ['name', 'prefix']
    readonly_fields = ['prefix', 'key_hash', 'last_used_at', 'last_used_ip']
