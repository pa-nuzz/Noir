import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.db.models import Q

from .models import Workflow, WorkflowEnrollment, WorkflowNode, WorkflowEdge

logger = logging.getLogger(__name__)


def process_workflow_enrollments():
    now = timezone.now()
    ready = WorkflowEnrollment.objects.filter(
        status='active',
        next_execution_at__lte=now,
    ).select_related('workflow', 'contact')

    processed = 0
    for enrollment in ready:
        try:
            _advance_enrollment(enrollment)
            processed += 1
        except Exception as exc:
            logger.error(
                f"Error advancing enrollment {enrollment.id} "
                f"(contact={enrollment.contact_id}, workflow={enrollment.workflow_id}): {exc}"
            )

    if processed:
        logger.info(f"Workflow engine processed {processed} enrollment(s).")
    return processed


def _advance_enrollment(enrollment):
    workflow = enrollment.workflow
    current_node_id = enrollment.current_node_id

    if current_node_id is None:
        next_node = WorkflowNode.objects.filter(
            workflow=workflow,
            type='trigger',
        ).order_by('created_at').first()
    else:
        edge = WorkflowEdge.objects.filter(
            workflow=workflow,
            from_node_id=current_node_id,
        ).order_by('created_at').first()

        if edge is None:
            enrollment.status = 'completed'
            enrollment.current_node_id = None
            enrollment.next_execution_at = None
            enrollment.save()
            _trigger_workflow_completed(enrollment)
            return

        next_node = WorkflowNode.objects.filter(
            workflow=workflow,
            node_id=edge.to_node_id,
        ).first()

    if next_node is None:
        logger.warning(
            "Enrollment %s (contact=%s, workflow=%s) completed — no further nodes in graph",
            enrollment.id, enrollment.contact_id, workflow.id,
        )
        enrollment.status = 'completed'
        enrollment.current_node_id = None
        enrollment.next_execution_at = None
        enrollment.save()
        _trigger_workflow_completed(enrollment)
        return

    with transaction.atomic():
        enrollment.current_node_id = next_node.node_id

        if next_node.type == 'delay':
            hours = next_node.config.get('hours', 24)
            enrollment.next_execution_at = timezone.now() + timedelta(hours=hours)

        elif next_node.type == 'wait_until_condition':
            _handle_wait_condition(enrollment, next_node)

        elif next_node.type == 'branch':
            _handle_branch(enrollment, next_node)

        elif next_node.type == 'goal':
            _handle_goal(enrollment, next_node)

        elif next_node.type == 'action':
            action_type = next_node.config.get('action', '')
            if action_type == 'send_email' and next_node.config.get('template_id'):
                _dispatch_template_email(enrollment, next_node.config['template_id'])
            elif action_type == 'add_tag' and next_node.config.get('tags'):
                _apply_tags(enrollment, next_node.config['tags'])
            elif action_type == 'remove_tag' and next_node.config.get('tags'):
                _remove_tags(enrollment, next_node.config['tags'])
            enrollment.next_execution_at = timezone.now()

        elif next_node.type == 'trigger':
            enrollment.next_execution_at = timezone.now()

        enrollment.save()


def _handle_wait_condition(enrollment, node):
    """
    Wait until a condition is met. Supported condition types:
      - opened_email: wait until Contact has an EmailEngagement with opens > 0
      - clicked_link: wait until Contact has an EmailClickEvent
      - tag_added: wait until Contact has the specified tag
    Config: { condition_type, target_value, max_days }
    """
    config = node.config
    condition_type = config.get('condition_type', '')
    target_value = config.get('target_value', '')
    max_days = config.get('max_days', 7)
    contact = enrollment.contact

    met = False
    if condition_type == 'opened_email':
        from apps.campaigns.models import EmailEngagement
        met = EmailEngagement.objects.filter(
            contact_email=contact.email,
            opens__gt=0,
        ).exists()
    elif condition_type == 'clicked_link':
        from apps.campaigns.models import EmailEngagement
        met = EmailEngagement.objects.filter(
            contact_email=contact.email,
            clicks__gt=0,
        ).exists()
    elif condition_type == 'tag_added' and target_value:
        met = contact.tags.filter(name=target_value).exists()

    if met:
        enrollment.next_execution_at = timezone.now()
    else:
        elapsed = timezone.now() - enrollment.created_at
        if elapsed > timedelta(days=max_days):
            logger.info(
                f"Wait condition timed out for enrollment {enrollment.id} "
                f"({condition_type}), advancing"
            )
            enrollment.next_execution_at = timezone.now()
        else:
            enrollment.next_execution_at = timezone.now() + timedelta(minutes=15)


def _handle_branch(enrollment, node):
    """
    Evaluate an if/else condition on contact properties and take the matching edge.
    Config: { property, operator, value }
    The edge whose condition field matches 'true' or 'default' is followed.
    """
    config = node.config
    prop = config.get('property', '')
    operator = config.get('operator', 'equals')
    expected_value = config.get('value', '')
    contact = enrollment.contact

    actual_value = None
    if prop == 'email':
        actual_value = contact.email
    elif prop == 'is_active':
        actual_value = str(contact.is_active)
    elif prop and hasattr(contact, prop):
        actual_value = str(getattr(contact, prop, ''))

    result = False
    if actual_value is not None:
        if operator == 'equals':
            result = actual_value.lower() == str(expected_value).lower()
        elif operator == 'not_equals':
            result = actual_value.lower() != str(expected_value).lower()
        elif operator == 'contains':
            result = str(expected_value).lower() in actual_value.lower()
        elif operator == 'gt':
            try:
                result = float(actual_value) > float(expected_value)
            except (ValueError, TypeError):
                result = False
        elif operator == 'lt':
            try:
                result = float(actual_value) < float(expected_value)
            except (ValueError, TypeError):
                result = False

    edge = WorkflowEdge.objects.filter(
        workflow=node.workflow,
        from_node_id=node.node_id,
        condition='true' if result else 'false',
    ).order_by('created_at').first()

    if edge is None:
        edge = WorkflowEdge.objects.filter(
            workflow=node.workflow,
            from_node_id=node.node_id,
            condition='default',
        ).order_by('created_at').first()

    if edge:
        enrollment.current_node_id = edge.to_node_id
        enrollment.next_execution_at = timezone.now()
    else:
        enrollment.next_execution_at = timezone.now()


def _handle_goal(enrollment, node):
    """
    Goal node — stops enrollment when a contact reaches a conversion point.
    If the goal condition is already met, mark as completed.
    Config: { goal_type }
    Supported: replied, clicked_sale_link, unsubscribed, tag_added
    """
    config = node.config
    goal_type = config.get('goal_type', '')
    contact = enrollment.contact

    met = False
    if goal_type == 'replied':
        from apps.campaigns.models import EmailEngagement
        met = EmailEngagement.objects.filter(
            contact_email=contact.email,
            replies__gt=0,
        ).exists()
    elif goal_type == 'clicked_sale_link':
        from apps.campaigns.models import EmailClickEvent
        met = EmailClickEvent.objects.filter(
            engagement__contact_email=contact.email,
        ).exists()
    elif goal_type == 'unsubscribed':
        from apps.campaigns.models import EmailUnsubscribe
        met = EmailUnsubscribe.objects.filter(
            email=contact.email,
        ).exists()
    elif goal_type == 'tag_added' and config.get('target_tag'):
        met = contact.tags.filter(name=config['target_tag']).exists()

    if met:
        enrollment.status = 'completed'
        enrollment.current_node_id = None
        enrollment.next_execution_at = None
        enrollment.save()
        _trigger_workflow_completed(enrollment)
        return

    enrollment.next_execution_at = timezone.now() + timedelta(hours=1)


def _dispatch_template_email(enrollment, template_id):
    try:
        from apps.campaigns.models import EmailTemplate
        from apps.campaigns.services.delivery import send_campaign_with_smtp
        from apps.campaigns.models import Campaign
        from apps.senders.models import Sender

        sender = Sender.objects.filter(
            user=enrollment.workflow.user,
            is_active=True,
        ).first()
        if not sender:
            logger.warning(f"No active sender for workflow {enrollment.workflow_id}")
            return

        template = EmailTemplate.objects.filter(id=template_id).first()
        if not template:
            logger.warning(f"Template {template_id} not found")
            return

        campaign = Campaign.objects.create(
            user=enrollment.workflow.user,
            sender=sender,
            name=f"Automation: {enrollment.workflow.name}",
            subject=template.subject,
            body_text=template.body_text,
            body_html=template.body_html,
            recipient_emails=enrollment.contact.email,
            status='sending',
            source_workflow=enrollment.workflow,
        )
        base_url = ''
        from django.conf import settings
        base_url = getattr(settings, 'PUBLIC_BASE_URL', 'http://localhost:8000')

        try:
            send_campaign_with_smtp(
                campaign,
                base_url,
                recipients_override=[enrollment.contact.email],
            )
        except Exception as exc:
            logger.error(f"Auto-dispatch failed for enrollment {enrollment.id}: {exc}")
            campaign.status = 'failed'
            campaign.save(update_fields=['status'])
    except Exception as exc:
        logger.error(f"Error dispatching template email: {exc}")


def _apply_tags(enrollment, tags):
    try:
        from apps.contacts.models import ContactTag
        contact = enrollment.contact
        for tag_name in tags:
            tag, _ = ContactTag.objects.get_or_create(
                user=enrollment.workflow.user,
                name=tag_name.strip(),
            )
            contact.tags.add(tag)
    except Exception as exc:
        logger.error(f"Error applying tags: {exc}")


def _remove_tags(enrollment, tags):
    try:
        from apps.contacts.models import ContactTag
        contact = enrollment.contact
        for tag_name in tags:
            tag = ContactTag.objects.filter(
                user=enrollment.workflow.user,
                name=tag_name.strip(),
            ).first()
            if tag:
                contact.tags.remove(tag)
    except Exception as exc:
        logger.error(f"Error removing tags: {exc}")


def enroll_contact(contact, workflow):
    enrollment, created = WorkflowEnrollment.objects.get_or_create(
        contact=contact,
        workflow=workflow,
        defaults={
            'status': 'active',
            'next_execution_at': timezone.now(),
        }
    )
    is_triggered = created
    if not created and enrollment.status != 'active':
        enrollment.status = 'active'
        enrollment.next_execution_at = timezone.now()
        enrollment.save()
        is_triggered = True

    if is_triggered:
        from apps.webhooks.utils import dispatch_webhook_event
        workspace_id = workflow.workspace_id
        if workspace_id:
            dispatch_webhook_event(
                workspace_id=workspace_id,
                event_type='workflow.triggered',
                payload={
                    'workflow_id': workflow.id,
                    'workflow_name': workflow.name,
                    'contact_id': contact.id,
                    'contact_email': contact.email,
                    'enrolled_at': timezone.now().isoformat(),
                }
            )

    return enrollment


def _trigger_workflow_completed(enrollment):
    from apps.webhooks.utils import dispatch_webhook_event
    workspace_id = enrollment.workflow.workspace_id
    if workspace_id:
        dispatch_webhook_event(
            workspace_id=workspace_id,
            event_type='workflow.completed',
            payload={
                'workflow_id': enrollment.workflow.id,
                'workflow_name': enrollment.workflow.name,
                'contact_id': enrollment.contact_id,
                'contact_email': enrollment.contact.email,
                'completed_at': timezone.now().isoformat(),
            }
        )
