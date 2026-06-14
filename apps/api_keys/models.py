import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


class WorkspaceAPIKey(models.Model):
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, related_name='api_keys')
    name = models.CharField(max_length=255, help_text='Label to identify this key')
    prefix = models.CharField(max_length=8, unique=True, editable=False)
    key_hash = models.CharField(max_length=128, editable=False)
    scopes = models.JSONField(default=list, blank=True, help_text='List of permitted actions or "*" for all')
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    last_used_ip = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Workspace API key'
        verbose_name_plural = 'Workspace API keys'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.prefix}...)'

    @property
    def is_expired(self):
        if self.expires_at is None:
            return False
        return timezone.now() >= self.expires_at

    def record_usage(self, ip=''):
        WorkspaceAPIKey.objects.filter(pk=self.pk).update(
            last_used_at=timezone.now(),
            last_used_ip=ip or '',
        )

    @classmethod
    def generate_key(cls):
        raw = secrets.token_hex(32)
        prefix = raw[:8]
        key_hash = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        return raw, prefix, key_hash

    @classmethod
    def create_key(cls, workspace, name, scopes=None, expires_at=None):
        raw, prefix, key_hash = cls.generate_key()
        api_key = cls.objects.create(
            workspace=workspace,
            name=name,
            prefix=prefix,
            key_hash=key_hash,
            scopes=scopes or [],
            expires_at=expires_at,
        )
        return api_key, raw
