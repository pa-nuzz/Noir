import hashlib
import hmac
import json
import requests as http_requests
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import AuditMixin


WEBHOOK_EVENTS = [
    ('campaign.sent', 'Campaign Sent'),
    ('campaign.opened', 'Campaign Opened'),
    ('campaign.clicked', 'Campaign Clicked'),
    ('campaign.bounced', 'Campaign Bounced'),
    ('contact.created', 'Contact Created'),
    ('contact.updated', 'Contact Updated'),
    ('contact.unsubscribed', 'Contact Unsubscribed'),
    ('social_post.published', 'Social Post Published'),
    ('social_post.failed', 'Social Post Failed'),
    ('inbox.synced', 'Inbox Synced'),
    ('workflow.triggered', 'Workflow Triggered'),
    ('workflow.completed', 'Workflow Completed'),
]


class WebhookEndpoint(AuditMixin):
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='webhook_endpoints')
    name = models.CharField(max_length=255, help_text='Label to identify this endpoint')
    url = models.URLField(help_text='HTTPS endpoint that will receive POST requests')
    events = models.JSONField(default=list, blank=True, help_text='List of event types to subscribe to')
    secret = models.CharField(max_length=128, blank=True, help_text='Optional secret for HMAC signing')
    is_active = models.BooleanField(default=True)
    last_triggered_at = models.DateTimeField(null=True, blank=True)
    last_response_code = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.url})'

    def save(self, *args, **kwargs):
        if not self.secret:
            import secrets
            self.secret = secrets.token_hex(32)
        super().save(*args, **kwargs)

    def sign_payload(self, payload):
        if not self.secret:
            return ''
        raw = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        return hmac.new(self.secret.encode('utf-8'), raw, hashlib.sha256).hexdigest()

    def deliver(self, event_type, payload):
        from .tasks import deliver_webhook
        deliver_webhook.delay(self.id, event_type, payload, workspace_id=self.workspace_id)


class WebhookDelivery(AuditMixin):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
        ('retrying', 'Retrying'),
    ]

    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name='deliveries')
    event_type = models.CharField(max_length=50)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    response_code = models.PositiveIntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Webhook deliveries'

    def __str__(self):
        return f'{self.event_type} → {self.endpoint.url} ({self.status})'

    def retry_delay(self):
        return min(60 * (2 ** (self.attempt_count - 1)), 3600)

    def should_retry(self):
        return self.status in ('failed', 'retrying') and self.attempt_count < self.max_attempts

    def execute(self):
        import requests
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'MailFlow-Webhook/1.0',
        }
        if self.endpoint.secret:
            headers['X-Webhook-Signature'] = self.endpoint.sign_payload(self.payload)

        try:
            resp = requests.post(
                self.endpoint.url,
                json=self.payload,
                headers=headers,
                timeout=30,
            )
            self.response_code = resp.status_code
            self.response_body = resp.text[:2000]
            self.attempt_count += 1

            if 200 <= resp.status_code < 300:
                self.status = 'delivered'
                self.delivered_at = timezone.now()
                self.endpoint.last_triggered_at = timezone.now()
                self.endpoint.last_response_code = resp.status_code
                self.endpoint.save(update_fields=['last_triggered_at', 'last_response_code'])
            else:
                if self.should_retry():
                    self.status = 'retrying'
                    self.next_retry_at = timezone.now() + timedelta(seconds=self.retry_delay())
                else:
                    self.status = 'failed'
        except requests.RequestException as e:
            self.response_code = None
            self.response_body = str(e)[:2000]
            self.attempt_count += 1
            if self.should_retry():
                self.status = 'retrying'
                self.next_retry_at = timezone.now() + timedelta(seconds=self.retry_delay())
            else:
                self.status = 'failed'

        self.save(update_fields=[
            'status', 'response_code', 'response_body', 'attempt_count',
            'next_retry_at', 'delivered_at',
        ])
        return self.status
