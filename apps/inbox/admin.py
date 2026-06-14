from django.contrib import admin

from .models import EmailDraft, EmailInbox, EmailMessage, EmailThread


@admin.register(EmailInbox)
class EmailInboxAdmin(admin.ModelAdmin):
    list_display = ['email_address', 'provider', 'user', 'is_active', 'last_synced_at']
    list_filter = ['provider', 'is_active']
    search_fields = ['email_address', 'user__email']


@admin.register(EmailThread)
class EmailThreadAdmin(admin.ModelAdmin):
    list_display = ['subject', 'inbox', 'message_count', 'intent', 'urgency', 'is_flagged', 'last_message_at']
    list_filter = ['intent', 'urgency', 'is_flagged']
    search_fields = ['subject', 'snippet']


@admin.register(EmailMessage)
class EmailMessageAdmin(admin.ModelAdmin):
    list_display = ['subject', 'from_email', 'thread', 'received_at', 'is_incoming']
    list_filter = ['is_incoming']
    search_fields = ['subject', 'from_email', 'body_text']


@admin.register(EmailDraft)
class EmailDraftAdmin(admin.ModelAdmin):
    list_display = ['thread', 'status', 'created_at']
    list_filter = ['status']

