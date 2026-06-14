"""Campaign sending views (send, retry, AB winner)."""

import json
import logging

from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.conf import settings
from django.utils.html import mark_safe, escape
from django.contrib import messages
from django.urls import reverse
from django_ratelimit.decorators import ratelimit

from apps.campaigns.models import Campaign, CampaignVariant
from apps.campaigns.tasks import async_send_campaign
from apps.campaigns.views.campaign import _validate_campaign_ready_to_send
from apps.workspaces.decorators import require_workspace_permission
from apps.workspaces.query_helpers import filter_by_context

logger = logging.getLogger(__name__)



@ratelimit(key='user', rate='10/m', method='POST', block=True)
@login_required
@require_workspace_permission('campaigns', 'edit')
def campaign_send(request, campaign_id):
    """Send a draft campaign or resend an existing campaign.
    
    Handles POST requests to send a campaign. Accumulates sent counts if re-sending
    the same campaign multiple times.
    
    Args:
        request: The HTTP request object with POST method.
        campaign_id (int): Primary key of the campaign to send.
    
    Returns:
        HttpResponseRedirect: Redirect to campaign list after send attempt.
    """
    if request.method != 'POST':
        return redirect('campaigns:campaign_list')

    campaign = get_object_or_404(filter_by_context(request, Campaign.objects.all()), id=campaign_id)

    pre_send_errors, recipient_count = _validate_campaign_ready_to_send(campaign)
    if pre_send_errors:
        for error in pre_send_errors:
            messages.error(request, error)
        return redirect('campaigns:campaign_edit', campaign_id=campaign.id)

    # Mark campaign as sending and save (with row lock to prevent race conditions)
    with transaction.atomic():
        campaign = Campaign.objects.select_for_update().get(
            id=campaign_id,
            **({'workspace_id': request.session.get('active_workspace_id')} if request.session.get('active_workspace_id') else {'user': request.user})
        )
        campaign.status = 'sending'
        campaign.total_recipients = recipient_count
        campaign.save(update_fields=['status', 'total_recipients', 'updated_at'])
    base_url = (settings.TRACKING_BASE_URL or request.build_absolute_uri('/')).rstrip('/')
    try:
        async_send_campaign.delay(campaign.id, base_url)
    except Exception:
        logger.warning("Celery unavailable, sending campaign synchronously")
        from apps.campaigns.tasks import run_send_campaign
        sent, failed, error = run_send_campaign(campaign.id, base_url)
        if sent > 0:
            messages.success(
                request,
                mark_safe(
                    f'Campaign "<strong>{escape(campaign.name)}</strong>" sent to <strong>{sent}</strong> recipients. '
                    f'<a href="{reverse("campaigns:campaign_analytics", args=[campaign.id])}" '
                    f'class="text-indigo-600 hover:text-indigo-800 font-semibold underline">View analytics →</a>'
                )
            )
        else:
            messages.error(request, f'Failed to send campaign: {error}')
        return redirect('campaigns:campaign_list')

    messages.success(
        request,
        mark_safe(
            f'Campaign "<strong>{escape(campaign.name)}</strong>" is sending to <strong>{recipient_count}</strong> recipients. '
            f'<a href="{reverse("campaigns:campaign_analytics", args=[campaign.id])}" '
            f'class="text-indigo-600 hover:text-indigo-800 font-semibold underline">View analytics →</a>'
        )
    )
    return redirect('campaigns:campaign_list')



@ratelimit(key='user', rate='5/m', method='POST', block=True)
@login_required
@require_workspace_permission('campaigns', 'edit')
def campaign_retry_failed(request, campaign_id):
    campaign = get_object_or_404(filter_by_context(request, Campaign.objects.all()), id=campaign_id)
    if request.method != 'POST':
        return redirect('campaigns:campaign_list')

    all_recipients = campaign.get_recipient_list()
    if not all_recipients:
        messages.error(request, 'No recipients found for this campaign.')
        return redirect('campaigns:campaign_edit', campaign_id=campaign.id)

    sent_recipients = set(
        campaign.engagements.values_list('recipient_email', flat=True)
    )
    retry_recipients = [email for email in all_recipients if email not in sent_recipients]

    if not retry_recipients:
        messages.info(request, 'No failed recipients left to retry.')
        return redirect('campaigns:campaign_list')

    campaign.status = 'sending'
    campaign.save(update_fields=['status', 'updated_at'])
    base_url = (settings.TRACKING_BASE_URL or request.build_absolute_uri('/')).rstrip('/')
    try:
        async_send_campaign.delay(campaign.id, base_url, recipients_override=retry_recipients)
    except Exception:
        logger.warning("Celery unavailable, retrying campaign synchronously")
        from apps.campaigns.tasks import run_send_campaign
        sent, failed, error = run_send_campaign(campaign.id, base_url, recipients_override=retry_recipients)
        if sent > 0:
            messages.success(request, f'Retried {sent} recipients.')
        else:
            messages.error(request, f'Retry failed: {error}')
        return redirect('campaigns:campaign_list')
    messages.success(request, f'Retrying {len(retry_recipients)} failed recipients in the background.')
    return redirect('campaigns:campaign_list')



@login_required
@require_POST
@require_workspace_permission('campaigns', 'edit')
def set_ab_winner(request):
    """Manually set the winner of an A/B test campaign."""
    try:
        data = json.loads(request.body)
        campaign_id = int(data.get('campaign_id', 0))
        variant_id = int(data.get('variant_id', 0))
        campaign = Campaign.objects.get(pk=campaign_id, user=request.user)
        variant = CampaignVariant.objects.get(pk=variant_id, campaign=campaign)
        campaign.winner_variant = variant
        campaign.ab_test_status = 'completed'
        campaign.save(update_fields=['winner_variant', 'ab_test_status', 'updated_at'])
        return JsonResponse({'success': True, 'message': f'Variant {variant.label} set as winner.'})
    except (Campaign.DoesNotExist, CampaignVariant.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Campaign or variant not found.'}, status=404)
    except Exception as exc:
        logger.error(f"set_ab_winner error: {exc}")
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)

