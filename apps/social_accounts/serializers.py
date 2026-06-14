from rest_framework import serializers

from .models import SocialAccount, SocialAnalytics, SocialPost


class SocialAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = SocialAccount
        fields = ['id', 'platform', 'account_name', 'account_id', 'avatar_url', 'profile_url', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class SocialPostSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source='account.account_name', read_only=True)
    platform_display = serializers.CharField(source='get_platform_display', read_only=True)

    class Meta:
        model = SocialPost
        fields = [
            'id', 'account', 'account_name', 'platform', 'platform_display',
            'content', 'media_urls', 'link_url', 'hashtags',
            'scheduled_at', 'published_at', 'status',
            'platform_post_id', 'platform_post_url', 'error_message',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'status', 'published_at', 'platform_post_id', 'platform_post_url', 'error_message', 'created_at', 'updated_at']


class SocialAnalyticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SocialAnalytics
        fields = '__all__'
        read_only_fields = ['id', 'fetched_at']
