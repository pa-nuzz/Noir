from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Contact
from apps.webhooks.utils import dispatch_webhook_event

@receiver(post_save, sender=Contact)
def on_contact_saved(sender, instance, created, **kwargs):
    workspace_id = instance.contact_list.workspace_id if instance.contact_list else None
    if not workspace_id:
        return

    event_type = 'contact.created' if created else 'contact.updated'
    
    payload = {
        'contact_id': instance.id,
        'email': instance.email,
        'first_name': instance.first_name,
        'last_name': instance.last_name,
        'contact_list_id': instance.contact_list_id,
        'contact_list_name': instance.contact_list.name if instance.contact_list else '',
        'workspace_id': workspace_id,
        'is_active': instance.is_active,
        'unsubscribed': instance.unsubscribed,
        'bounce_count': instance.bounce_count,
        'created_at': instance.created_at.isoformat() if instance.created_at else None,
        'updated_at': instance.updated_at.isoformat() if instance.updated_at else None,
    }
    
    try:
        payload['tags'] = list(instance.tags.values_list('name', flat=True))
    except Exception:
        payload['tags'] = []

    dispatch_webhook_event(workspace_id, event_type, payload)

    initial_unsubscribed = getattr(instance, '_initial_unsubscribed', False)
    if instance.unsubscribed and not initial_unsubscribed:
        unsub_payload = {
            'contact_id': instance.id,
            'email': instance.email,
            'first_name': instance.first_name,
            'last_name': instance.last_name,
            'workspace_id': workspace_id,
            'unsubscribed_at': instance.unsubscribed_at.isoformat() if instance.unsubscribed_at else None,
        }
        dispatch_webhook_event(workspace_id, 'contact.unsubscribed', unsub_payload)
        
    instance._initial_unsubscribed = instance.unsubscribed


# Registering receiver for EmailUnsubscribe post_save to propagate unsubscribe to Workspace Contacts
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save)
def on_email_unsubscribe_saved(sender, instance, created, **kwargs):
    # Check sender class name to avoid circular import issues at startup
    if sender.__name__ != 'EmailUnsubscribe':
        return
    if not created:
        return

    email = instance.email
    campaign = instance.campaign
    if not campaign or not campaign.workspace_id:
        return

    contacts = Contact.objects.filter(
        contact_list__workspace_id=campaign.workspace_id,
        email__iexact=email,
        unsubscribed=False,
    )
    for c in contacts:
        c.unsubscribe()
