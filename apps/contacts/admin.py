from django.contrib import admin
from .models import Contact, ContactCustomField, ContactCustomFieldValue, ContactList, ContactSegment, ContactTag


@admin.register(ContactList)
class ContactListAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'contact_count', 'created_at', 'updated_at']
    list_filter = ['created_at', 'user']
    search_fields = ['name', 'user__email', 'description']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']

    def contact_count(self, obj):
        return obj.contacts.count()
    contact_count.short_description = 'Contacts'


@admin.register(ContactTag)
class ContactTagAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'contact_count', 'created_at']
    list_filter = ['created_at', 'user']
    search_fields = ['name', 'user__email']
    ordering = ['name']

    def contact_count(self, obj):
        return obj.contacts.count()
    contact_count.short_description = 'Contacts'


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ['email', 'first_name', 'last_name', 'contact_list', 'is_active', 'unsubscribed', 'bounce_count', 'is_suppressed', 'gdpr_consent']
    list_filter = ['is_active', 'unsubscribed', 'is_suppressed', 'gdpr_consent', 'created_at']
    search_fields = ['email', 'first_name', 'last_name', 'contact_list__name']
    ordering = ['-created_at']
    filter_horizontal = ['tags']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(ContactCustomField)
class ContactCustomFieldAdmin(admin.ModelAdmin):
    list_display = ['name', 'field_type', 'user', 'is_required']
    list_filter = ['field_type']


@admin.register(ContactCustomFieldValue)
class ContactCustomFieldValueAdmin(admin.ModelAdmin):
    list_display = ['contact', 'field', 'value']


@admin.register(ContactSegment)
class ContactSegmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'match_type', 'is_active', 'created_at']
    list_filter = ['match_type', 'is_active']
