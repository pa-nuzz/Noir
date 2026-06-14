from django.contrib import admin

from .models import WebhookEndpoint, WebhookDelivery


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    list_display = ['name', 'workspace', 'url', 'is_active', 'last_triggered_at']
    list_filter = ['is_active', 'workspace']
    search_fields = ['name', 'url']


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ['event_type', 'endpoint', 'status', 'attempt_count', 'response_code', 'created_at']
    list_filter = ['status', 'event_type']
