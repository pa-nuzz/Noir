import threading
from contextlib import contextmanager

from django.db import models
from django.db.models import Q

_thread_local = threading.local()


def get_current_tenant():
    return getattr(_thread_local, 'tenant', None)


def set_current_tenant(tenant):
    _thread_local.tenant = tenant


def clear_current_tenant():
    if hasattr(_thread_local, 'tenant'):
        del _thread_local.tenant


@contextmanager
def tenant_context(tenant):
    old = get_current_tenant()
    set_current_tenant(tenant)
    try:
        yield
    finally:
        if old is not None:
            set_current_tenant(old)
        else:
            clear_current_tenant()


class TenantManager(models.Manager):
    def __init__(self, workspace_field='workspace', related_filter=None):
        super().__init__()
        self.workspace_field = workspace_field
        self.related_filter = related_filter

    def get_queryset(self):
        qs = super().get_queryset()
        tenant = get_current_tenant()
        if tenant is not None:
            if self.related_filter:
                return qs.filter(**{self.related_filter: tenant})
            if hasattr(self.model, self.workspace_field):
                return qs.filter(
                    Q(**{self.workspace_field: tenant}) |
                    Q(**{self.workspace_field + '__isnull': True})
                )
        return qs
