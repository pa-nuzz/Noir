import threading

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.utils.nepali_calendar import ad_to_bs


class AuditMixin(models.Model):
    postby = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+',
    )
    postdatead = models.DateTimeField(default=timezone.now)
    postdatebs = models.CharField(max_length=10, blank=True, default='')
    posttime = models.TimeField(default=timezone.now)

    modifyby = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+',
    )
    modifydatead = models.DateTimeField(null=True, blank=True)
    modifydatebs = models.CharField(max_length=10, blank=True, default='')
    modifytime = models.TimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        now_ad = timezone.now()
        is_new = self._state.adding or not self.postdatead
        user = getattr(threading, '_audit_user', None)

        if is_new:
            self.postdatead = now_ad
            self.posttime = now_ad.time()
            self.postdatebs = ad_to_bs(now_ad)
            if user and not self.postby_id:
                self.postby = user

        self.modifydatead = now_ad
        self.modifytime = now_ad.time()
        self.modifydatebs = ad_to_bs(now_ad)
        if user:
            self.modifyby = user

        super().save(*args, **kwargs)
