from django.db import models
from django.conf import settings
from cryptography.fernet import Fernet
import base64
import hashlib
import logging

from core.tenant import TenantManager

logger = logging.getLogger(__name__)


class Sender(models.Model):
    objects = TenantManager()
    PROVIDER_CHOICES = [
        ('gmail', 'Gmail / Google Workspace'),
        ('outlook', 'Outlook / Office 365'),
        ('custom', 'Custom SMTP'),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='senders')
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, null=True, blank=True, related_name='senders')
    display_name = models.CharField(max_length=255)
    from_email = models.EmailField()
    reply_to = models.EmailField(blank=True, help_text="Optional reply-to address")
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default='gmail')
    smtp_host = models.CharField(max_length=255)
    smtp_port = models.PositiveIntegerField(default=587)
    username = models.CharField(max_length=255)
    _password = models.TextField(db_column='password')  # encrypted
    use_tls = models.BooleanField(default=True)
    daily_limit = models.PositiveIntegerField(default=500)
    send_delay_seconds = models.FloatField(default=3.0, help_text="Seconds to wait between each email send (rate limiting)")
    emails_sent_today = models.PositiveIntegerField(default=0)
    last_reset_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=False, help_text='Manually toggled on/off by user')
    is_verified = models.BooleanField(default=False, help_text='Set to True only after successful SMTP connection test')
    last_verified_at = models.DateTimeField(null=True, blank=True, help_text='When the SMTP connection was last successfully tested')
    created_at = models.DateTimeField(auto_now_add=True)

    def get_fernet(self):
        from apps.common.crypto import normalize_key
        key = normalize_key(getattr(settings, 'FERNET_KEY', ''))
        if not key:
            raise ValueError("FERNET_KEY is not set or invalid in settings")
        return Fernet(key)

    def _candidate_fernets(self):
        from apps.common.crypto import candidate_fernets as _cf
        return _cf(include_expired=False)

    def set_password(self, raw_password):
        """Encrypt and set the SMTP password"""
        try:
            f = self.get_fernet()
            # Encrypt the password
            encrypted = f.encrypt(raw_password.encode())
            # Store as base64 string in database
            self._password = base64.urlsafe_b64encode(encrypted).decode()
            logger.info(f"Password encrypted successfully for {self.display_name}")
        except Exception as e:
            logger.error(f"Password encryption error: {e}")
            raise

    def get_password(self):
        """Decrypt and return the SMTP password"""
        if not self._password:
            return None

        ciphertext = self._password.strip().encode()

        for fernet in self._candidate_fernets():
            try:
                encrypted = base64.urlsafe_b64decode(ciphertext)
                decrypted = fernet.decrypt(encrypted).decode()

                primary_fernet = self.get_fernet()
                refreshed = base64.urlsafe_b64encode(primary_fernet.encrypt(decrypted.encode())).decode()
                if refreshed != self._password:
                    self._password = refreshed
                    self.save(update_fields=['_password'])

                return decrypted
            except Exception:
                continue

        logger.error("Password decryption error for sender '%s'", self.display_name)
        return None

    def reset_daily_quota_if_needed(self):
        """Reset daily email count if it's a new day. Call before checking limit."""
        from django.utils import timezone
        today = timezone.now().date()
        if self.last_reset_date != today:
            self.emails_sent_today = 0
            self.last_reset_date = today
            self.save(update_fields=['emails_sent_today', 'last_reset_date'])

    @property
    def is_limit_reached(self):
        """Check if daily email limit is reached. Does NOT modify database."""
        from django.utils import timezone
        today = timezone.now().date()
        if self.last_reset_date != today:
            return False
        return self.emails_sent_today >= self.daily_limit

    class Meta:
        unique_together = ('user', 'from_email')

    def save(self, *args, **kwargs):
        if self.from_email:
            self.from_email = self.from_email.strip().lower()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.display_name} "
