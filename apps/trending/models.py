from django.conf import settings
from django.db import models
from django.utils.text import slugify

from core.tenant import TenantManager


class Topic(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=10, blank=True, default='📰')
    color = models.CharField(max_length=7, blank=True, default='#06B6D4')
    keywords = models.JSONField(default=list, blank=True, help_text='Keywords used to auto-classify content')
    subscriber_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-subscriber_count', 'name']

    def __str__(self):
        return f"{self.icon} {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class ContentSource(models.Model):
    SOURCE_TYPES = [
        ('rss', 'RSS Feed'),
        ('api', 'API'),
        ('web', 'Web Scraper'),
    ]

    name = models.CharField(max_length=200)
    source_type = models.CharField(max_length=10, choices=SOURCE_TYPES)
    url = models.URLField(max_length=500)
    config_json = models.JSONField(default=dict, blank=True, help_text='Extra config like headers, params, selectors')
    poll_interval_hours = models.PositiveIntegerField(default=6)
    is_active = models.BooleanField(default=True)
    last_fetched = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"[{self.get_source_type_display()}] {self.name}"


class FeedItem(models.Model):
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, blank=True, related_name='feed_items')
    source = models.ForeignKey(ContentSource, on_delete=models.CASCADE, related_name='feed_items')
    title = models.CharField(max_length=500)
    url = models.URLField(max_length=1000, unique=True)
    author = models.CharField(max_length=255, blank=True)
    content_raw = models.TextField(blank=True)
    content_cleaned = models.TextField(blank=True)
    image_url = models.URLField(max_length=1000, blank=True)
    ai_summary = models.TextField(blank=True)
    ai_categories = models.JSONField(default=list, blank=True)
    trending_score = models.FloatField(default=0.0)
    published_at = models.DateTimeField(null=True, blank=True)
    fetched_at = models.DateTimeField(auto_now_add=True)
    is_duplicate = models.BooleanField(default=False)
    language = models.CharField(max_length=10, blank=True, default='en')

    class Meta:
        ordering = ['-trending_score', '-published_at']
        indexes = [
            models.Index(fields=['-trending_score']),
            models.Index(fields=['topic', '-published_at']),
            models.Index(fields=['is_duplicate']),
        ]

    def __str__(self):
        return self.title[:80]


class UserActivityProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trending_profile')
    inferred_keywords = models.JSONField(default=list, blank=True)
    inferred_topic_ids = models.JSONField(default=list, blank=True)
    last_analyzed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'User activity profiles'

    def __str__(self):
        return f"Profile for {self.user.email}"


class UserTopicPreference(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trending_topic_prefs')
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='user_preferences')
    is_auto_detected = models.BooleanField(default=False)
    subscribed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'topic')
        ordering = ['-subscribed_at']

    def __str__(self):
        return f"{self.user.email} → {self.topic.name}"


class UserFeedInteraction(models.Model):
    INTERACTION_TYPES = [
        ('saved', 'Saved as Draft'),
        ('bookmarked', 'Bookmarked'),
        ('dismissed', 'Dismissed'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trending_interactions')
    feed_item = models.ForeignKey(FeedItem, on_delete=models.CASCADE, related_name='user_interactions')
    interaction_type = models.CharField(max_length=20, choices=INTERACTION_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'feed_item', 'interaction_type')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} {self.interaction_type} → {self.feed_item.title[:50]}"


class CurrentItem(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('published', 'Published'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='currents')
    feed_item = models.ForeignKey(FeedItem, on_delete=models.CASCADE, related_name='currents')
    scheduled_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('user', 'feed_item')

    def __str__(self):
        return f"{self.user.email} → {self.feed_item.title[:60]}"
