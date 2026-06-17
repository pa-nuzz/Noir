from django.db import models
from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.utils import timezone
import html
import re

from apps.campaigns import constants as C
from core.models import AuditMixin
from core.tenant import TenantManager


def template_image_upload_to(instance, filename):
    return f'template_images/{instance.template.id}/{instance.cid_name}'

class Campaign(AuditMixin):
    objects = TenantManager()
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('sending', 'Sending'),
        ('sent', 'Sent'),
        ('paused', 'Paused'),
        ('failed', 'Failed'),
    ]
    RISK_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='campaigns')
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, null=True, blank=True, related_name='campaigns')
    sender = models.ForeignKey('senders.Sender', on_delete=models.SET_NULL, null=True, blank=True)
    template = models.ForeignKey('EmailTemplate', on_delete=models.SET_NULL, null=True, blank=True, related_name='campaigns', help_text="Template used as source for this campaign")
    name = models.CharField(max_length=255)
    subject = models.CharField(max_length=998)
    body_html = models.TextField(blank=True, default='')
    body_text = models.TextField(blank=True, default='')
    recipient_emails = models.TextField(blank=True, default='')
    from_name = models.CharField(max_length=255, blank=True)
    reply_to = models.EmailField(blank=True)
    recipient_context = models.JSONField(blank=True, default=dict, help_text="Per-recipient variable data (e.g., from CSV upload)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    scheduled_at = models.DateTimeField(blank=True, null=True)
    total_recipients = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    open_count = models.PositiveIntegerField(default=0)
    bounce_count = models.PositiveIntegerField(default=0)
    spam_score = models.FloatField(null=True, blank=True)
    spam_risk = models.CharField(max_length=10, choices=RISK_CHOICES, default='low')
    
    # A/B Testing Fields
    is_ab_test = models.BooleanField(default=False)
    ab_test_status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'), ('running', 'Running'), ('completed', 'Completed')],
        default='pending'
    )
    ab_test_duration_hours = models.PositiveIntegerField(default=2)
    winner_variant = models.ForeignKey('CampaignVariant', null=True, blank=True, on_delete=models.SET_NULL, related_name='won_campaigns')
    source_workflow = models.ForeignKey(
        'automations.Workflow', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='campaigns', help_text="If set, this campaign was created by an automation workflow",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False, help_text='Soft delete flag')
    deleted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['workspace', 'status', '-created_at']),
            models.Index(fields=['workspace', 'scheduled_at']),
            models.Index(fields=['user', 'status', '-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status', 'scheduled_at']),
            models.Index(fields=['sender', 'status']),
        ]

    def __str__(self):
        return self.name

    @property
    def open_rate(self):
        if self.sent_count == 0:
            return 0
        return round((self.open_count / self.sent_count) * 100, 1)

    @property
    def bounce_rate(self):
        if self.sent_count == 0:
            return 0
        return round((self.bounce_count / self.sent_count) * 100, 1)

    def _clean_email(self, raw):
        email = raw.strip().lower()
        if email.startswith('<') and email.endswith('>'):
            email = email[1:-1].strip()
        if email.startswith('mailto:'):
            email = email[7:].strip()
        if not email:
            return None
        try:
            validate_email(email)
        except ValidationError:
            return None
        return email

    def get_recipient_list(self):
        recipients = []
        for item in (self.recipient_emails or '').replace(';', ',').replace('\n', ',').split(','):
            email = self._clean_email(item)
            if not email:
                continue
            try:
                validate_email(email)
            except ValidationError:
                continue
            if email not in recipients:
                recipients.append(email)
        # Filter out globally unsubscribed emails
        if recipients:
            unsubscribed = set(
                EmailUnsubscribe.objects.filter(email__in=recipients)
                .values_list('email', flat=True)
            )
            recipients = [e for e in recipients if e not in unsubscribed]
        return recipients

    def render_preview_html(self):
        """Render the campaign as full HTML for preview."""
        from apps.campaigns.services.delivery import render_html
        from apps.campaigns import constants as C

        # Get the base HTML from the unified pipeline
        sample_data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john@example.com',
            'company_name': 'Acme Inc.',
            'month': timezone.now().strftime('%B %Y'),
            'year': str(timezone.now().year),
        }

        # Use the unified pipeline with preview context and CID resolution
        html_body, plain_text, _ = render_html(
            body_html=self.body_html if not self.template else self.template.body_html,
            template=self.template,
            recipient_email='preview@example.com',
            recipient_context=sample_data,
            include_tracking=False,
            base_url='',
            resolve_cids=True,
        )

        subject = (self.template.subject if self.template else self.subject) or 'Preview'
        subject_escaped = html.escape(subject)

        html_preview = (
            '<!DOCTYPE html>\n'
            '<html>\n'
            '<head>\n'
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            '<title>Preview: ' + subject_escaped + '</title>\n'
            '</head>\n'
            '<body style="margin:0;padding:0;background-color:' + C.EMAIL_BACKGROUND_COLOR + ';'
            'font-family:' + C.EMAIL_FONT_FAMILY + ';'
            'line-height:' + C.EMAIL_LINE_HEIGHT + ';color:' + C.EMAIL_TEXT_COLOR + '">\n'
            '<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" '
            'style="border-collapse:collapse;background-color:' + C.EMAIL_BACKGROUND_COLOR + '">\n'
            '<tr>\n'
            '<td align="center" style="padding:24px 16px">\n'
            '<table role="presentation" border="0" cellpadding="0" cellspacing="0" '
            'style="border-collapse:collapse;max-width:' + str(C.EMAIL_MAX_WIDTH) + 'px;width:100%">\n'
            '<tr>\n'
            '<td style="background-color:' + C.EMAIL_CONTAINER_BACKGROUND + ';border-radius:8px;overflow:hidden;'
            'box-shadow:0 1px 2px rgba(0,0,0,0.06)">\n'
            '<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" '
            'style="border-collapse:collapse">\n'
            '<tr>\n'
            '<td style="padding:20px 24px 16px;border-bottom:1px solid ' + C.EMAIL_BORDER_COLOR + '">\n'
            '<h1 style="font-size:' + C.EMAIL_FONT_SIZE_HEADER + ';font-weight:600;margin:0;color:' + C.EMAIL_TEXT_COLOR + ';'
            'font-family:' + C.EMAIL_FONT_FAMILY + ';'
            'line-height:1.4">'
            + subject_escaped + '</h1>\n'
            '</td>\n'
            '</tr>\n'
            '<tr>\n'
            '<td style="padding:20px 24px;font-size:' + C.EMAIL_FONT_SIZE_BODY + ';line-height:' + C.EMAIL_LINE_HEIGHT + ';color:' + C.EMAIL_TEXT_COLOR + ';'
            'font-family:' + C.EMAIL_FONT_FAMILY + '">\n'
            + html_body + '\n'
            '</td>\n'
            '</tr>\n'
            '<tr>\n'
            '<td style="padding:16px 24px;text-align:center;font-size:12px;color:' + C.EMAIL_TEXT_MUTED + ';'
            'border-top:1px solid ' + C.EMAIL_BORDER_COLOR + ';'
            'font-family:' + C.EMAIL_FONT_FAMILY + '">\n'
            '<p style="margin:0;line-height:1.5">This is a preview. Sent from Intelligent Digital Automation (IDA).</p>\n'
            '</td>\n'
            '</tr>\n'
            '</table>\n'
            '</td>\n'
            '</tr>\n'
            '</table>\n'
            '</td>\n'
            '</tr>\n'
            '</table>\n'
            '</body>\n'
            '</html>'
        )
        return html_preview


class CampaignAttachment(AuditMixin):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='campaign_attachments/%Y/%m/')
    original_filename = models.CharField(max_length=255, blank=True)
    mime_type = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at']

    def __str__(self):
        return self.original_filename or self.file.name


class CampaignVariant(AuditMixin):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='variants')
    label = models.CharField(max_length=1)  # 'A', 'B'
    subject = models.CharField(max_length=998)
    body_html = models.TextField(blank=True, default='')
    body_text = models.TextField(blank=True, default='')
    percentage = models.PositiveIntegerField(default=10)  # E.g., 10% of total list
    sent_count = models.PositiveIntegerField(default=0)
    open_count = models.PositiveIntegerField(default=0)
    bounce_count = models.PositiveIntegerField(default=0)
    spam_score = models.FloatField(null=True, blank=True)
    spam_risk = models.CharField(max_length=10, choices=Campaign.RISK_CHOICES, default='low')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('campaign', 'label')

    def __str__(self):
        return f"{self.campaign.name} - Variant {self.label}"

    @property
    def open_rate(self):
        if self.sent_count == 0:
            return 0
        return round((self.open_count / self.sent_count) * 100, 1)

    @property
    def bounce_rate(self):
        if self.sent_count == 0:
            return 0
        return round((self.bounce_count / self.sent_count) * 100, 1)


class EmailEngagement(AuditMixin):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='engagements')
    campaign_variant = models.ForeignKey(CampaignVariant, null=True, blank=True, on_delete=models.SET_NULL, related_name='engagements')
    recipient_email = models.EmailField()
    tracking_token = models.CharField(max_length=64, unique=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    open_count = models.PositiveIntegerField(default=0)
    click_count = models.PositiveIntegerField(default=0)
    last_event_at = models.DateTimeField(null=True, blank=True)


    class Meta:
        indexes = [
            models.Index(fields=['tracking_token']),
            models.Index(fields=['campaign', 'recipient_email']),
            models.Index(fields=['recipient_email']),  # For recipient lookups
            models.Index(fields=['sent_at']),
            models.Index(fields=['opened_at']),  # For open rate queries
            models.Index(fields=['clicked_at']),  # For click rate queries
        ]

    def __str__(self):
        return f"{self.recipient_email} - {self.campaign.name}"


class EmailClickEvent(AuditMixin):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='click_events')
    engagement = models.ForeignKey(EmailEngagement, on_delete=models.CASCADE, related_name='click_events')
    clicked_url = models.URLField(max_length=2048)
    clicked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['campaign', 'clicked_at']),
            models.Index(fields=['campaign', 'clicked_url']),
        ]

    def __str__(self):
        return f"{self.campaign.name} -> {self.clicked_url}"


class EmailUnsubscribe(AuditMixin):
    email = models.EmailField(db_index=True)
    campaign = models.ForeignKey(Campaign, on_delete=models.SET_NULL, null=True, blank=True, related_name='unsubscribes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['email', 'campaign']

    def __str__(self):
        return self.email


class EmailTemplate(AuditMixin):
    """Reusable email templates like Gmail templates."""
    objects = TenantManager()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='email_templates')
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, null=True, blank=True, related_name='email_templates')
    name = models.CharField(max_length=255, help_text="Template name (e.g., 'Welcome Email', 'Monthly Newsletter')")
    subject = models.CharField(max_length=998, blank=True, help_text="Email subject line")
    body_html = models.TextField(blank=True, help_text="HTML version of the email")
    body_text = models.TextField(blank=True, help_text="Plain text version")
    header_logo = models.ImageField(upload_to='template_headers/', blank=True, help_text="Logo/image for the email header")
    footer_logo = models.ImageField(upload_to='template_footers/', blank=True, help_text="Logo/image for the email footer")
    header_text = models.CharField(max_length=255, blank=True, help_text="Text displayed next to header logo")
    footer_text = models.TextField(blank=True, help_text="Text displayed in the email footer")
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False, help_text="System-defined default template that cannot be deleted")
    use_count = models.PositiveIntegerField(default=0, help_text="How many times this template was used")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ['user', 'name']

    def __str__(self):
        return self.name

    def clean(self):
        """Validate template name uniqueness (case-insensitive)."""
        from django.core.exceptions import ValidationError
        # Check for case-insensitive duplicate names
        if EmailTemplate.objects.filter(
            user=self.user,
            name__iexact=self.name
        ).exclude(id=self.id).exists():
            raise ValidationError({
                'name': 'A template with this name already exists (case-insensitive).'
            })

    def increment_use(self):
        self.use_count += 1
        self.save(update_fields=['use_count'])

    def get_embedded_images(self):
        """Return dict mapping cid_name -> image URL for all template images."""
        return {img.cid_name: img.image.url for img in self.images.all() if img.image}

    def get_all_cid_names(self):
        """Extract all cid: references from the HTML body."""
        if not self.body_html:
            return set()
        return set(re.findall(r'cid:([^"\'\\s>]+)', self.body_html))

    def render_complete_html(self, preview_context=None):
        from apps.campaigns.services.delivery import render_html
        from apps.campaigns import constants as C

        ctx = preview_context or {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john@example.com',
            'company_name': 'Acme Inc.',
            'client_name': 'Valued Customer',
            'voucher': 'your discount',
            'subject': 'Your Email',
        }

        html_out, _, _ = render_html(
            body_html=self.body_html,
            template=self,
            recipient_email=ctx.get('email', 'john@example.com'),
            recipient_context=ctx,
            include_tracking=False,
            resolve_cids=True,
        )

        return html_out


class TemplateImage(AuditMixin):
    """Embedded image referenced via cid: in template HTML (signature pics, icons, etc.)."""
    template = models.ForeignKey(EmailTemplate, on_delete=models.CASCADE, related_name='images')
    cid_name = models.CharField(max_length=255, help_text="Content-ID name (e.g. profile.jpg, logo.png)")
    image = models.ImageField(upload_to=template_image_upload_to, help_text="Image file to embed")
    label = models.CharField(max_length=255, blank=True, help_text="Human-readable label (e.g. Profile Picture)")

    class Meta:
        unique_together = ['template', 'cid_name']

    def __str__(self):
        return f'{self.cid_name} ({self.template.name})'