import base64
import hashlib
import logging

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models

from core.tenant import TenantManager

logger = logging.getLogger(__name__)


class EmailInbox(models.Model):
    objects = TenantManager()
    PROVIDER_CHOICES = [
        ('gmail', 'Gmail'),
        ('outlook', 'Outlook'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='email_inboxes')
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, null=True, blank=True, related_name='email_inboxes')
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    email_address = models.EmailField()
    provider_account_id = models.CharField(max_length=255, blank=True, help_text='User ID from provider')

    access_token = models.TextField(blank=True)
    refresh_token = models.TextField(blank=True, help_text='Encrypted via set_token() — never read/write directly')
    token_expires_at = models.DateTimeField(blank=True, null=True)

    is_active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(blank=True, null=True)
    last_sync_status = models.CharField(max_length=50, blank=True, default='pending', help_text='pending, success, error')
    last_sync_error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'email_address')
        ordering = ['email_address']
        indexes = [
            models.Index(fields=['is_active', 'last_sync_status']),
        ]

    def get_fernet(self):
        from apps.common.crypto import normalize_key
        key = normalize_key(getattr(settings, 'FERNET_KEY', ''))
        if not key:
            raise ValueError("FERNET_KEY is not set or invalid in settings")
        return Fernet(key)

    def _candidate_fernets(self, include_expired=False):
        from apps.common.crypto import candidate_fernets as _cf
        return _cf(include_expired=include_expired)

    def _dev_fallback_key(self):
        from apps.common.crypto import dev_fallback_key
        return dev_fallback_key()

    def set_token(self, raw_token):
        try:
            f = self.get_fernet()
        except ValueError:
            if getattr(settings, 'DEBUG', False):
                dev_key = self._dev_fallback_key()
                if dev_key:
                    f = Fernet(dev_key)
                else:
                    raise
            else:
                raise
        try:
            encrypted = f.encrypt(raw_token.encode())
            self.access_token = base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            logger.error(f"Token encryption error for {self.email_address}: {e}")
            raise

    def get_token(self):
        if not self.access_token:
            return None
        ciphertext = self.access_token.strip().encode()
        for fernet in self._candidate_fernets(include_expired=True):
            try:
                encrypted = base64.urlsafe_b64decode(ciphertext)
                decrypted = fernet.decrypt(encrypted).decode()
                try:
                    primary_fernet = self.get_fernet()
                    refreshed = base64.urlsafe_b64encode(primary_fernet.encrypt(decrypted.encode())).decode()
                    if refreshed != self.access_token:
                        self.access_token = refreshed
                        self.save(update_fields=['access_token'])
                except Exception:
                    logger.debug("Primary Fernet unavailable; returning decrypted token without refresh")
                return decrypted
            except Exception:
                continue
        logger.error("Token decryption error for inbox '%s'", self.email_address)
        return None

    def set_refresh_token(self, raw_token):
        if not raw_token:
            self.refresh_token = ''
            return
        try:
            f = self.get_fernet()
        except ValueError:
            if getattr(settings, 'DEBUG', False):
                dev_key = self._dev_fallback_key()
                f = Fernet(dev_key) if dev_key else None
            else:
                raise
        if f is None:
            raise ValueError("No encryption key available to encrypt refresh_token")
        self.refresh_token = base64.urlsafe_b64encode(f.encrypt(raw_token.encode())).decode()

    def get_refresh_token(self):
        if not self.refresh_token:
            return None
        ciphertext = self.refresh_token.strip().encode()
        for fernet in self._candidate_fernets(include_expired=True):
            try:
                encrypted = base64.urlsafe_b64decode(ciphertext)
                return fernet.decrypt(encrypted).decode()
            except Exception:
                continue
        logger.error("Refresh token decryption error for inbox '%s'", self.email_address)
        return None

    def __str__(self):
        return f"{self.email_address} ({self.get_provider_display()})"


class EmailThread(models.Model):
    inbox = models.ForeignKey(EmailInbox, on_delete=models.CASCADE, related_name='threads')
    thread_id = models.CharField(max_length=255, help_text='Provider thread/conversation ID')
    subject = models.CharField(max_length=998, blank=True)
    snippet = models.TextField(blank=True, help_text='Latest message preview')

    participants = models.JSONField(default=list, blank=True, help_text='List of email addresses in thread')
    message_count = models.IntegerField(default=0)

    ai_summary = models.TextField(blank=True, help_text='AI-generated thread summary')
    intent = models.CharField(max_length=50, blank=True, help_text='Detected intent: question, complaint, support, sales, etc.')
    urgency = models.CharField(max_length=20, blank=True, help_text='Detected urgency: low, medium, high, urgent')
    is_flagged = models.BooleanField(default=False, help_text='Flagged for priority attention')

    last_message_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('inbox', 'thread_id')
        ordering = ['-last_message_at', '-updated_at']

    def __str__(self):
        return self.subject or self.thread_id


class EmailMessage(models.Model):
    thread = models.ForeignKey(EmailThread, on_delete=models.CASCADE, related_name='messages')
    message_id = models.CharField(max_length=255, help_text='Provider message ID')

    from_email = models.EmailField()
    from_name = models.CharField(max_length=255, blank=True)
    to_emails = models.JSONField(default=list, blank=True)
    cc_emails = models.JSONField(default=list, blank=True)
    bcc_emails = models.JSONField(default=list, blank=True)

    subject = models.CharField(max_length=998, blank=True)
    body_text = models.TextField(blank=True)
    body_html = models.TextField(blank=True)

    received_at = models.DateTimeField()
    is_incoming = models.BooleanField(default=True, help_text='True if received, False if sent')
    is_read = models.BooleanField(default=False, help_text='Whether the message has been opened')
    is_deleted = models.BooleanField(default=False, help_text='Soft delete flag')
    deleted_at = models.DateTimeField(blank=True, null=True)

    ai_summary = models.TextField(blank=True, help_text='AI summary of this individual message')
    intent = models.CharField(max_length=50, blank=True)
    urgency = models.CharField(max_length=20, blank=True)

    class Meta:
        unique_together = ('thread', 'message_id')
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['thread', 'received_at']),
            models.Index(fields=['is_incoming', 'received_at']),
        ]

    def __str__(self):
        return f"[{self.received_at.date()}] {self.from_email}: {self.subject[:60]}"


class EmailDraft(models.Model):
    STATUS_CHOICES = [
        ('pending_review', 'Pending Review'),
        ('edited', 'Edited'),
        ('approved', 'Approved'),
        ('sent', 'Sent'),
    ]

    thread = models.ForeignKey(EmailThread, on_delete=models.CASCADE, related_name='drafts')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='email_drafts')
    original_message = models.ForeignKey(EmailMessage, on_delete=models.SET_NULL, blank=True, null=True, related_name='drafts')

    ai_generated_body = models.TextField(help_text='Original AI-generated reply')
    edited_body = models.TextField(blank=True, help_text='Human-edited version')
    final_body = models.TextField(blank=True, help_text='The version that was approved/sent')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending_review')
    feedback = models.TextField(blank=True, help_text='Human feedback on the draft')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['original_message']),
        ]

    def __str__(self):
        return f"Draft for {self.thread.subject[:40]} — {self.status}"



