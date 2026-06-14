from django.contrib import admin

from .models import ContentSource, FeedItem, Topic, UserActivityProfile, UserFeedInteraction, UserTopicPreference


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'subscriber_count', 'is_active')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(ContentSource)
class ContentSourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'source_type', 'url', 'poll_interval_hours', 'is_active', 'last_fetched')
    list_filter = ('source_type', 'is_active')


@admin.register(FeedItem)
class FeedItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'topic', 'source', 'trending_score', 'published_at', 'fetched_at', 'is_duplicate')
    list_filter = ('topic', 'source', 'is_duplicate')
    search_fields = ('title', 'content_cleaned')
    readonly_fields = ('fetched_at',)


@admin.register(UserTopicPreference)
class UserTopicPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'topic', 'is_auto_detected', 'subscribed_at')
    list_filter = ('is_auto_detected', 'topic')


@admin.register(UserFeedInteraction)
class UserFeedInteractionAdmin(admin.ModelAdmin):
    list_display = ('user', 'feed_item', 'interaction_type', 'created_at')
    list_filter = ('interaction_type',)


@admin.register(UserActivityProfile)
class UserActivityProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'last_analyzed_at')
