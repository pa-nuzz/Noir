from django.db import models
from django.conf import settings
from django.utils import timezone


class Notification(models.Model):
    """User notifications for various system events."""

    TYPE_CHOICES = [
        ('draft_created', 'AI Draft Created'),
        ('campaign_sent', 'Campaign Sent'),
        ('campaign_completed', 'Campaign Completed'),
        ('sync_completed', 'Sync Completed'),
        ('sync_failed', 'Sync Failed'),
        ('auto_reply_draft', 'Auto-Reply Draft Created'),
        ('campaign_failed', 'Campaign Failed'),
        ('sender_issue', 'Sender Issue'),
        ('dns_audit_completed', 'DNS Audit Completed'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    action_url = models.CharField(max_length=500, blank=True)
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_notifications'
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_notifications'
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'read']),
            models.Index(fields=['user', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.title} ({self.user.email})"
    
    def mark_read(self):
        self.read = True
        self.save(update_fields=['read'])
    
    @classmethod
    def create_notification(cls, user, type, title, message, action_url='', created_by=None):
        """Create a new notification for a user. If created_by is provided, it will be used as the creator."""
        return cls.objects.create(
            user=user,
            type=type,
            title=title,
            message=message,
            action_url=action_url,
            created_by=created_by or user,
            updated_by=created_by or user
        )
    
    @classmethod
    def get_unread_count(cls, user):
        return cls.objects.filter(user=user, read=False).count()