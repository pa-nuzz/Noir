from django.contrib import admin

from .models import EditLock


@admin.register(EditLock)
class EditLockAdmin(admin.ModelAdmin):
    list_display = ['content_type', 'object_id', 'locked_by', 'locked_at', 'expires_at']
    list_filter = ['content_type', 'locked_at']
    search_fields = ['locked_by__email']
