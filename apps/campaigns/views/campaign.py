import json
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q, F
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

import re

from apps.campaigns.models import Campaign, EmailTemplate, CampaignVariant, EmailEngagement, CampaignAttachment, EmailUnsubscribe
from apps.contacts.models import ContactList, ContactTag
from apps.campaigns import constants as C
from apps.senders.models import Sender
from apps.campaigns.services import delivery
from apps.campaigns.services.content import text_to_html, apply_campaign_spam_signals, merge_recipient_emails
from apps.campaigns.services.delivery import send_test_email_with_smtp, send_campaign_with_smtp, replace_variables
from apps.campaigns.tasks import run_send_campaign, async_send_campaign
from apps.campaigns.forms import CampaignForm
from apps.workspaces.decorators import require_workspace_permission
from apps.workspaces.query_helpers import filter_by_context
from apps.campaigns.services import (
    text_to_html,
    apply_campaign_spam_signals,
    merge_recipient_emails,
    send_test_email_with_smtp,
    update_campaign_unique_open_count,
)
from apps.campaigns.tasks import async_send_campaign, run_send_campaign
from apps.contacts.models import ContactList, Contact, ContactTag

logger = logging.getLogger(__name__)

wizard_steps = ["Contacts", "Identity", "Message", "Delivery", "Review"]


def _campaign_form_view(request, campaign=None, read_only=False):
    """Shared form view for creating/editing campaigns."""

    # Fetch user's active SMTP senders for form dropdown
    senders = filter_by_context(request, Sender.objects.filter(is_active=True))
    user_templates = filter_by_context(request, EmailTemplate.objects.filter(is_active=True))
    selected_template = None
    templates_json = json.dumps({
        str(t.id): {'id': t.id, 'name': t.name, 'subject': t.subject, 'body_html': t.body_html, 'body_text': t.body_text}
        for t in user_templates
    })

    if read_only:
        form = CampaignForm(request=request, instance=campaign)
        for _, field in form.fields.items():
            field.disabled = True
        return render(request, 'campaigns/create.html', {
            'form': form,
            'senders': senders,
            'campaign': campaign,
            'contact_lists': filter_by_context(request, ContactList.objects.all()),
            'templates': user_templates,
            'templates_json': templates_json,
            'read_only': True,
            'wizard_steps': wizard_steps,
            'current_step': 4,
        })

    if request.method == 'POST':
        form = CampaignForm(request.POST, request.FILES, request=request, instance=campaign)
        action = request.POST.get('action', 'save_draft')
        test_email = request.POST.get('test_email')

        if form.is_valid():
            campaign_obj = form.save(commit=False)
            campaign_obj.user = request.user
            ws_id = request.session.get('active_workspace_id')
            if ws_id:
                campaign_obj.workspace_id = ws_id
            # Link the source template if one was used
            template_id = request.POST.get('template_id')
            if template_id:
                try:
                    campaign_obj.template = filter_by_context(request, EmailTemplate.objects.all()).get(id=template_id)
                except (EmailTemplate.DoesNotExist, AttributeError):
                    logger.warning(f"Template {template_id} not found for user {request.user.id}")

            explicit_html = request.POST.get('body_html', '').strip()
            if explicit_html:
                campaign_obj.body_html = explicit_html
            else:
                raw_body = campaign_obj.body_text or ''
                campaign_obj.body_html = text_to_html(raw_body) if not raw_body.strip().startswith('<') else raw_body

            apply_campaign_spam_signals(campaign_obj)

            selected_list_ids = [v for v in request.POST.getlist('contact_lists') if v.isdigit()]
            selected_tag_ids = [v for v in request.POST.getlist('contact_tags') if v.isdigit()]

            if selected_list_ids:
                selected_lists = filter_by_context(request, ContactList.objects.filter(id__in=selected_list_ids))
                if selected_tag_ids:
                    tagged_emails = Contact.objects.filter(
                        contact_list__in=selected_lists, is_active=True, tags__id__in=selected_tag_ids,
                    ).values_list('email', flat=True).distinct()
                    campaign_obj.recipient_emails = merge_recipient_emails(campaign_obj.recipient_emails, list(tagged_emails))
                else:
                    for lst in selected_lists:
                        campaign_obj.recipient_emails = merge_recipient_emails(campaign_obj.recipient_emails, lst.get_email_list())
            elif selected_tag_ids:
                tagged_emails = Contact.objects.filter(
                    contact_list__in=filter_by_context(request, ContactList.objects.all()),
                    is_active=True, tags__id__in=selected_tag_ids,
                ).values_list('email', flat=True).distinct()
                campaign_obj.recipient_emails = merge_recipient_emails(campaign_obj.recipient_emails, list(tagged_emails))

            contact_list = form.cleaned_data.get('contact_list')
            if contact_list:
                campaign_obj.recipient_emails = merge_recipient_emails(campaign_obj.recipient_emails, contact_list.get_email_list())

            csv_context_raw = request.POST.get('csv_context', '')
            if csv_context_raw:
                try:
                    campaign_obj.recipient_context = json.loads(csv_context_raw)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid CSV context JSON for campaign {campaign_obj.id}")

            if action == 'send_test':
                if not test_email:
                    messages.error(request, 'Enter a test email address before sending a test.')
                    return render(request, 'campaigns/create.html', {
                        'form': form,
                        'senders': senders,
                        'campaign': campaign,
                        'contact_lists': filter_by_context(request, ContactList.objects.all()),
                        'available_tags': filter_by_context(request, ContactTag.objects.all()),
                        'templates': user_templates,
                        'templates_json': templates_json,
                        'wizard_steps': wizard_steps,
                        'current_step': 4,
                    })
                try:
                    validate_email(test_email)
                except ValidationError:
                    messages.error(request, 'Enter a valid test email address.')
                    return render(request, 'campaigns/create.html', {
                        'form': form,
                        'senders': senders,
                        'campaign': campaign,
                        'contact_lists': filter_by_context(request, ContactList.objects.all()),
                        'available_tags': filter_by_context(request, ContactTag.objects.all()),
                        'templates': user_templates,
                        'templates_json': templates_json,
                        'wizard_steps': wizard_steps,
                        'current_step': 4,
                    })
                campaign_obj.total_recipients = len(campaign_obj.get_recipient_list())
                if not campaign_obj.pk:
                    campaign_obj.status = 'draft'
                campaign_obj.save()
                _process_campaign_attachments(request, campaign_obj)
                try:
                    send_test_email_with_smtp(campaign_obj, test_email)
                    messages.success(request, f'Test email sent to {test_email}.')
                except Exception as exc:
                    messages.error(request, f'Test send failed: {exc}')
                return redirect('campaigns:campaign_edit', campaign_id=campaign_obj.id)

            if action == 'send_now':
                logger.info(f"[Campaign Send] User {request.user.id} initiating send for campaign '{campaign_obj.name}' (action={action})")
                pre_send_errors, recipient_count = _validate_campaign_ready_to_send(campaign_obj)
                if pre_send_errors:
                    logger.warning(f"[Campaign Send] Validation failed: {pre_send_errors}")
                    for error in pre_send_errors:
                        messages.error(request, error)
                    campaign_obj.status = 'draft'
                    campaign_obj.total_recipients = recipient_count
                    campaign_obj.save()
                    _process_campaign_attachments(request, campaign_obj)
                    return redirect('campaigns:campaign_edit', campaign_id=campaign_obj.id)

                logger.info(f"[Campaign Send] Validation passed, {recipient_count} recipients")
                campaign_obj.status = 'sending'
                campaign_obj.total_recipients = recipient_count
                campaign_obj.save()
                _process_campaign_attachments(request, campaign_obj)
                base_url = (settings.TRACKING_BASE_URL or request.build_absolute_uri('/')).rstrip('/')
                logger.info(f"[Campaign Send] Using base_url: {base_url}")
                
                try:
                    logger.info("[Campaign Send] Attempting Celery async send")
                    result = async_send_campaign.delay(campaign_obj.id, base_url, workspace_id=campaign_obj.workspace_id)
                    logger.info(f"[Campaign Send] Celery task submitted: {result}")
                    messages.success(request, f'Campaign "{campaign_obj.name}" is now sending in the background.')
                except Exception as celery_exc:
                    logger.warning(f"Celery unavailable, running send synchronously: {celery_exc}")
                    try:
                        logger.info("[Campaign Send] Running synchronous send")
                        sent, failed, error = run_send_campaign(campaign_obj.id, base_url)
                        logger.info(f"[Campaign Send] Sync send completed: sent={sent}, failed={failed}, error={error}")
                        if sent > 0:
                            messages.success(request, f'Campaign "{campaign_obj.name}" sent ({sent} recipients).')
                        else:
                            messages.error(request, f'Send failed: {error}')
                    except Exception as e2:
                        logger.exception(f"Sync send failed: {e2}")
                        messages.error(request, f'Failed to send campaign: {e2}')
                return redirect('campaigns:campaign_list')

            campaign_obj.status = 'scheduled' if campaign_obj.scheduled_at else 'draft'
            campaign_obj.total_recipients = len(campaign_obj.get_recipient_list())
            campaign_obj.save()
            _process_campaign_attachments(request, campaign_obj)
            messages.success(request, f'Campaign "{campaign_obj.name}" saved as {campaign_obj.status}.')
            return redirect('campaigns:campaign_list')
    # GET request or form initialization: display campaign form
    else:
        initial = {}
        template_id = request.GET.get('template')
        if template_id and not campaign:
            try:
                selected_template = filter_by_context(request, EmailTemplate.objects.filter(is_active=True)).get(id=template_id)
                initial['subject'] = selected_template.subject
                initial['body_text'] = selected_template.body_text or ''
                initial['body_html'] = selected_template.body_html or ''
            except (EmailTemplate.DoesNotExist, AttributeError):
                logger.warning(f"Template {template_id} not found for campaign creation")
        form = CampaignForm(request=request, instance=campaign, initial=initial or None)

        return render(request, 'campaigns/create.html', {
            'form': form, 'senders': senders, 'campaign': campaign,
            'contact_lists': filter_by_context(request, ContactList.objects.all()),
            'available_tags': filter_by_context(request, ContactTag.objects.all()),
            'templates': user_templates, 'templates_json': templates_json,
            'selected_template': selected_template, 'csv_columns': [],
            'wizard_steps': wizard_steps, 'current_step': 4,
        })

    initial = {}
    template_id = request.GET.get('template')
    if template_id and not campaign:
        try:
            selected_template = request.user.email_templates.get(id=template_id, is_active=True)
            initial['subject'] = selected_template.subject
            initial['body_text'] = selected_template.body_text or ''
            initial['body_html'] = selected_template.body_html or ''
        except EmailTemplate.DoesNotExist:
            logger.warning(f"Template {template_id} not found for campaign creation")
    form = CampaignForm(request=request, instance=campaign, initial=initial or None)

    csv_columns = []
    if campaign and campaign.recipient_context:
        cols = set()
        for data in campaign.recipient_context.values():
            cols.update(data.keys())
        csv_columns = sorted(cols)

    return render(request, 'campaigns/create.html', {
        'form': form,
        'senders': senders,
        'campaign': campaign,
        'contact_lists': filter_by_context(request, ContactList.objects.all()),
        'available_tags': filter_by_context(request, ContactTag.objects.all()),
        'templates': user_templates,
        'templates_json': templates_json,
        'selected_template': selected_template,
        'csv_columns': csv_columns,
        'wizard_steps': wizard_steps,
        'current_step': 0,
    })


# These functions are defined below _campaign_form_view

def _validate_campaign_ready_to_send(campaign):
    """Validate that a campaign is ready to send."""
    errors = []
    if not campaign.sender:
        errors.append('Select a sender profile before sending.')
    if not campaign.get_recipient_list():
        errors.append('Add at least one valid recipient email before sending.')
    if not campaign.subject:
        errors.append('Add a subject line before sending.')
    if not campaign.body_html and not campaign.body_text:
        errors.append('Add content before sending.')
    return errors, len(campaign.get_recipient_list())


def _process_campaign_attachments(request, campaign):
    """Process uploaded attachments for a campaign."""
    if 'attachments' in request.FILES:
        for file in request.FILES.getlist('attachments'):
            CampaignAttachment.objects.create(
                campaign=campaign,
                file=file,
                original_filename=file.name,
                mime_type=file.content_type,
                file_size=file.size,
            )


@login_required
@require_workspace_permission('campaigns', 'create')
def campaign_create(request):
    """Create a new campaign.

    Args:
        request: The HTTP request object.

    Returns:
        HttpResponse: Rendered campaign form template.
    """
    return _campaign_form_view(request)


@login_required
@require_workspace_permission('campaigns', 'edit')
def campaign_edit(request, campaign_id):
    """Edit an existing campaign.

    Args:
        request: The HTTP request object.
        campaign_id (int): Primary key of the campaign to edit.

    Returns:
        HttpResponse: Rendered campaign form template for editing.
    """
    campaign = get_object_or_404(filter_by_context(request, Campaign.objects.all()), id=campaign_id)
    return _campaign_form_view(request, campaign=campaign)


@login_required
@require_workspace_permission('campaigns', 'read')
def campaign_view(request, campaign_id):
    """View a campaign in read-only mode.

    Args:
        request: The HTTP request object.
        campaign_id (int): Primary key of the campaign to view.

    Returns:
        HttpResponse: Rendered campaign form with all fields disabled.
    """
    campaign = get_object_or_404(filter_by_context(request, Campaign.objects.all()), id=campaign_id)
    return _campaign_form_view(request, campaign=campaign, read_only=True)


@login_required
@require_workspace_permission('campaigns', 'read')
def campaign_list(request):
    """Display a paginated list of campaigns with engagement summaries.

    Shows campaign status breakdown counts and email statistics (sent, opened, clicked)
    aggregated from EmailEngagement records.

    Args:
        request: The HTTP request object containing the authenticated user.

    Returns:
        HttpResponse: Rendered campaigns list template with campaign and stats data.
    """
    # Fetch campaigns scoped to active workspace or user
    campaigns_qs = filter_by_context(request, Campaign.objects.filter(
        is_deleted=False
    )).select_related('sender').prefetch_related('engagements', 'attachments')
    scoped_campaigns = filter_by_context(request, Campaign.objects.all())
    engagements = EmailEngagement.objects.filter(campaign__in=scoped_campaigns, campaign__is_deleted=False)

    query = (request.GET.get('q') or '').strip()
    status = (request.GET.get('status') or 'all').strip().lower()
    start_date = (request.GET.get('start') or '').strip()
    end_date = (request.GET.get('end') or '').strip()

    if query:
        campaigns_qs = campaigns_qs.filter(Q(name__icontains=query) | Q(subject__icontains=query))

    valid_statuses = {choice[0] for choice in Campaign.STATUS_CHOICES}
    if status in valid_statuses:
        campaigns_qs = campaigns_qs.filter(status=status)
    else:
        status = 'all'

    if start_date:
        try:
            campaigns_qs = campaigns_qs.filter(updated_at__date__gte=start_date)
        except (ValueError, ValidationError):
            logger.warning(f"Invalid start_date filter: {start_date}")
            start_date = ''
    if end_date:
        try:
            campaigns_qs = campaigns_qs.filter(updated_at__date__lte=end_date)
        except (ValueError, ValidationError):
            logger.warning(f"Invalid end_date filter: {end_date}")
            end_date = ''

    paginator = Paginator(campaigns_qs, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    campaigns = page_obj.object_list
    base_qs = filter_by_context(request, Campaign.objects.filter(is_deleted=False))
    status_counts = {
        'all': base_qs.count(),
        'draft': base_qs.filter(status='draft').count(),
        'scheduled': base_qs.filter(status='scheduled').count(),
        'sent': base_qs.filter(status='sent').count(),
        'failed': base_qs.filter(status='failed').count(),
    }
    trash_count = filter_by_context(request, Campaign.objects.filter(is_deleted=True)).count()
    # Aggregate email metrics from EmailEngagement (event-driven, not denormalized fields)
    email_totals = {
        'recipients': engagements.values('recipient_email').distinct().count(),
        'sent': engagements.count(),
        'opened': engagements.filter(opened_at__isnull=False).count(),
        'clicked': engagements.filter(clicked_at__isnull=False).count(),
    }
    return render(request, 'campaigns/list.html', {
        'campaigns': campaigns,
        'page_obj': page_obj,
        'status_counts': status_counts,
        'email_totals': email_totals,
        'filters': {
            'q': query,
            'status': status,
            'start': start_date,
            'end': end_date,
        },
        'trash_count': trash_count,
    })


@login_required
@require_workspace_permission('campaigns', 'create')
def campaign_duplicate(request, campaign_id):
    source_campaign = get_object_or_404(filter_by_context(request, Campaign.objects.all()), id=campaign_id)

    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('campaigns:campaign_list')

    duplicate = Campaign.objects.create(
        user=request.user,
        sender=source_campaign.sender,
        name=f"{source_campaign.name} (Copy)",
        subject=source_campaign.subject,
        body_html=source_campaign.body_html,
        body_text=source_campaign.body_text,
        recipient_emails=source_campaign.recipient_emails,
        from_name=source_campaign.from_name,
        reply_to=source_campaign.reply_to,
        status='draft',
        scheduled_at=None,
        total_recipients=source_campaign.total_recipients,
        spam_score=source_campaign.spam_score,
        spam_risk=source_campaign.spam_risk,
        template=source_campaign.template,
    )

    for att in source_campaign.attachments.all():
        duplicate.attachments.create(
            file=att.file,
            original_filename=att.original_filename,
            mime_type=att.mime_type,
            file_size=att.file_size,
        )

    messages.success(request, f'Campaign duplicated as "{duplicate.name}".')
    return redirect('campaigns:campaign_edit', campaign_id=duplicate.id)


@login_required
@require_workspace_permission('campaigns', 'delete')
def campaign_delete(request, campaign_id):
    """Soft-delete a campaign (moves to trash)."""
    campaign = get_object_or_404(filter_by_context(request, Campaign.objects.all()), id=campaign_id)
    if request.method != 'POST':
        return redirect('campaigns:campaign_list')
    campaign.is_deleted = True
    campaign.deleted_at = timezone.now()
    campaign.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])
    messages.success(request, f'Campaign "{campaign.name}" moved to trash.')
    return redirect('campaigns:campaign_list')


@login_required
@require_workspace_permission('campaigns', 'read')
def campaign_trash(request):
    """Show soft-deleted campaigns."""
    campaigns = filter_by_context(request, Campaign.objects.filter(is_deleted=True)).select_related('sender').order_by('-deleted_at')
    paginator = Paginator(campaigns, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'campaigns/trash.html', {
        'campaigns': page_obj.object_list,
        'page_obj': page_obj,
    })


@require_POST
@login_required
@require_workspace_permission('campaigns', 'edit')
def campaign_restore(request, campaign_id):
    """Restore a soft-deleted campaign."""
    campaign = get_object_or_404(filter_by_context(request, Campaign.objects.all()), id=campaign_id)
    campaign.is_deleted = False
    campaign.deleted_at = None
    campaign.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])
    messages.success(request, f'Campaign "{campaign.name}" restored.')
    return redirect('campaigns:campaign_list')


