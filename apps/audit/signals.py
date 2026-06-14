import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from apps.workspaces.models import AuditLog

logger = logging.getLogger(__name__)

SENSITIVE_MODELS = {
    'Campaign': 'apps.campaigns.models',
    'EmailTemplate': 'apps.campaigns.models',
    'Sender': 'apps.senders.models',
    'EmailInbox': 'apps.inbox.models',
    'ContactList': 'apps.contacts.models',
    'Contact': 'apps.contacts.models',
    'Workflow': 'apps.automations.models',
    'SocialAccount': 'apps.social_accounts.models',
    'SocialPost': 'apps.social_accounts.models',
    'ContentItem': 'apps.content_studio.models',
    'WorkspaceStorageConfig': 'apps.workspaces.models',
    'WorkspaceMembership': 'apps.workspaces.models',
    'APIKey': 'apps.api_keys.models',
}


def _get_workspace(instance):
    if hasattr(instance, 'workspace') and instance.workspace_id:
        return instance.workspace
    return None


def _summarize(instance):
    field = getattr(instance, 'name', None) or getattr(instance, 'email', None) or getattr(instance, 'subject', None) or getattr(instance, 'display_name', None) or str(instance)
    return str(field)[:120]


@receiver(post_save)
def audit_post_save(sender, instance, created, **kwargs):
    model_name = sender.__name__
    if model_name not in SENSITIVE_MODELS:
        return
    module = sender.__module__
    if module != SENSITIVE_MODELS[model_name]:
        return

    workspace = _get_workspace(instance)
    if not workspace:
        return

    import threading
    user = getattr(threading, '_audit_user', None)
    ip = getattr(threading, '_audit_ip', None)

    action = 'created' if created else 'updated'
    AuditLog.objects.create(
        workspace=workspace,
        user=user,
        action=f"{model_name} {action}: {_summarize(instance)}",
        details={
            'model': model_name,
            'object_id': instance.pk,
            'summary': _summarize(instance),
        },
        ip_address=ip,
    )


@receiver(post_delete)
def audit_post_delete(sender, instance, **kwargs):
    model_name = sender.__name__
    if model_name not in SENSITIVE_MODELS:
        return
    module = sender.__module__
    if module != SENSITIVE_MODELS[model_name]:
        return

    workspace = _get_workspace(instance)
    if not workspace:
        return

    import threading
    user = getattr(threading, '_audit_user', None)
    ip = getattr(threading, '_audit_ip', None)

    AuditLog.objects.create(
        workspace=workspace,
        user=user,
        action=f"{model_name} deleted: {_summarize(instance)}",
        details={
            'model': model_name,
            'object_id': instance.pk,
            'summary': _summarize(instance),
        },
        ip_address=ip,
    )
