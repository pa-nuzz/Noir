"""Campaign tracking views (open/click tracking, unsubscribe, preview)."""

import base64
import logging
from urllib.parse import unquote_plus, urlparse

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib import messages

from apps.campaigns.models import Campaign, EmailClickEvent, EmailEngagement, EmailUnsubscribe
from apps.campaigns.services import update_campaign_unique_open_count
from apps.workspaces.decorators import require_workspace_permission
from apps.workspaces.query_helpers import filter_by_context

logger = logging.getLogger(__name__)



@login_required
@require_workspace_permission('campaigns', 'read')
def campaign_preview(request, campaign_id):
    """Render a full-page preview of a campaign."""
    campaign = get_object_or_404(filter_by_context(request, Campaign.objects.all()), id=campaign_id)
    try:
        html = campaign.render_preview_html()
    except Exception as e:
        logger.exception(f"Campaign preview render failed for {campaign_id}")
        return HttpResponse(f'<html><body><p>Preview render error: {e}</p></body></html>', content_type='text/html', status=500)
    return HttpResponse(html, content_type='text/html')



def campaign_track_open(request, token):
    """Track email opens via tracking pixel.
    
    Called when the 1x1 transparent GIF pixel is loaded in the recipient's email client.
    Records the first open timestamp and increments open counter. Updates campaign's
    unique_open_count if this is the recipient's first open.
    
    Note: Open tracking only works if emails are sent from a public domain. Localhost
    tracking URLs cannot be reached by external email clients, so opens remain untracked
    in development environments.
    
    Args:
        request: The HTTP request object from the tracking pixel load.
        token (str): The unique tracking token for the recipient's email engagement (signed).
    
    Returns:
        HttpResponse: 1x1 transparent GIF pixel with no-cache headers to prevent proxy caching.
    """
    from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
    
    # Try to verify signed token (7-day expiration), but also support legacy tokens
    try:
        signer = TimestampSigner(salt='email-tracking')
        signer.unsign(token, max_age=604800)  # 7 days in seconds
        # Token is valid, proceed
    except (BadSignature, SignatureExpired):
        # Could be legacy token or expired - still try to find engagement
        # This allows backward compatibility
        pass
    
    # Fetch engagement record by tracking token
    tracking = EmailEngagement.objects.filter(tracking_token=token).select_related('campaign').first()
    if tracking:
        now = timezone.now()
        # Detect first open to set opened_at timestamp
        first_open = tracking.opened_at is None
        tracking.open_count = (tracking.open_count or 0) + 1  # Increment open counter
        tracking.last_event_at = now  # Record activity timestamp
        if first_open:
            tracking.opened_at = now  # Set first open time
        tracking.save(update_fields=['open_count', 'last_event_at', 'opened_at'])

        # Update campaign's unique open count if this is first open for recipient
        if first_open:
            update_campaign_unique_open_count(tracking.campaign)
            
            # Trigger campaign.opened webhook
            from apps.webhooks.utils import dispatch_webhook_event
            workspace_id = tracking.campaign.workspace_id
            if workspace_id:
                dispatch_webhook_event(
                    workspace_id=workspace_id,
                    event_type='campaign.opened',
                    payload={
                        'campaign_id': tracking.campaign.id,
                        'campaign_name': tracking.campaign.name,
                        'workspace_id': workspace_id,
                        'recipient_email': tracking.recipient_email,
                        'opened_at': now.isoformat(),
                    }
                )

    # Return 1x1 transparent GIF pixel with no-cache to prevent CDN serving stale data
    pixel_bytes = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==')
    response = HttpResponse(pixel_bytes, content_type='image/gif')
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    return response



def campaign_track_click(request, token):
    """Track email link clicks and redirect to destination.
    
    Called when recipient clicks a tracked link in the email. Records click event
    and redirects to the intended URL. If click is first open, also marks email
    as opened and updates campaign unique_open_count.
    
    Args:
        request: The HTTP request object with 'next' parameter containing target URL.
        token (str): The unique tracking token for the recipient's email engagement.
    
    Returns:
        HttpResponseRedirect: Redirect to the original destination URL, or home if invalid.
    """
    # Extract and validate destination URL from query parameter
    next_url = unquote_plus(request.GET.get('next', '')).strip()
    parsed = urlparse(next_url)
    is_valid_redirect = bool(next_url and parsed.scheme in ('http', 'https') and parsed.netloc)

    # Fetch engagement record by tracking token
    tracking = EmailEngagement.objects.filter(tracking_token=token).select_related('campaign').first()
    if tracking:
        now = timezone.now()
        # Detect first click to set clicked_at timestamp
        first_click = tracking.clicked_at is None
        # Check if this click is also the first time opening the email
        first_open_via_click = tracking.opened_at is None
        tracking.click_count = (tracking.click_count or 0) + 1  # Increment click counter
        tracking.last_event_at = now  # Record activity timestamp
        if first_click:
            tracking.clicked_at = now  # Set first click time
        if first_open_via_click:
            tracking.opened_at = now  # Set first open time (click implies open)
        tracking.save(update_fields=['click_count', 'last_event_at', 'clicked_at', 'opened_at'])

        # Update campaign's unique open count if this is first open via click
        if first_open_via_click:
            update_campaign_unique_open_count(tracking.campaign)

        if is_valid_redirect:
            EmailClickEvent.objects.create(
                campaign=tracking.campaign,
                engagement=tracking,
                clicked_url=next_url,
            )

        # Trigger outbound webhooks
        from apps.webhooks.utils import dispatch_webhook_event
        workspace_id = tracking.campaign.workspace_id
        if workspace_id:
            if first_open_via_click:
                dispatch_webhook_event(
                    workspace_id=workspace_id,
                    event_type='campaign.opened',
                    payload={
                        'campaign_id': tracking.campaign.id,
                        'campaign_name': tracking.campaign.name,
                        'workspace_id': workspace_id,
                        'recipient_email': tracking.recipient_email,
                        'opened_at': now.isoformat(),
                    }
                )
            if first_click:
                dispatch_webhook_event(
                    workspace_id=workspace_id,
                    event_type='campaign.clicked',
                    payload={
                        'campaign_id': tracking.campaign.id,
                        'campaign_name': tracking.campaign.name,
                        'workspace_id': workspace_id,
                        'recipient_email': tracking.recipient_email,
                        'clicked_url': next_url,
                        'clicked_at': now.isoformat(),
                    }
                )

    # Only redirect to valid http/https URLs with proper domain (prevent open-redirect attacks)
    if is_valid_redirect:
        return HttpResponseRedirect(next_url)
    # Invalid URL: redirect to home page
    return redirect('home')



def campaign_unsubscribe(request, token):
    """Handle email unsubscribe — one-click via List-Unsubscribe header or page visit."""
    engagement = EmailEngagement.objects.filter(tracking_token=token).select_related('campaign').first()
    if not engagement:
        messages.error(request, 'Invalid or expired unsubscribe link.')
        return redirect('home')
    email = engagement.recipient_email

    if request.method == 'POST' and email:
        EmailUnsubscribe.objects.get_or_create(
            email=email,
            campaign=engagement.campaign if engagement else None,
        )
        messages.success(request, f'{email} has been unsubscribed from all future campaigns.')
        return redirect('campaigns:campaign_list')

    return render(request, 'campaigns/unsubscribe_confirm.html', {
        'email': email,
        'token': token,
    })

