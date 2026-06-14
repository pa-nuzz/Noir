from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from .models import EditLock


LOCK_DURATION_MINUTES = 10


def acquire_lock(model_obj, user):
    ct = ContentType.objects.get_for_model(model_obj)
    lock, created = EditLock.objects.get_or_create(
        content_type=ct,
        object_id=model_obj.pk,
        defaults={
            'locked_by': user,
            'expires_at': timezone.now() + timedelta(minutes=LOCK_DURATION_MINUTES),
        },
    )
    if not created:
        if lock.locked_by == user:
            lock.renew(minutes=LOCK_DURATION_MINUTES)
            return lock, True
        if lock.is_expired():
            lock.locked_by = user
            lock.locked_at = timezone.now()
            lock.expires_at = timezone.now() + timedelta(minutes=LOCK_DURATION_MINUTES)
            lock.save()
            return lock, True
        return lock, False
    return lock, True


def release_lock(model_obj):
    ct = ContentType.objects.get_for_model(model_obj)
    EditLock.objects.filter(content_type=ct, object_id=model_obj.pk).delete()


def get_lock(model_obj):
    ct = ContentType.objects.get_for_model(model_obj)
    try:
        lock = EditLock.objects.get(content_type=ct, object_id=model_obj.pk)
        if lock.is_expired():
            lock.delete()
            return None
        return lock
    except EditLock.DoesNotExist:
        return None
