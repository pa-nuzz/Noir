"""Campaign analytics views (analytics dashboard, CSV export)."""

import csv
import logging
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Count
from django.db.models.functions import TruncHour
from django.http import HttpResponse
from django.contrib import messages

from apps.campaigns.models import Campaign, EmailClickEvent, EmailEngagement
from apps.workspaces.decorators import require_workspace_permission
from apps.workspaces.query_helpers import filter_by_context

logger = logging.getLogger(__name__)



@login_required
@require_workspace_permission('campaigns', 'read')
def campaign_analytics(request, campaign_id):
    campaign = get_object_or_404(filter_by_context(request, Campaign.objects.all()), id=campaign_id)

    opened_qs = campaign.engagements.filter(opened_at__isnull=False).order_by('-opened_at', 'recipient_email')
    paginator = Paginator(opened_qs, 100)
    opened_page = paginator.get_page(request.GET.get('page'))
    opened_engagements = opened_page.object_list
    top_clicked_links = (
        campaign.click_events
        .values('clicked_url')
        .annotate(total_clicks=Count('id'))
        .order_by('-total_clicks', 'clicked_url')[:10]
    )

    now = timezone.now()
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    start_hour = current_hour - timedelta(hours=23)

    hourly_opens_raw = (
        campaign.engagements
        .filter(opened_at__gte=start_hour, opened_at__lte=now)
        .annotate(hour=TruncHour('opened_at'))
        .values('hour')
        .annotate(total_opens=Count('id'))
        .order_by('hour')
    )
    opens_by_hour = {item['hour']: item['total_opens'] for item in hourly_opens_raw if item['hour'] is not None}

    timeline = []
    max_opens = 1
    for index in range(24):
        hour_point = start_hour + timedelta(hours=index)
        open_count = opens_by_hour.get(hour_point, 0)
        max_opens = max(max_opens, open_count)
        timeline.append({
            'hour_label': timezone.localtime(hour_point).strftime('%H:%M'),
            'opens': open_count,
        })

    for point in timeline:
        point['height_pct'] = round((point['opens'] / max_opens) * 100) if max_opens else 0

    # A/B variant comparison data
    ab_variants = []
    if campaign.is_ab_test:
        for v in campaign.variants.all().order_by('label'):
            v_opens = v.engagements.filter(opened_at__isnull=False).count()
            v_clicks = campaign.click_events.filter(engagement__campaign_variant=v).count()
            ab_variants.append({
                'label': v.label,
                'subject': v.subject,
                'sent': v.sent_count,
                'opens': v_opens,
                'open_rate': v.open_rate,
                'clicks': v_clicks,
                'bounce_rate': v.bounce_rate,
            })

    total_clicks = campaign.click_events.count()
    unique_opens = campaign.open_count
    sent_count = campaign.sent_count
    total_recip = campaign.total_recipients or 1

    context = {
        'campaign': campaign,
        'opened_engagements': opened_engagements,
        'top_clicked_links': top_clicked_links,
        'timeline': timeline,
        'ab_variants': ab_variants,
        'bounce_rate': campaign.bounce_rate,
        'click_through_rate': round(
            (total_clicks / unique_opens) * 100, 1
        ) if unique_opens else 0,
        'delivery_rate': round(
            (sent_count / total_recip) * 100, 1
        ),
        'unsubscribe_count': campaign.unsubscribes.count(),
        'opened_page': opened_page,
    }
    return render(request, 'campaigns/analytics.html', context)



@login_required
@require_workspace_permission('campaigns', 'read')
def campaign_analytics_export_csv(request, campaign_id):
    campaign = get_object_or_404(filter_by_context(request, Campaign.objects.all()), id=campaign_id)
    export_type = (request.GET.get('type') or 'opens').strip().lower()

    if export_type == 'links':
        rows = (
            campaign.click_events
            .values('clicked_url')
            .annotate(total_clicks=Count('id'))
            .order_by('-total_clicks', 'clicked_url')
        )
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="campaign_{campaign.id}_clicked_links.csv"'
        writer = csv.writer(response)
        writer.writerow(['campaign_id', 'campaign_name', 'clicked_url', 'total_clicks'])
        for row in rows:
            writer.writerow([
                campaign.id,
                campaign.name,
                row['clicked_url'],
                row['total_clicks'],
            ])
        return response

    engagements = campaign.engagements.order_by('-opened_at', 'recipient_email')
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="campaign_{campaign.id}_opens.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'campaign_id',
        'campaign_name',
        'recipient_email',
        'sent_at',
        'opened_at',
        'clicked_at',
        'open_count',
        'click_count',
    ])
    for engagement in engagements:
        writer.writerow([
            campaign.id,
            campaign.name,
            engagement.recipient_email,
            engagement.sent_at.isoformat() if engagement.sent_at else '',
            engagement.opened_at.isoformat() if engagement.opened_at else '',
            engagement.clicked_at.isoformat() if engagement.clicked_at else '',
            engagement.open_count,
            engagement.click_count,
        ])
    return response

