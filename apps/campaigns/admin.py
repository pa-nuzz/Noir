from django.contrib import admin
from apps.campaigns.models import Campaign, CampaignVariant, EmailEngagement, EmailClickEvent, EmailTemplate


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'sender', 'status', 'total_recipients', 'sent_count', 'open_count', 'spam_risk', 'created_at']
    list_filter = ['status', 'spam_risk', 'created_at', 'sender']
    search_fields = ['name', 'subject', 'user__email', 'recipient_emails']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at', 'open_rate', 'bounce_rate']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Basic Info', {'fields': ('name', 'user', 'sender', 'status')}),
        ('Email Content', {'fields': ('subject', 'from_name', 'reply_to', 'body_text', 'body_html')}),
        ('Recipients', {'fields': ('recipient_emails', 'total_recipients')}),
        ('Performance', {'fields': ('sent_count', 'open_count', 'bounce_count', 'open_rate', 'bounce_rate')}),
        ('Spam Analysis', {'fields': ('spam_score', 'spam_risk')}),
        ('Scheduling', {'fields': ('scheduled_at',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )


@admin.register(EmailEngagement)
class EmailEngagementAdmin(admin.ModelAdmin):
    list_display = ['campaign', 'recipient_email', 'sent_at', 'opened_at', 'clicked_at', 'open_count', 'click_count']
    list_filter = ['sent_at', 'opened_at', 'clicked_at']
    search_fields = ['recipient_email', 'campaign__name', 'tracking_token']
    ordering = ['-sent_at']
    readonly_fields = ['sent_at', 'tracking_token']
    date_hierarchy = 'sent_at'


@admin.register(EmailClickEvent)
class EmailClickEventAdmin(admin.ModelAdmin):
    list_display = ['campaign', 'engagement', 'clicked_url', 'clicked_at']
    list_filter = ['clicked_at']
    search_fields = ['clicked_url', 'campaign__name', 'engagement__recipient_email']
    ordering = ['-clicked_at']
    readonly_fields = ['clicked_at']
    date_hierarchy = 'clicked_at'


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'subject', 'use_count', 'is_active', 'updated_at']
    list_filter = ['is_active', 'created_at', 'updated_at']
    search_fields = ['name', 'subject', 'user__email', 'body_html', 'body_text']
    ordering = ['-use_count', '-updated_at']
    readonly_fields = ['created_at', 'updated_at', 'use_count']


@admin.register(CampaignVariant)
class CampaignVariantAdmin(admin.ModelAdmin):
    list_display = ['campaign', 'label', 'percentage', 'sent_count', 'open_count', 'bounce_count', 'spam_risk', 'created_at']
    search_fields = ['campaign__name', 'subject']
    list_filter = ['spam_risk', 'created_at']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'
