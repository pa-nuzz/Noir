from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from core.models import AuditMixin


class EditLock(AuditMixin):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='edit_locks',
    )
    locked_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        unique_together = ('content_type', 'object_id')
        verbose_name = 'Edit lock'
        verbose_name_plural = 'Edit locks'

    def __str__(self):
        return f"Lock on {self.content_type.model}:{self.object_id} by {self.locked_by.email}"

    def is_expired(self):
        return timezone.now() >= self.expires_at

    def renew(self, minutes=10):
        self.expires_at = timezone.now() + timezone.timedelta(minutes=minutes)
        self.save(update_fields=['expires_at'])
