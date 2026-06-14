import logging

from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver

from apps.contacts.models import Contact, ContactTag
from .models import Workflow, WorkflowNode
from .engine import enroll_contact

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Contact)
def on_contact_created(sender, instance, created, **kwargs):
    if not created:
        return
    contact_list = instance.contact_list
    if not contact_list:
        return
    ws = contact_list.workspace
    filter_kwargs = {'is_active': True, 'nodes__type': 'trigger', 'nodes__config__event': 'list_signup'}
    if ws:
        filter_kwargs['workspace'] = ws
    else:
        filter_kwargs['user'] = contact_list.user
    workflows = Workflow.objects.filter(**filter_kwargs).distinct()
    for wf in workflows:
        try:
            enroll_contact(instance, wf)
            logger.info("Auto-enrolled %s in workflow '%s' (list signup)", instance.email, wf.name)
        except Exception as exc:
            logger.error("Failed to enroll %s in workflow %s: %s", instance.email, wf.id, exc)


@receiver(m2m_changed, sender=Contact.tags.through)
def on_contact_tags_changed(sender, instance, action, pk_set, **kwargs):
    if action != 'post_add':
        return
    contact_list = instance.contact_list
    if not contact_list:
        return
    ws = contact_list.workspace
    filter_kwargs = {'is_active': True, 'nodes__type': 'trigger', 'nodes__config__event': 'tag_added'}
    if ws:
        filter_kwargs['workspace'] = ws
    else:
        filter_kwargs['user'] = contact_list.user
    workflows = Workflow.objects.filter(**filter_kwargs).distinct()
    for wf in workflows:
        try:
            enroll_contact(instance, wf)
            logger.info("Auto-enrolled %s in workflow '%s' (tag added)", instance.email, wf.name)
        except Exception as exc:
            logger.error("Failed to enroll %s in workflow %s: %s", instance.email, wf.id, exc)
