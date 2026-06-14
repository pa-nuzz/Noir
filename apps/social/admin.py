from django.contrib import admin

from .models import SocialAccount, SocialPost, SocialMediaAnalytics


@admin.register(SocialAccount)
class SocialAccountAdmin(admin.ModelAdmin):
    list_display = ['account_name', 'platform', 'user', 'is_active', 'created_at']
    list_filter = ['platform', 'is_active']
    search_fields = ['account_name', 'user__email']


@admin.register(SocialPost)
class SocialPostAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'platform', 'account', 'status', 'scheduled_at', 'published_at']
    list_filter = ['platform', 'status']
    search_fields = ['content']


@admin.register(SocialMediaAnalytics)
class SocialMediaAnalyticsAdmin(admin.ModelAdmin):
    list_display = ['post', 'impressions', 'likes', 'shares', 'comments', 'fetched_at']
