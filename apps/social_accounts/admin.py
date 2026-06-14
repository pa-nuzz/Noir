from django.contrib import admin

from .models import SocialAccount, SocialAnalytics, SocialPost


@admin.register(SocialAccount)
class SocialAccountAdmin(admin.ModelAdmin):
    list_display = ('account_name', 'platform', 'user', 'is_active', 'created_at')
    list_filter = ('platform', 'is_active')
    search_fields = ('account_name', 'user__email')


@admin.register(SocialPost)
class SocialPostAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'user', 'platform', 'status', 'scheduled_at')
    list_filter = ('status', 'platform')


@admin.register(SocialAnalytics)
class SocialAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('post', 'impressions', 'likes', 'comments', 'fetched_at')
