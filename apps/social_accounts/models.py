from django.conf import settings
from django.db import models

from core.models import AuditMixin
from core.tenant import TenantManager


class SocialAccount(AuditMixin):
    PLATFORM_CHOICES = [
        ('facebook', 'Facebook'),
        ('instagram', 'Instagram'),
        ('twitter', 'X (Twitter)'),
        ('linkedin', 'LinkedIn'),
        ('tiktok', 'TikTok'),
        ('youtube', 'YouTube'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='social_accounts_new')
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    account_name = models.CharField(max_length=255)
    account_id = models.CharField(max_length=255, blank=True)
    avatar_url = models.URLField(blank=True)
    profile_url = models.URLField(blank=True)

    access_token = models.TextField(blank=True)
    refresh_token = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(blank=True, null=True)

    app_key = models.CharField(max_length=255, blank=True, help_text='TikTok Developer App Key (Client ID)')
    app_secret = models.CharField(max_length=255, blank=True, help_text='TikTok Developer App Secret (Client Secret)')

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'platform', 'account_id')
        ordering = ['platform', 'account_name']

    def __str__(self):
        return f"{self.get_platform_display()} — {self.account_name}"


class SocialPost(AuditMixin):
    objects = TenantManager()
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('publishing', 'Publishing'),
        ('published', 'Published'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='social_posts_new')
    account = models.ForeignKey(SocialAccount, on_delete=models.CASCADE, related_name='posts')
    platform = models.CharField(max_length=20, choices=SocialAccount.PLATFORM_CHOICES)

    content = models.TextField(blank=True)
    media_urls = models.JSONField(default=list, blank=True)
    link_url = models.URLField(blank=True)
    hashtags = models.JSONField(default=list, blank=True)

    scheduled_at = models.DateTimeField(blank=True, null=True)
    published_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    platform_post_id = models.CharField(max_length=255, blank=True)
    platform_post_url = models.URLField(blank=True)
    error_message = models.TextField(blank=True)

    content_item = models.ForeignKey(
        'content_studio.ContentItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='social_posts',
        help_text='The Content Studio item this post was created from',
    )

    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, null=True, blank=True, related_name='social_posts')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-scheduled_at', '-created_at']
        indexes = [
            models.Index(fields=['account', 'status', 'scheduled_at']),
            models.Index(fields=['workspace', 'status']),
        ]

    def latest_analytics(self):
        return self.analytics.order_by('-fetched_at').first()

    def __str__(self):
        preview = (self.content or '')[:60]
        return f"[{self.get_platform_display()}] {preview}"


class SocialAnalytics(AuditMixin):
    post = models.ForeignKey(SocialPost, on_delete=models.CASCADE, related_name='analytics')
    fetched_at = models.DateTimeField(auto_now_add=True)

    impressions = models.IntegerField(default=0)
    reach = models.IntegerField(default=0)
    likes = models.IntegerField(default=0)
    shares = models.IntegerField(default=0)
    comments = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    saves = models.IntegerField(default=0)
    engagement_rate = models.FloatField(default=0.0)

    followers_gained = models.IntegerField(default=0)
    followers_lost = models.IntegerField(default=0)

    raw_data = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name_plural = 'Social analytics'
        ordering = ['-fetched_at']

    def __str__(self):
        return f"Analytics for {self.post} @ {self.fetched_at.date()}"
