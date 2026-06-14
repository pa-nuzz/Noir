from django.db import models
from django.conf import settings


class SocialAccount(models.Model):
    PLATFORM_CHOICES = [
        ('facebook', 'Facebook'),
        ('instagram', 'Instagram'),
        ('twitter', 'X (Twitter)'),
        ('linkedin', 'LinkedIn'),
        ('tiktok', 'TikTok'),
        ('youtube', 'YouTube'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='social_accounts')
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    account_name = models.CharField(max_length=255)
    account_id = models.CharField(max_length=255, blank=True)

    access_token = models.TextField(blank=True)
    refresh_token = models.TextField(blank=True)
    token_expires_at = models.DateTimeField(blank=True, null=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'platform', 'account_id')
        ordering = ['platform', 'account_name']

    def __str__(self):
        return f"{self.get_platform_display()} — {self.account_name}"


class SocialPost(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('publishing', 'Publishing'),
        ('published', 'Published'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='social_posts')
    account = models.ForeignKey(SocialAccount, on_delete=models.CASCADE, related_name='posts')
    platform = models.CharField(max_length=20, choices=SocialAccount.PLATFORM_CHOICES)

    content = models.TextField(blank=True, help_text='Post caption / body text')
    media_urls = models.JSONField(default=list, blank=True, help_text='List of media file URLs or paths')
    link_url = models.URLField(blank=True, help_text='Link to include in post')

    scheduled_at = models.DateTimeField(blank=True, null=True)
    published_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    platform_post_id = models.CharField(max_length=255, blank=True, help_text='ID returned by platform after publishing')
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-scheduled_at', '-created_at']

    def __str__(self):
        preview = (self.content or '')[:60]
        return f"[{self.get_platform_display()}] {preview}"


class SocialMediaAnalytics(models.Model):
    post = models.ForeignKey(SocialPost, on_delete=models.CASCADE, related_name='analytics')
    fetched_at = models.DateTimeField(auto_now_add=True)

    impressions = models.IntegerField(default=0)
    reach = models.IntegerField(default=0)
    likes = models.IntegerField(default=0)
    shares = models.IntegerField(default=0)
    comments = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    engagement_rate = models.FloatField(default=0.0)

    followers_gained = models.IntegerField(default=0)
    followers_lost = models.IntegerField(default=0)

    raw_data = models.JSONField(default=dict, blank=True, help_text='Raw API response for debugging')

    class Meta:
        verbose_name_plural = 'Social media analytics'
        ordering = ['-fetched_at']

    def __str__(self):
        return f"Analytics for {self.post} @ {self.fetched_at.date()}"
