from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import User
from apps.campaigns.models import Campaign, EmailTemplate
from apps.senders.models import Sender
from apps.inbox.models import EmailInbox
from apps.contacts.models import ContactList, ContactTag, ContactCustomField, ContactSegment, Contact
from apps.social_accounts.models import SocialPost
from apps.content_studio.models import ContentItem
from apps.media_assets.models import MediaFolder, MediaAsset
from apps.automations.models import Workflow
from apps.workspaces.models import WorkspaceMembership, WorkspaceQuota


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'username', 'first_name', 'last_name', 'company', 'avatar', 'email_verified', 'date_joined']
        read_only_fields = ['id', 'email_verified', 'date_joined']


class SenderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sender
        fields = ['id', 'display_name', 'from_email', 'provider', 'smtp_host', 'smtp_port',
                  'daily_limit', 'send_delay_seconds', 'is_active', 'is_verified', 'created_at']
        read_only_fields = ['id', 'is_verified', 'created_at', 'emails_sent_today', 'last_reset_date']


class CampaignSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(source='sender.display_name', read_only=True)

    class Meta:
        model = Campaign
        fields = ['id', 'name', 'subject', 'sender', 'sender_name', 'template',
                  'body_html', 'body_text', 'recipient_emails', 'status',
                  'scheduled_at', 'total_recipients', 'sent_count', 'open_count', 'bounce_count',
                  'spam_score', 'spam_risk', 'created_at', 'updated_at']
        read_only_fields = ['id', 'status', 'sent_count', 'open_count', 'bounce_count',
                            'spam_score', 'spam_risk', 'created_at', 'updated_at']


class EmailTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailTemplate
        fields = ['id', 'name', 'subject', 'body_html', 'body_text', 'is_active', 'is_default', 'created_at']
        read_only_fields = ['id', 'is_default', 'created_at']


class EmailInboxSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailInbox
        fields = ['id', 'provider', 'email_address', 'is_active', 'last_synced_at', 'last_sync_status', 'created_at']
        read_only_fields = ['id', 'last_synced_at', 'last_sync_status', 'created_at']
        extra_kwargs = {'access_token': {'write_only': True}, 'refresh_token': {'write_only': True}}


class ContactListSerializer(serializers.ModelSerializer):
    contact_count = serializers.SerializerMethodField()

    class Meta:
        model = ContactList
        fields = ['id', 'name', 'description', 'contact_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    @extend_schema_field(int)
    def get_contact_count(self, obj):
        return obj.contacts.count()


class ContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = ['id', 'contact_list', 'email', 'first_name', 'last_name',
                  'is_active', 'unsubscribed', 'bounce_count', 'is_suppressed', 'created_at']
        read_only_fields = ['id', 'bounce_count', 'is_suppressed', 'created_at']

    def validate_contact_list(self, value):
        from core.tenant import get_current_tenant
        tenant = get_current_tenant()
        if tenant is not None and value.workspace_id != tenant.id:
            raise serializers.ValidationError('Contact list does not belong to this workspace.')
        return value


class ContactTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactTag
        fields = ['id', 'name', 'created_at']
        read_only_fields = ['id', 'created_at']


class ContactCustomFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactCustomField
        fields = ['id', 'name', 'field_type', 'options', 'is_required', 'created_at']
        read_only_fields = ['id', 'created_at']


class ContactSegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactSegment
        fields = ['id', 'name', 'description', 'match_type', 'rules', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class SocialPostSerializer(serializers.ModelSerializer):
    platform_display = serializers.CharField(source='get_platform_display', read_only=True)

    class Meta:
        model = SocialPost
        fields = ['id', 'account', 'platform', 'platform_display', 'content', 'media_urls',
                  'link_url', 'hashtags', 'scheduled_at', 'published_at', 'status',
                  'platform_post_id', 'platform_post_url', 'error_message', 'created_at', 'updated_at']
        read_only_fields = ['id', 'status', 'published_at', 'platform_post_id', 'platform_post_url', 'created_at', 'updated_at']


class ContentItemSerializer(serializers.ModelSerializer):
    content_type_display = serializers.CharField(source='get_content_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = ContentItem
        fields = ['id', 'title', 'content_type', 'content_type_display', 'body',
                  'platform', 'status', 'status_display', 'tags', 'metadata',
                  'is_auto_generated', 'source_prompt', 'created_at', 'updated_at']
        read_only_fields = ['id', 'status', 'is_auto_generated', 'created_at', 'updated_at']


class MediaFolderSerializer(serializers.ModelSerializer):
    class Meta:
        model = MediaFolder
        fields = ['id', 'name', 'parent', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class MediaAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = MediaAsset
        fields = ['id', 'folder', 'file', 'file_type', 'original_filename', 'mime_type',
                  'file_size', 'width', 'height', 'title', 'description',
                  'is_optimized', 'created_at']
        read_only_fields = ['id', 'file_size', 'is_optimized', 'created_at']


class WorkflowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workflow
        fields = ['id', 'name', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class WorkspaceMembershipSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)

    class Meta:
        model = WorkspaceMembership
        fields = ['id', 'user', 'user_email', 'user_name', 'role', 'created_at']
        read_only_fields = ['id', 'created_at']


class WorkspaceQuotaSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkspaceQuota
        fields = ['emails_sent_this_month', 'ai_credits_used', 'storage_bytes_used',
                  'month_reset_at', 'updated_at']
        read_only_fields = ['month_reset_at', 'updated_at']
