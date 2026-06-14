from django.contrib import admin
from apps.senders.models import Sender


@admin.register(Sender)
class SenderAdmin(admin.ModelAdmin):
    list_display = ['display_name', 'from_email', 'user', 'provider', 'smtp_host', 'daily_limit', 'emails_sent_today', 'is_active', 'is_verified', 'created_at']
    list_filter = ['provider', 'is_active', 'is_verified', 'use_tls', 'created_at']
    search_fields = ['display_name', 'from_email', 'user__email', 'smtp_host', 'username']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'last_reset_date', 'is_limit_reached']

    fieldsets = (
        ('Basic Info', {'fields': ('user', 'display_name', 'from_email', 'provider', 'is_active', 'is_verified')}),
        ('SMTP Configuration', {'fields': ('smtp_host', 'smtp_port', 'username', 'use_tls')}),
        ('Daily Limits', {'fields': ('daily_limit', 'emails_sent_today', 'last_reset_date', 'is_limit_reached')}),
        ('Security', {'fields': ('_password',), 'classes': ('collapse',)}),
        ('Timestamps', {'fields': ('created_at',)}),
    )