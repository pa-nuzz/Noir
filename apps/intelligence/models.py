"""Intelligence app models.

Auto-reply settings and other intelligence-related models.
"""

from django.conf import settings
from django.db import models


class AutoReplySettings(models.Model):
    """User-specific auto-reply settings."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='auto_reply_settings',
    )
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='auto_reply_settings',
    )
    enable_auto_reply = models.BooleanField(
        default=False,
        help_text='Enable automatic reply generation for incoming emails'
    )
    confidence_threshold = models.IntegerField(
        default=80,
        help_text='Minimum confidence score (0-100) to consider auto-replying'
    )
    spam_risk_threshold = models.CharField(
        max_length=10,
        default='Medium',
        choices=[
            ('Very Low', 'Very Low'),
            ('Low', 'Low'),
            ('Medium', 'Medium'),
            ('High', 'High'),
        ],
        help_text='Maximum spam risk level allowed for auto-reply (higher = more permissive)'
    )
    # Tone preference for auto-replies
    default_tone = models.CharField(
        max_length=20,
        default='professional',
        choices=[
            ('professional', 'Professional'),
            ('friendly', 'Friendly'),
            ('formal', 'Formal'),
            ('casual', 'Casual'),
        ],
        help_text='Default tone for generated auto-replies'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Auto-reply settings for {self.user.email}'

    class Meta:
        verbose_name = 'Auto Reply Settings'
        verbose_name_plural = 'Auto Reply Settings'


class Rule(models.Model):
    """Auto-reply rule that defines when a reply should be triggered."""
    INTENT_CHOICES = [
        ('question', 'Question'),
        ('complaint', 'Complaint'),
        ('support', 'Support Request'),
        ('sales', 'Sales Inquiry'),
        ('meeting_request', 'Meeting Request'),
        ('information', 'Information Request'),
        ('introduction', 'Introduction'),
        ('feedback', 'Feedback'),
        ('other', 'Other'),
    ]
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='auto_reply_rules',
    )
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='auto_reply_rules',
    )
    name = models.CharField(max_length=100, help_text='Human-readable rule name')
    intent = models.CharField(
        max_length=30, choices=INTENT_CHOICES,
        help_text='Email intent to match',
    )
    min_confidence = models.IntegerField(
        default=80,
        help_text='Minimum confidence score (0-100) for this rule to fire',
    )
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(
        default=0,
        help_text='Higher priority rules are evaluated first',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority', 'name']
        verbose_name = 'Auto Reply Rule'
        verbose_name_plural = 'Auto Reply Rules'

    def __str__(self):
        return f'{self.name} (intent={self.intent}, confidence≥{self.min_confidence})'


class Action(models.Model):
    """Action to take when a Rule matches."""
    ACTION_CHOICES = [
        ('draft_reply', 'Generate Draft Reply'),
        ('flag_review', 'Flag for Human Review'),
        ('archive', 'Archive'),
        ('label', 'Apply Label'),
        ('ignore', 'Ignore (No Action)'),
    ]
    rule = models.ForeignKey(
        Rule, on_delete=models.CASCADE, related_name='actions',
    )
    action_type = models.CharField(
        max_length=20, choices=ACTION_CHOICES,
        help_text='Action to take when the parent rule matches',
    )
    label = models.CharField(
        max_length=50, blank=True,
        help_text='Label to apply (only for "Apply Label" action)',
    )
    tone_override = models.CharField(
        max_length=20, blank=True,
        choices=[
            ('professional', 'Professional'),
            ('friendly', 'Friendly'),
            ('formal', 'Formal'),
            ('casual', 'Casual'),
            ('urgent', 'Urgent'),
        ],
        help_text='Override default tone for draft_reply actions',
    )

    class Meta:
        ordering = ['id']
        verbose_name = 'Auto Reply Action'
        verbose_name_plural = 'Auto Reply Actions'

    def __str__(self):
        return f'{self.get_action_type_display()} (rule: {self.rule.name})'


class ActivityLog(models.Model):
    """Audit trail of auto-reply actions taken."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='auto_reply_activity_logs',
    )
    workspace = models.ForeignKey(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='auto_reply_activity_logs',
    )
    message = models.ForeignKey(
        'inbox.EmailMessage', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='auto_reply_logs',
    )
    rule = models.ForeignKey(
        Rule, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='activity_logs',
    )
    action_taken = models.CharField(max_length=30)
    confidence = models.IntegerField(null=True, blank=True)
    intent = models.CharField(max_length=30, blank=True)
    draft = models.ForeignKey(
        'inbox.EmailDraft', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='activity_logs',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Auto Reply Activity Log'
        verbose_name_plural = 'Auto Reply Activity Logs'

    def __str__(self):
        return f'{self.action_taken} at {self.created_at:%Y-%m-%d %H:%M}'