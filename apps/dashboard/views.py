"""Dashboard views module.

Provides views for rendering the main dashboard with KPIs, email engagement metrics,
campaign statistics, and user profile/settings management.
"""

from datetime import datetime, timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from .models import Notification as NotificationModel

from apps.campaigns.models import Campaign, EmailEngagement
from apps.senders.forms import SenderForm
from apps.senders.models import Sender

from .forms import ChangePasswordForm, ProfileForm
from apps.workspaces.decorators import require_workspace_permission
from apps.workspaces.query_helpers import filter_by_context
from apps.workspaces.onboarding import get_or_create_onboarding


def _safe_count(qs):
    """Return a queryset count, swallowing any DB errors so the dashboard always renders."""
    try:
        return qs.count()
    except Exception:
        return 0


def _safe_list(qs, limit=None):
    """Return a list from a queryset, swallowing errors and limiting results."""
    try:
        if limit is not None:
            return list(qs[:limit])
        return list(qs)
    except Exception:
        return []


def _format_file_size(size):
    """Convert bytes to a human-readable file size string."""
    if not size:
        return ''
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _safe_reverse(name, default='#', **kwargs):
    """reverse() that returns a fallback if the URL is not registered."""
    try:
        return reverse(name, kwargs=kwargs)
    except NoReverseMatch:
        return default


def _safe_model(app_label, model_name):
    """Dynamically import a model class, returning None on failure."""
    try:
        from django.apps import apps
        return apps.get_model(app_label, model_name)
    except Exception:
        return None


@login_required
@require_workspace_permission('workspace', 'read')
def dashboard_view(request):
    """Render the multi-module dashboard command center.

    Aggregates data from all major apps (campaigns, social, content_studio,
    inbox, media_assets, automations, contacts) into a single command center
    view. Every cross-app import is guarded so a missing model never breaks
    the page.

    Args:
        request: The HTTP request object containing the authenticated user.

    Returns:
        HttpResponse: Rendered dashboard template with module-wide context.
    """
    user = request.user
    now = timezone.now()
    today = now.date()
    week_start = today - timedelta(days=6)
    week_start_dt, _ = _day_bounds_static(week_start, now)
    _, tomorrow_dt = _day_bounds_static(today, now)
    prev_week_start = week_start - timedelta(days=7)
    prev_week_end = week_start - timedelta(days=1)
    prev_week_start_dt, _ = _day_bounds_static(prev_week_start, now)
    _, prev_week_end_next_dt = _day_bounds_static(prev_week_end, now)

    # ─── Email Campaign Core ───────────────────────────────────────────
    user_campaigns = Campaign.objects.filter(user=user)
    user_engagements = EmailEngagement.objects.filter(campaign__user=user)
    senders = Sender.objects.filter(user=user, is_active=True)

    recent_campaigns = _safe_list(
        user_campaigns.select_related('sender').order_by('-created_at')[:5]
    )

    status_style_map = {
        'sent': 'bg-emerald-50 text-emerald-600 border-emerald-200',
        'scheduled': 'bg-indigo-50 text-indigo-600 border-indigo-200',
        'sending': 'bg-amber-50 text-amber-700 border-amber-200',
        'draft': 'bg-slate-100 text-slate-700 border-slate-200',
        'failed': 'bg-red-50 text-red-700 border-red-200',
        'paused': 'bg-slate-100 text-slate-700 border-slate-200',
    }

    campaign_rows = []
    for campaign in recent_campaigns:
        campaign_created_at = (
            timezone.localtime(campaign.created_at)
            if timezone.is_aware(campaign.created_at)
            else campaign.created_at
        )
        campaign_rows.append(
            {
                'name': campaign.name,
                'status': campaign.status.title() if campaign.status else 'Draft',
                'status_style': status_style_map.get(
                    campaign.status, status_style_map['draft']
                ),
                'recipients': f"{campaign.total_recipients:,}",
                'open_rate': f"{campaign.open_rate}%" if campaign.sent_count > 0 else '—',
                'date': campaign_created_at.strftime('%b %d, %Y'),
            }
        )

    # ─── BATCH: Weekly engagement aggregates (2 queries vs 6) ─────
    weekly_eng_agg = user_engagements.filter(
        sent_at__gte=week_start_dt, sent_at__lt=tomorrow_dt
    ).aggregate(
        sent=Count('id'),
        opened=Count('id', filter=Q(opened_at__isnull=False)),
        clicked=Count('id', filter=Q(clicked_at__isnull=False)),
    )
    weekly_sent = weekly_eng_agg['sent'] or 0
    weekly_opened = weekly_eng_agg['opened'] or 0
    weekly_clicked = weekly_eng_agg['clicked'] or 0

    prev_weekly_eng_agg = user_engagements.filter(
        sent_at__gte=prev_week_start_dt, sent_at__lt=prev_week_end_next_dt
    ).aggregate(
        sent=Count('id'),
        opened=Count('id', filter=Q(opened_at__isnull=False)),
        clicked=Count('id', filter=Q(clicked_at__isnull=False)),
    )
    prev_weekly_sent = prev_weekly_eng_agg['sent'] or 0
    prev_weekly_opened = prev_weekly_eng_agg['opened'] or 0
    prev_weekly_clicked = prev_weekly_eng_agg['clicked'] or 0

    # ─── BATCH: Weekly campaign aggregates (2 queries vs 4) ─────
    weekly_camp_agg = user_campaigns.filter(
        updated_at__gte=week_start_dt, updated_at__lt=tomorrow_dt
    ).aggregate(
        bounce_sum=Sum('bounce_count'),
        spam_avg=Avg('spam_score', filter=Q(spam_score__isnull=False)),
    )
    weekly_bounced = weekly_camp_agg['bounce_sum'] or 0
    weekly_spam_score = weekly_camp_agg['spam_avg'] or 0

    prev_weekly_camp_agg = user_campaigns.filter(
        updated_at__gte=prev_week_start_dt, updated_at__lt=prev_week_end_next_dt
    ).aggregate(
        spam_avg=Avg('spam_score', filter=Q(spam_score__isnull=False)),
        active=Count('id', filter=Q(status__in=['sending', 'scheduled'])),
    )
    prev_spam_score = prev_weekly_camp_agg['spam_avg'] or 0
    prev_active_campaigns = prev_weekly_camp_agg['active'] or 0

    # ─── All-time totals (2 queries vs 4) ─────
    total_agg = user_engagements.aggregate(
        total_sent=Count('id'),
        total_opened=Count('id', filter=Q(opened_at__isnull=False)),
    )
    total_sent = total_agg['total_sent'] or 0
    total_opened = total_agg['total_opened'] or 0

    today_start_dt, today_end_dt = _day_bounds_static(today, now)
    sent_today = user_engagements.filter(
        sent_at__gte=today_start_dt, sent_at__lt=today_end_dt
    ).count()

    active_campaigns = user_campaigns.filter(
        status__in=['sending', 'scheduled']
    ).count()

    # ─── BATCH: Daily date-bucketed counts (2 queries replaces 28 loop queries) ─────
    fourteen_days_ago = today - timedelta(days=13)
    fourteen_days_ago_dt, _ = _day_bounds_static(fourteen_days_ago, now)
    sent_14d = dict(
        user_engagements.filter(
            sent_at__gte=fourteen_days_ago_dt, sent_at__lt=tomorrow_dt
        )
        .annotate(day=TruncDate('sent_at'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
        .values_list('day', 'count')
    )
    opened_7d = dict(
        user_engagements.filter(
            opened_at__gte=week_start_dt, opened_at__lt=tomorrow_dt,
            opened_at__isnull=False,
        )
        .annotate(day=TruncDate('opened_at'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
        .values_list('day', 'count')
    )

    # ─── fmt_delta helper ─────
    def fmt_delta(current, previous, suffix=''):
        if previous == 0:
            if current == 0:
                return '0' + suffix, 'up'
            return f'+{current}{suffix}', 'up'
        delta = current - previous
        trend = 'up' if delta >= 0 else 'down'
        sign = '+' if delta >= 0 else ''
        return f'{sign}{delta}{suffix}', trend

    weekly_open_rate = round((weekly_opened / weekly_sent * 100), 1) if weekly_sent > 0 else 0
    prev_open_rate = round((prev_weekly_opened / prev_weekly_sent * 100), 1) if prev_weekly_sent > 0 else 0

    sent_delta, sent_trend = fmt_delta(weekly_sent, prev_weekly_sent)
    open_delta, open_trend = fmt_delta(weekly_open_rate, prev_open_rate, '%')
    click_delta, click_trend = fmt_delta(weekly_clicked, prev_weekly_clicked)
    spam_delta, spam_trend = fmt_delta(
        round(weekly_spam_score or 0, 1), round(prev_spam_score or 0, 1)
    )
    active_delta, active_trend = fmt_delta(active_campaigns, prev_active_campaigns)

    kpis = [
        {
            'label': 'Emails Sent (Last 7 Days)',
            'value': f"{weekly_sent:,}",
            'change': sent_delta,
            'trend': sent_trend,
            'period_label': 'vs previous 7 days',
            'icon_bg': 'bg-indigo-50 text-indigo-600',
            'icon_svg': '<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 4h16v16H4z"/><polyline points="22,6 12,13 2,6"/></svg>',
        },
        {
            'label': 'Open Rate (Last 7 Days)',
            'value': f"{weekly_open_rate}%",
            'change': open_delta,
            'trend': open_trend,
            'period_label': 'vs previous 7 days',
            'icon_bg': 'bg-emerald-50 text-emerald-600',
            'icon_svg': '<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="4 14 8 10 12 14 20 6"/></svg>',
        },
        {
            'label': 'Clicks (Last 7 Days)',
            'value': f"{weekly_clicked:,}",
            'change': click_delta,
            'trend': click_trend,
            'period_label': 'vs previous 7 days',
            'icon_bg': 'bg-indigo-50 text-indigo-600',
            'icon_svg': '<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M10 13a5 5 0 007.54.54l3.92-3.91a5 5 0 00-7.07-7.08l-1.77 1.77"/><path d="M14 11a5 5 0 00-7.54-.54L2.54 14.37a5 5 0 107.07 7.08l1.77-1.77"/></svg>',
        },
        {
            'label': 'Active Campaigns',
            'value': str(active_campaigns),
            'change': active_delta,
            'trend': active_trend,
            'period_label': 'vs previous 7 days',
            'icon_bg': 'bg-emerald-50 text-emerald-600',
            'icon_svg': '<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>',
        },
    ]

    # Build chart data from pre-aggregated dicts (0 queries vs 14)
    chart_data = []
    max_sent = 1
    max_open = 1
    day_buckets = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        s = sent_14d.get(day, 0)
        o = opened_7d.get(day, 0)
        max_sent = max(max_sent, s)
        max_open = max(max_open, o)
        day_buckets.append((day, s, o))
    for day, s, o in day_buckets:
        chart_data.append(
            {
                'day': day.strftime('%a'),
                'date_label': day.strftime('%b %d'),
                'sent': s,
                'opens': o,
                'sent_pct': round((s / max_sent) * 100) if max_sent else 0,
                'opens_pct': round((o / max_open) * 100) if max_open else 0,
            }
        )

    senders_count = senders.count()
    max_weekly_value = max(
        weekly_sent, weekly_opened, weekly_bounced, senders_count, weekly_clicked, 1
    )
    deliverability_rate = (
        round(((weekly_sent - weekly_bounced) / weekly_sent) * 100, 1)
        if weekly_sent else 0.0
    )

    weekly_stats = [
        {
            'label': 'Total Sent', 'value': f"{weekly_sent:,}",
            'width': f"{int((weekly_sent / max_weekly_value) * 100)}%",
            'color': 'bg-indigo-500',
        },
        {
            'label': 'Total Opened', 'value': f"{weekly_opened:,}",
            'width': f"{int((weekly_opened / max_weekly_value) * 100)}%",
            'color': 'bg-emerald-400',
        },
        {
            'label': 'Bounced', 'value': f"{weekly_bounced:,}",
            'width': f"{int((weekly_bounced / max_weekly_value) * 100)}%",
            'color': 'bg-rose-400',
        },
        {
            'label': 'Senders', 'value': str(senders_count),
            'width': f"{int((senders_count / max_weekly_value) * 100)}%",
            'color': 'bg-slate-400',
        },
    ]

    # ─── Multi-module data ────────────────────────────────────────────
    SocialAccount = _safe_model('social_accounts', 'SocialAccount')
    SocialPost = _safe_model('social_accounts', 'SocialPost')
    ContentItem = _safe_model('content_studio', 'ContentItem')
    MediaAsset = _safe_model('media_assets', 'MediaAsset')
    EmailDraft = _safe_model('inbox', 'EmailDraft')
    EmailInbox = _safe_model('inbox', 'EmailInbox')
    Workflow = _safe_model('automations', 'Workflow')
    Contact = _safe_model('contacts', 'Contact')

    # KPI strip (cross-module)
    connected_channels = (
        _safe_count(SocialAccount.objects.filter(user=user, is_active=True))
        if SocialAccount else 0
    )
    total_contacts = _safe_count(Contact.objects.filter(contact_list__user=user, is_active=True)) if Contact else 0
    pending_drafts = (
        _safe_count(
            EmailDraft.objects.filter(user=user, status__in=['pending_review', 'edited'])
        )
        if EmailDraft else 0
    )
    scheduled_campaigns = (
        _safe_count(Campaign.objects.filter(user=user, status='scheduled'))
    )
    scheduled_posts = (
        _safe_count(SocialPost.objects.filter(user=user, status='scheduled'))
        if SocialPost else 0
    )
    scheduled_total = scheduled_campaigns + scheduled_posts

    connected_inboxes = (
        _safe_count(EmailInbox.objects.filter(user=user, is_active=True))
        if EmailInbox else 0
    )

    multi_kpis = [
        {
            'label': 'Connected Channels',
            'value': f"{connected_channels}",
            'sub': f"{connected_inboxes} inbox" if connected_inboxes else 'No inbox linked',
            'change': '',
            'trend': 'up',
            'period_label': 'social accounts',
            'icon_bg': 'bg-pink-50 text-pink-600',
            'icon_svg': '<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"/></svg>',
            'href': _safe_reverse('social_accounts:social_hub'),
        },
        {
            'label': 'Total Contacts',
            'value': f"{total_contacts:,}",
            'sub': 'across all lists',
            'change': '',
            'trend': 'up',
            'period_label': 'audience',
            'icon_bg': 'bg-emerald-50 text-emerald-600',
            'icon_svg': '<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"/></svg>',
            'href': _safe_reverse('contacts:list'),
        },
        {
            'label': 'AI Drafts to Review',
            'value': f"{pending_drafts}",
            'sub': 'pending in inbox',
            'change': '',
            'trend': 'up' if pending_drafts else 'up',
            'period_label': 'inbox agent',
            'icon_bg': 'bg-violet-50 text-violet-600',
            'icon_svg': '<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/></svg>',
            'href': _safe_reverse('inbox:dashboard'),
        },
        {
            'label': 'Scheduled Content',
            'value': f"{scheduled_total}",
            'sub': f"{scheduled_campaigns} email · {scheduled_posts} social",
            'change': '',
            'trend': 'up',
            'period_label': 'upcoming',
            'icon_bg': 'bg-amber-50 text-amber-600',
            'icon_svg': '<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 8v4l3 3M3.05 11A9 9 0 1012 3"/></svg>',
            'href': _safe_reverse('campaigns:campaign_list'),
        },
    ]

    # Module quick-entries
    module_cards = [
        {
            'name': 'Email Campaigns',
            'desc': 'Compose, schedule, and track campaigns',
            'icon_bg': 'bg-indigo-50 text-indigo-600',
            'count': _safe_count(Campaign.objects.filter(user=user)),
            'count_label': 'campaigns',
            'href': _safe_reverse('campaigns:campaign_list'),
            'cta': 'Open campaigns',
            'icon_svg': '<svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>',
        },
        {
            'name': 'Social Posts',
            'desc': 'Publish across all connected channels',
            'icon_bg': 'bg-pink-50 text-pink-600',
            'count': _safe_count(SocialPost.objects.filter(user=user)) if SocialPost else 0,
            'count_label': 'posts',
            'href': _safe_reverse('social_accounts:post_list'),
            'cta': 'Open posts',
            'icon_svg': '<svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m9.032 4.026a3 3 0 10-4.5-2.052M3 12h6m9 0h3M3 6h18M3 18h18"/></svg>',
        },
        {
            'name': 'AI Content Studio',
            'desc': 'Generate captions, hashtags, scripts',
            'icon_bg': 'bg-violet-50 text-violet-600',
            'count': _safe_count(ContentItem.objects.filter(user=user)) if ContentItem else 0,
            'count_label': 'items',
            'href': _safe_reverse('content_studio:dashboard'),
            'cta': 'Open studio',
            'icon_svg': '<svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"/></svg>',
        },
        {
            'name': 'AI Email Agent',
            'desc': 'Auto-reply, summarize, and triage inbox',
            'icon_bg': 'bg-emerald-50 text-emerald-600',
            'count': pending_drafts,
            'count_label': 'drafts pending',
            'href': _safe_reverse('inbox:dashboard'),
            'cta': 'Open inbox',
            'icon_svg': '<svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/></svg>',
        },
        {
            'name': 'Media Library',
            'desc': 'Images, video, and assets',
            'icon_bg': 'bg-orange-50 text-orange-600',
            'count': _safe_count(MediaAsset.objects.filter(user=user)) if MediaAsset else 0,
            'count_label': 'assets',
            'href': _safe_reverse('media_assets:library'),
            'cta': 'Open library',
            'icon_svg': '<svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>',
        },
        {
            'name': 'Automations',
            'desc': 'Workflows and triggers',
            'icon_bg': 'bg-rose-50 text-rose-600',
            'count': _safe_count(Workflow.objects.filter(user=user)) if Workflow else 0,
            'count_label': 'workflows',
            'href': _safe_reverse('automations:workflow_list'),
            'cta': 'Open workflows',
            'icon_svg': '<svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>',
        },
    ]

    # Connected channels row
    platform_brand = {
        'facebook':  {'name': 'Facebook',  'icon': 'facebook.webp',  'pill': 'bg-blue-50 text-blue-600 border-blue-100'},
        'instagram': {'name': 'Instagram', 'icon': 'insta.webp',     'pill': 'bg-pink-50 text-pink-600 border-pink-100'},
        'twitter':   {'name': 'X / Twitter','icon': 'x-twitter.svg',  'pill': 'bg-slate-100 text-slate-700 border-slate-200'},
        'linkedin':  {'name': 'LinkedIn',  'icon': 'linkedin.webp',  'pill': 'bg-sky-50 text-sky-700 border-sky-100'},
        'tiktok':    {'name': 'TikTok',    'icon': 'tiktok.svg',     'pill': 'bg-slate-100 text-slate-700 border-slate-200'},
        'youtube':   {'name': 'YouTube',   'icon': 'youtube.webp',   'pill': 'bg-red-50 text-red-600 border-red-100'},
    }

    connected_accounts = (
        _safe_list(
            SocialAccount.objects.filter(user=user, is_active=True)
            .order_by('platform', 'account_name')
        )
        if SocialAccount else []
    )

    all_platforms = ['facebook', 'instagram', 'twitter', 'linkedin', 'tiktok', 'youtube']
    channel_summaries = []
    for plat in all_platforms:
        brand = platform_brand.get(plat, {'name': plat.title(), 'icon': '', 'pill': 'bg-slate-50 text-slate-600 border-slate-100'})
        acc = next((a for a in connected_accounts if a.platform == plat), None)
        channel_summaries.append(
            {
                'platform': plat,
                'name': brand['name'],
                'icon': brand['icon'],
                'pill': brand['pill'],
                'connected': acc is not None,
                'account_name': acc.account_name if acc else None,
            }
        )

    # AI Email Agent — drafts to review
    draft_rows = []
    if EmailDraft:
        for d in _safe_list(
            EmailDraft.objects.filter(user=user, status__in=['pending_review', 'edited'])
            .select_related('thread')
            .order_by('-created_at')[:5]
        ):
            subject = ''
            try:
                subject = d.thread.subject if d.thread else ''
            except Exception:
                subject = ''
            if not subject:
                subject = '(no subject)'
            preview_source = d.edited_body or d.ai_generated_body or ''
            preview = (preview_source[:120] + '…') if len(preview_source) > 120 else preview_source
            urgency = ''
            try:
                urgency = (d.thread.urgency or '').lower() if d.thread else ''
            except Exception:
                urgency = ''
            intent = ''
            try:
                intent = (d.thread.intent or '') if d.thread else ''
            except Exception:
                intent = ''
            draft_rows.append(
                {
                    'id': d.id,
                    'subject': subject[:80],
                    'preview': preview,
                    'status': d.status,
                    'urgency': urgency,
                    'intent': intent,
                    'created_at': d.created_at,
                    'url': _safe_reverse('inbox:dashboard') + '?folder=drafts',
                }
            )

    # Upcoming scheduled content (email + social)
    upcoming_rows = []
    for c in _safe_list(
        Campaign.objects.filter(user=user, status='scheduled', scheduled_at__isnull=False)
        .order_by('scheduled_at')[:5]
    ):
        upcoming_rows.append(
            {
                'kind': 'email',
                'title': c.name,
                'when': c.scheduled_at,
                'pill': 'bg-indigo-50 text-indigo-600 border-indigo-100',
                'pill_label': 'Email',
                'icon_svg': '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>',
                'url': _safe_reverse('campaigns:campaign_list'),
            }
        )
    if SocialPost:
        for p in _safe_list(
            SocialPost.objects.filter(user=user, status='scheduled', scheduled_at__isnull=False)
            .order_by('scheduled_at')[:5]
        ):
            brand = platform_brand.get(p.platform, {'name': p.platform.title()})
            upcoming_rows.append(
                {
                    'kind': 'social',
                    'title': (p.content or '(no caption)')[:60],
                    'when': p.scheduled_at,
                    'pill': 'bg-pink-50 text-pink-600 border-pink-100',
                    'pill_label': brand['name'],
                    'icon_svg': '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342"/></svg>',
                    'url': _safe_reverse('social_accounts:post_list'),
                }
            )
    upcoming_rows.sort(key=lambda r: r['when'] or now)
    upcoming_rows = upcoming_rows[:6]

    # Recent activity feed — mix of recent items
    activity = []
    for c in _safe_list(
        Campaign.objects.filter(user=user).order_by('-updated_at')[:4]
    ):
        activity.append(
            {
                'tone': 'indigo' if c.status == 'sent' else ('emerald' if c.status == 'scheduled' else 'slate'),
                'icon_svg': '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>',
                'title': f"Email campaign: {c.name}",
                'sub': f"Status: {c.status.title() if c.status else 'Draft'}",
                'when': c.updated_at,
                'url': _safe_reverse('campaigns:campaign_list'),
            }
        )
    if SocialPost:
        for p in _safe_list(
            SocialPost.objects.filter(user=user).order_by('-updated_at')[:4]
        ):
            brand = platform_brand.get(p.platform, {'name': p.platform.title()})
            activity.append(
                {
                    'tone': 'pink',
                    'icon_svg': '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/></svg>',
                    'title': f"Social post on {brand['name']}",
                    'sub': f"{(p.content or '(no caption)')[:60]}",
                    'when': p.updated_at,
                    'url': _safe_reverse('social_accounts:post_list'),
                }
            )
    if ContentItem:
        for it in _safe_list(
            ContentItem.objects.filter(user=user).order_by('-created_at')[:4]
        ):
            activity.append(
                {
                    'tone': 'violet',
                    'icon_svg': '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M5 3v4M3 5h4M6 17v4m-2-2h4"/></svg>',
                    'title': f"AI generated: {it.title}",
                    'sub': f"Type: {it.get_content_type_display() if hasattr(it, 'get_content_type_display') else it.content_type}",
                    'when': it.created_at,
                    'url': _safe_reverse('content_studio:dashboard'),
                }
            )

    activity.sort(key=lambda r: r['when'] or now, reverse=True)
    activity = activity[:8]

    # Audience health + 7-day growth sparkline (TruncDate, 1-2 queries vs 9)
    contacts_total = total_contacts
    contacts_new_this_week = 0
    contacts_unsubscribed = 0
    growth_buckets = [0] * 7
    if Contact:
        try:
            contacts_unsubscribed = Contact.objects.filter(
                unsubscribed=True, unsubscribed_at__gte=week_start_dt
            ).count()
            contacts_growth = dict(
                Contact.objects.filter(
                    is_active=True, created_at__gte=week_start_dt, created_at__lt=tomorrow_dt
                )
                .annotate(day=TruncDate('created_at'))
                .values('day')
                .annotate(count=Count('id'))
                .order_by('day')
                .values_list('day', 'count')
            )
            contacts_new_this_week = sum(contacts_growth.values()) if contacts_growth else 0
            growth_buckets = [contacts_growth.get(today - timedelta(days=offset), 0) for offset in range(6, -1, -1)]
        except Exception:
            pass
    growth_max = max(growth_buckets) or 1
    growth_pcts = [int((v / growth_max) * 100) for v in growth_buckets]

    # Multi-channel chart — 14-day TruncDate aggregations (3 queries vs 42)
    social_published_14d = {}
    ai_created_14d = {}
    if SocialPost:
        social_published_14d = dict(
            SocialPost.objects.filter(
                user=user, status='published',
                published_at__gte=fourteen_days_ago_dt, published_at__lt=tomorrow_dt,
            )
            .annotate(day=TruncDate('published_at'))
            .values('day')
            .annotate(count=Count('id'))
            .order_by('day')
            .values_list('day', 'count')
        )
    if ContentItem:
        ai_created_14d = dict(
            ContentItem.objects.filter(
                user=user,
                created_at__gte=fourteen_days_ago_dt, created_at__lt=tomorrow_dt,
            )
            .annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(count=Count('id'))
            .order_by('day')
            .values_list('day', 'count')
        )

    multi_chart_buckets = {'email': [], 'social': [], 'ai': []}
    for offset in range(13, -1, -1):
        day = today - timedelta(days=offset)
        label = day.strftime('%b %d')
        multi_chart_buckets['email'].append({'label': label, 'value': sent_14d.get(day, 0), 'day': day.strftime('%a')})
        multi_chart_buckets['social'].append({'label': label, 'value': social_published_14d.get(day, 0), 'day': day.strftime('%a')})
        multi_chart_buckets['ai'].append({'label': label, 'value': ai_created_14d.get(day, 0), 'day': day.strftime('%a')})

    for channel_data in multi_chart_buckets.values():
        m = max([c['value'] for c in channel_data] + [1])
        for c in channel_data:
            c['pct'] = int((c['value'] / m) * 100) if m else 0

    multi_chart = [
        {'key': 'email', 'label': 'Emails sent', 'color': 'bg-indigo-500', 'data': multi_chart_buckets['email']},
        {'key': 'social', 'label': 'Posts published', 'color': 'bg-pink-500', 'data': multi_chart_buckets['social']},
        {'key': 'ai', 'label': 'AI items generated', 'color': 'bg-violet-500', 'data': multi_chart_buckets['ai']},
    ]

    # ─── Context assembly ─────────────────────────────────────────────
    context = {
        # Existing email-campaign context
        'kpis': kpis,
        'chart_data': chart_data,
        'weekly_stats': weekly_stats,
        'campaigns': campaign_rows,
        'inbox_rate': deliverability_rate,
        'total_sent': total_sent,
        'total_opened': total_opened,
        'weekly_clicked': weekly_clicked,
        'sent_today': sent_today,
        'weekly_spam_score': round(weekly_spam_score, 1) if weekly_spam_score else 0,
        'spam_delta': spam_delta,
        'spam_trend': spam_trend,
        'weekly_clicked_width': int((weekly_clicked / max_weekly_value) * 100) if max_weekly_value else 0,

        # Multi-module context
        'multi_kpis': multi_kpis,
        'module_cards': module_cards,
        'channel_summaries': channel_summaries,
        'connected_accounts': connected_accounts,
        'draft_rows': draft_rows,
        'upcoming_rows': upcoming_rows,
        'activity': activity,
        'multi_chart': multi_chart,
        'audience': {
            'total': contacts_total,
            'new_week': contacts_new_this_week,
            'unsubscribed_week': contacts_unsubscribed,
            'growth_pcts': growth_pcts,
        },

        # Quick actions
        'quick_actions': [
            {
                'label': 'New Campaign',
                'href': _safe_reverse('campaigns:campaign_create'),
                'icon_svg': '<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4"/></svg>',
            },
            {
                'label': 'New Post',
                'href': _safe_reverse('social_accounts:post_create'),
                'icon_svg': '<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4"/></svg>',
            },
            {
                'label': 'Generate Content',
                'href': _safe_reverse('content_studio:generate'),
                'icon_svg': '<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 4v16m8-8H4"/></svg>',
            },
        ],

        # Onboarding
        'onboarding': get_or_create_onboarding(request.tenant) if hasattr(request, 'tenant') and request.tenant else None,
    }
    return render(request, 'dashboard/home.html', context)


def _safe_aggregate(qs, **kwargs):
    try:
        result = qs.aggregate(**kwargs)
        return result
    except Exception:
        return {k: 0 for k in kwargs}


@login_required
@require_workspace_permission('workspace', 'read')
def platform_analytics(request):
    user = request.user
    now = timezone.now()
    today = now.date()
    week_start = today - timedelta(days=6)
    week_start_dt, _ = _day_bounds_static(week_start, now)
    _, tomorrow_dt = _day_bounds_static(today, now)
    prev_week_start = week_start - timedelta(days=7)
    prev_week_end = week_start - timedelta(days=1)
    prev_week_start_dt, _ = _day_bounds_static(prev_week_start, now)
    _, prev_week_end_next_dt = _day_bounds_static(prev_week_end, now)
    month_start = today - timedelta(days=30)
    month_start_dt, _ = _day_bounds_static(month_start, now)

    user_campaigns = Campaign.objects.filter(user=user)
    user_engagements = EmailEngagement.objects.filter(campaign__user=user)

    SocialAccount = _safe_model('social_accounts', 'SocialAccount')
    SocialPost = _safe_model('social_accounts', 'SocialPost')
    SocialAnalytics = _safe_model('social_accounts', 'SocialAnalytics')
    ContentItem = _safe_model('content_studio', 'ContentItem')
    Contact = _safe_model('contacts', 'Contact')
    Workflow = _safe_model('automations', 'Workflow')
    WorkflowEnrollment = _safe_model('automations', 'WorkflowEnrollment')
    EmailDraft = _safe_model('inbox', 'EmailDraft')
    EmailInbox = _safe_model('inbox', 'EmailInbox')
    MediaAsset = _safe_model('media_assets', 'MediaAsset')
    WorkspaceBilling = _safe_model('billing', 'WorkspaceBilling')
    StoragePlan = _safe_model('billing', 'StoragePlan')

    # ─── EMAIL ANALYTICS ────────────────────────────────────────────
    total_campaigns = _safe_count(user_campaigns)
    total_sent = _safe_count(user_engagements)
    total_opened = _safe_count(user_engagements.filter(opened_at__isnull=False))
    total_clicked = _safe_count(user_engagements.filter(clicked_at__isnull=False))
    total_bounced = _safe_aggregate(user_campaigns, total=Sum('bounce_count'))['total'] or 0
    total_unsubscribes = _safe_count(
        _safe_model('campaigns', 'EmailUnsubscribe').objects.filter(campaign__user=user)
        if _safe_model('campaigns', 'EmailUnsubscribe') else []
    )

    weekly_sent = _safe_count(user_engagements.filter(sent_at__gte=week_start_dt, sent_at__lt=tomorrow_dt))
    weekly_opened = _safe_count(user_engagements.filter(opened_at__gte=week_start_dt, opened_at__lt=tomorrow_dt))
    weekly_clicked = _safe_count(user_engagements.filter(clicked_at__gte=week_start_dt, clicked_at__lt=tomorrow_dt))
    weekly_bounced = _safe_aggregate(
        user_campaigns.filter(updated_at__gte=week_start_dt, updated_at__lt=tomorrow_dt),
        total=Sum('bounce_count')
    )['total'] or 0

    total_open_rate = round((total_opened / total_sent * 100), 1) if total_sent else 0
    total_click_rate = round((total_clicked / total_sent * 100), 1) if total_sent else 0
    total_bounce_rate = round((total_bounced / total_sent * 100), 1) if total_sent else 0
    total_deliverability = round(((total_sent - total_bounced) / total_sent * 100), 1) if total_sent else 0

    sent_campaigns = _safe_count(user_campaigns.filter(status='sent'))
    avg_spam_score = _safe_aggregate(
        user_campaigns.filter(spam_score__isnull=False),
        avg=Avg('spam_score')
    )['avg'] or 0

    # 30-day email chart data
    email_chart = []
    for offset in range(29, -1, -1):
        day = today - timedelta(days=offset)
        day_start, day_end = _day_bounds_static(day, now)
        sent = _safe_count(user_engagements.filter(sent_at__gte=day_start, sent_at__lt=day_end))
        opened = _safe_count(user_engagements.filter(opened_at__gte=day_start, opened_at__lt=day_end))
        email_chart.append({
            'date': day.strftime('%b %d'),
            'sent': sent,
            'opened': opened,
        })

    # ─── AUDIENCE / CONTACT ANALYTICS ──────────────────────────────
    base_contacts = Contact.objects.filter(contact_list__user=user) if Contact else Contact.objects.none()
    total_contacts = _safe_count(base_contacts.filter(is_active=True)) if Contact else 0
    contacts_new_30d = _safe_count(
        base_contacts.filter(is_active=True, created_at__gte=month_start_dt)
    ) if Contact else 0
    contacts_unsubscribed = _safe_count(
        base_contacts.filter(unsubscribed=True)
    ) if Contact else 0
    contacts_suppressed = _safe_count(
        base_contacts.filter(is_suppressed=True)
    ) if Contact else 0
    contacts_gdpr_consent = _safe_count(
        base_contacts.filter(gdpr_consent=True)
    ) if Contact else 0
    contact_growth_rate = round((contacts_new_30d / max(total_contacts, 1)) * 100, 1)

    # ─── SOCIAL MEDIA ANALYTICS ────────────────────────────────────
    total_social_accounts = _safe_count(SocialAccount.objects.filter(user=user, is_active=True)) if SocialAccount else 0
    total_social_posts = _safe_count(SocialPost.objects.filter(user=user)) if SocialPost else 0
    social_published = _safe_count(SocialPost.objects.filter(user=user, status='published')) if SocialPost else 0

    total_impressions = 0
    total_reach = 0
    total_engagement = 0
    total_followers_gained = 0
    platform_breakdown = []
    if SocialAnalytics:
        all_analytics = SocialAnalytics.objects.filter(post__user=user)
        agg = _safe_aggregate(
            all_analytics,
            impressions=Sum('impressions'),
            reach=Sum('reach'),
            likes=Sum('likes'),
            shares=Sum('shares'),
            comments=Sum('comments'),
            clicks=Sum('clicks'),
            followers_gained=Sum('followers_gained'),
            followers_lost=Sum('followers_lost'),
        )
        total_impressions = agg.get('impressions') or 0
        total_reach = agg.get('reach') or 0
        total_likes = agg.get('likes') or 0
        total_shares = agg.get('shares') or 0
        total_comments = agg.get('comments') or 0
        total_clicks = agg.get('clicks') or 0
        total_followers_gained = agg.get('followers_gained') or 0
        total_followers_lost = agg.get('followers_lost') or 0
        total_engagement = total_likes + total_shares + total_comments + total_clicks
        avg_engagement_rate = round((total_engagement / max(total_impressions, 1)) * 100, 2)

        try:
            platform_data = (
                all_analytics.values('post__platform')
                .annotate(
                    imp=Sum('impressions'),
                    rea=Sum('reach'),
                    eng=Sum('likes') + Sum('shares') + Sum('comments') + Sum('clicks'),
                )
                .order_by('-imp')
            )
            for p in platform_data:
                platform_breakdown.append({
                    'platform': p['post__platform'] or 'unknown',
                    'impressions': p['imp'] or 0,
                    'reach': p['rea'] or 0,
                    'engagement': p['eng'] or 0,
                    'engagement_rate': round((p['eng'] or 0) / max(p['imp'] or 1, 1) * 100, 1),
                })
        except Exception:
            pass
    else:
        total_likes = total_shares = total_comments = total_clicks = 0
        total_followers_lost = 0
        avg_engagement_rate = 0

    # ─── CONTENT STUDIO ANALYTICS ──────────────────────────────────
    total_content = _safe_count(ContentItem.objects.filter(user=user)) if ContentItem else 0
    content_drafts = _safe_count(ContentItem.objects.filter(user=user, status='draft')) if ContentItem else 0
    content_approved = _safe_count(ContentItem.objects.filter(user=user, status='approved')) if ContentItem else 0
    content_published = _safe_count(ContentItem.objects.filter(user=user, status='published')) if ContentItem else 0

    # ─── AUTOMATION ANALYTICS ──────────────────────────────────────
    total_workflows = _safe_count(Workflow.objects.filter(user=user)) if Workflow else 0
    active_enrollments = 0
    completed_enrollments = 0
    if WorkflowEnrollment:
        active_enrollments = _safe_count(
            WorkflowEnrollment.objects.filter(workflow__user=user, status='active')
        )
        completed_enrollments = _safe_count(
            WorkflowEnrollment.objects.filter(workflow__user=user, status='completed')
        )

    # ─── INBOX / AI AGENT ANALYTICS ────────────────────────────────
    total_inboxes = _safe_count(EmailInbox.objects.filter(user=user, is_active=True)) if EmailInbox else 0
    pending_drafts = _safe_count(
        EmailDraft.objects.filter(user=user, status__in=['pending_review', 'edited'])
    ) if EmailDraft else 0
    approved_drafts = _safe_count(
        EmailDraft.objects.filter(user=user, status='approved')
    ) if EmailDraft else 0

    # ─── MEDIA ASSET ANALYTICS ─────────────────────────────────────
    total_media = _safe_count(MediaAsset.objects.filter(user=user)) if MediaAsset else 0
    media_images = 0
    media_videos = 0
    total_file_size_mb = 0
    if MediaAsset:
        media_images = _safe_count(MediaAsset.objects.filter(user=user, file_type='image'))
        media_videos = _safe_count(MediaAsset.objects.filter(user=user, file_type='video'))
        size_agg = _safe_aggregate(
            MediaAsset.objects.filter(user=user),
            total_size=Sum('file_size')
        )
        total_file_size_mb = round((size_agg.get('total_size') or 0) / (1024 * 1024), 2)

    # ─── BILLING / REVENUE ANALYTICS ───────────────────────────────
    monthly_storage_cost = 0
    storage_used_mb = 0
    storage_savings = 0
    if WorkspaceBilling:
        try:
            from apps.workspaces.models import get_or_create_personal_workspace
            ws = get_or_create_personal_workspace(user)
            billing = WorkspaceBilling.objects.filter(workspace=ws).first()
            if billing:
                monthly_storage_cost = float(billing.monthly_cost_estimate)
                storage_used_mb = billing.storage_used_mb

            from apps.workspaces.models import WorkspaceStorageConfig
            config = WorkspaceStorageConfig.objects.filter(workspace=ws).first()
            if config and config.backend != 'local':
                storage_savings = round(storage_used_mb / 1024 * 10, 2)
                monthly_storage_cost = 0
        except Exception:
            pass

    # ─── ESTIMATED BUSINESS VALUE ──────────────────────────────────
    cost_per_email_send = 0.50
    estimated_email_value = round(total_sent * cost_per_email_send, 2)
    cost_per_click = 5.00
    estimated_click_value = round(total_clicked * cost_per_click, 2)
    value_per_lead = 50.00
    estimated_lead_value = round(contacts_new_30d * value_per_lead, 2)
    social_media_value = round(total_impressions * 0.02, 2)

    total_estimated_value = round(
        estimated_email_value + estimated_click_value + estimated_lead_value + social_media_value, 2
    )
    total_cost_savings = round(storage_savings, 2)

    # ─── GROWTH TRENDS ─────────────────────────────────────────────
    prev_weekly_sent = _safe_count(
        user_engagements.filter(sent_at__gte=prev_week_start_dt, sent_at__lt=prev_week_end_next_dt)
    )
    prev_weekly_opened = _safe_count(
        user_engagements.filter(opened_at__gte=prev_week_start_dt, opened_at__lt=prev_week_end_next_dt)
    )
    prev_weekly_clicked = _safe_count(
        user_engagements.filter(clicked_at__gte=prev_week_start_dt, clicked_at__lt=prev_week_end_next_dt)
    )

    def pct_change(current, previous):
        if previous == 0:
            return 100 if current > 0 else 0
        return round(((current - previous) / previous) * 100, 1)

    sent_trend = pct_change(weekly_sent, prev_weekly_sent)
    open_trend = pct_change(weekly_opened, prev_weekly_opened)
    click_trend = pct_change(weekly_clicked, prev_weekly_clicked)

    context = {
        'total_campaigns': total_campaigns,
        'total_sent': total_sent,
        'total_opened': total_opened,
        'total_clicked': total_clicked,
        'total_bounced': total_bounced,
        'total_unsubscribes': total_unsubscribes,
        'total_open_rate': total_open_rate,
        'total_click_rate': total_click_rate,
        'total_bounce_rate': total_bounce_rate,
        'total_deliverability': total_deliverability,
        'sent_campaigns': sent_campaigns,
        'avg_spam_score': round(avg_spam_score, 2),
        'email_chart': email_chart,

        'total_contacts': total_contacts,
        'contacts_new_30d': contacts_new_30d,
        'contacts_unsubscribed': contacts_unsubscribed,
        'contacts_suppressed': contacts_suppressed,
        'contacts_gdpr_consent': contacts_gdpr_consent,
        'contact_growth_rate': contact_growth_rate,

        'total_social_accounts': total_social_accounts,
        'total_social_posts': total_social_posts,
        'social_published': social_published,
        'total_impressions': total_impressions,
        'total_reach': total_reach,
        'total_likes': total_likes,
        'total_shares': total_shares,
        'total_comments': total_comments,
        'total_clicks': total_clicks,
        'total_followers_gained': total_followers_gained,
        'total_followers_lost': total_followers_lost,
        'total_engagement': total_engagement,
        'avg_engagement_rate': avg_engagement_rate,
        'platform_breakdown': platform_breakdown,

        'total_content': total_content,
        'content_drafts': content_drafts,
        'content_approved': content_approved,
        'content_published': content_published,

        'total_workflows': total_workflows,
        'active_enrollments': active_enrollments,
        'completed_enrollments': completed_enrollments,

        'total_inboxes': total_inboxes,
        'pending_drafts': pending_drafts,
        'approved_drafts': approved_drafts,

        'total_media': total_media,
        'media_images': media_images,
        'media_videos': media_videos,
        'total_file_size_mb': total_file_size_mb,

        'monthly_storage_cost': monthly_storage_cost,
        'storage_used_mb': storage_used_mb,
        'storage_savings': storage_savings,

        'estimated_email_value': estimated_email_value,
        'estimated_click_value': estimated_click_value,
        'estimated_lead_value': estimated_lead_value,
        'social_media_value': social_media_value,
        'total_estimated_value': total_estimated_value,
        'total_cost_savings': total_cost_savings,

        'weekly_sent': weekly_sent,
        'weekly_opened': weekly_opened,
        'weekly_clicked': weekly_clicked,
        'sent_trend': sent_trend,
        'open_trend': open_trend,
        'click_trend': click_trend,
    }
    return render(request, 'dashboard/platform_analytics.html', context)


def _day_bounds_static(day, now_value):
    """Timezone-safe start and end datetime for a calendar day.

    Helper extracted so the dashboard view stays linear. Mirrors the logic
    in the original day_bounds() — extracted into a free function so we
    don't rely on a closure.
    """
    start = datetime.combine(day, datetime.min.time())
    end = start + timedelta(days=1)
    timezone_aware = timezone.is_aware(now_value)
    if timezone_aware:
        tz = timezone.get_current_timezone()
        start = timezone.make_aware(start, tz)
        end = timezone.make_aware(end, tz)
    return start, end


@login_required
@require_workspace_permission('workspace', 'edit')
def settings_view(request):
    """Manage sender SMTP profiles and email credentials.

    Allows users to add, update, and delete SMTP sender profiles for outgoing emails.
    Email normalization and deduplication prevent duplicate sender configurations.

    Args:
        request: The HTTP request object containing the authenticated user.

    Returns:
        HttpResponse: Rendered settings template with senders list and form.
    """
    senders = filter_by_context(request, Sender.objects.all())
    sender_form = SenderForm()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_sender':
            sender_form = SenderForm(request.POST)

            if sender_form.is_valid():
                candidate = sender_form.save(commit=False)
                normalized_email = (candidate.from_email or '').strip().lower()
                existing_sender = Sender.objects.filter(
                    user=request.user,
                    from_email__iexact=normalized_email,
                ).first()

                if existing_sender:
                    existing_sender.display_name = candidate.display_name
                    existing_sender.from_email = normalized_email
                    existing_sender.provider = candidate.provider
                    existing_sender.smtp_host = candidate.smtp_host
                    existing_sender.smtp_port = candidate.smtp_port
                    existing_sender.username = candidate.username
                    existing_sender.use_tls = candidate.use_tls
                    existing_sender.daily_limit = candidate.daily_limit
                    existing_sender.send_delay_seconds = candidate.send_delay_seconds
                    existing_sender.is_active = True

                    raw_password = sender_form.cleaned_data.get('smtp_password')
                    if raw_password:
                        existing_sender.set_password(raw_password)

                    existing_sender.save()
                    messages.success(request, 'Sender already existed and was updated successfully.')
                else:
                    sender = candidate
                    sender.user = request.user
                    sender.from_email = normalized_email
                    sender.is_active = True
                    sender.is_verified = True
                    raw_password = sender_form.cleaned_data['smtp_password']
                    sender.set_password(raw_password)
                    sender.save()
                    messages.success(request, 'Sender added successfully.')

                return redirect('dashboard:settings')

            messages.error(request, 'Please correct the errors below.')

        elif action == 'delete_sender':
            sender_id = request.POST.get('sender_id')
            filter_by_context(request, Sender.objects.filter(id=sender_id)).delete()
            messages.success(request, 'Sender removed.')
            return redirect('dashboard:settings')

    from datetime import date, timedelta
    today = date.today()

    # Aggregate real delivery metrics per sender (last 6 months)
    six_months_ago = today - timedelta(days=180)
    sender_metrics_qs = (
        Campaign.objects.filter(sender__in=senders, created_at__gte=six_months_ago)
        .values('sender_id')
        .annotate(
            total_sent=Sum('sent_count'),
            total_open=Sum('open_count'),
            total_bounce=Sum('bounce_count'),
            campaign_count=Count('id'),
            recent_sent=Sum('sent_count', filter=Q(created_at__gte=today - timedelta(days=7))),
        )
    )
    sender_metrics = {m['sender_id']: m for m in sender_metrics_qs}

    sender_campaign_counts = dict(
        Campaign.objects.filter(sender__in=senders)
        .values('sender_id')
        .annotate(count=Count('id'))
        .values_list('sender_id', 'count')
    )

    sender_reputations = {}
    for s in senders:
        m = sender_metrics.get(s.id, {})
        total_sent = m.get('total_sent', 0) or 0
        total_open = m.get('total_open', 0) or 0
        total_bounce = m.get('total_bounce', 0) or 0
        campaign_count = m.get('campaign_count', 0) or 0
        recent_sent = m.get('recent_sent', 0) or 0

        score = 0

        # 1. Verified sender (SMTP test passed) — 10 pts
        if s.is_verified:
            score += 10

        # 2. Campaign volume (proven sending experience) — up to 15 pts
        if campaign_count >= 10:
            score += 15
        elif campaign_count >= 5:
            score += 10
        elif campaign_count >= 1:
            score += 5

        # 3. Bounce rate (lower is better) — up to 30 pts
        if total_sent > 0:
            bounce_rate = total_bounce / total_sent * 100
            if bounce_rate < 1:
                score += 30
            elif bounce_rate < 3:
                score += 25
            elif bounce_rate < 5:
                score += 15
            elif bounce_rate < 10:
                score += 5

        # 4. Open rate (higher is better) — up to 25 pts
        if total_sent > 0:
            open_rate = total_open / total_sent * 100
            if open_rate >= 30:
                score += 25
            elif open_rate >= 20:
                score += 20
            elif open_rate >= 10:
                score += 12
            elif open_rate >= 5:
                score += 5

        # 5. Recent activity — up to 20 pts
        if recent_sent > 0:
            score += 20
        elif campaign_count > 0:
            score += 10

        sender_reputations[s.id] = {
            'score': min(score, 100),
            'weekly_limit': (s.daily_limit or 500) * 7,
            'weekly_used': (s.emails_sent_today or 0) * 7,
        }

    context = {
        'senders': senders,
        'sender_form': sender_form,
        'sender_reputations': sender_reputations,
        'sender_campaign_counts': sender_campaign_counts,
    }
    return render(request, 'dashboard/settings.html', context)


@login_required
@require_workspace_permission('workspace', 'read')
def profile_view(request):
    """Manage user profile and password settings.

    Allows users to update avatar, company info, and change their password.
    Also displays total sent campaigns count.

    Args:
        request: The HTTP request object containing the authenticated user.

    Returns:
        HttpResponse: Rendered profile template with user forms and campaign count.
    """
    profile_form = ProfileForm(instance=request.user)
    password_form = ChangePasswordForm(request.user)
    total_campaigns = filter_by_context(request, Campaign.objects.filter(status='sent')).count()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_profile':
            profile_form = ProfileForm(request.POST, request.FILES, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Profile updated.')
                return redirect('dashboard:dashboard')

        elif action == 'change_password':
            password_form = ChangePasswordForm(request.user, request.POST)
            if password_form.is_valid():
                password_form.save()
                messages.success(request, 'Password changed. Please log in again.')
                return redirect('accounts:login')

    return render(request, 'dashboard/profile.html', {
        'profile_form': profile_form,
        'password_form': password_form,
        'total_campaigns': total_campaigns,
    })


@login_required
@require_workspace_permission('workspace', 'read')
def clear_notifications_view(request):
    """Clear dashboard notifications via AJAX.

    Marks all persistent notifications as read and records dismissal timestamp
    for session-based notifications.

    Args:
        request: The HTTP request object with POST method.

    Returns:
        JsonResponse: JSON response with status confirmation.
    """
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Method not allowed'}, status=405)

    NotificationModel.objects.filter(user=request.user, is_read=False).update(is_read=True)
    request.session['dashboard_notifications_dismissed_at'] = timezone.now().isoformat()
    request.session.modified = True
    return JsonResponse({'ok': True})


@login_required
def check_notifications_view(request):
    since_id = request.GET.get('since_id')
    qs = NotificationModel.objects.filter(user=request.user, is_read=False)
    if since_id:
        try:
            qs = qs.filter(id__gt=int(since_id))
        except (ValueError, TypeError):
            pass
    count = NotificationModel.objects.filter(user=request.user, is_read=False).count()
    items = []
    for n in qs.order_by('-created_at')[:5]:
        items.append({
            'id': f'db-{n.id}',
            'title': n.title,
            'message': n.message,
            'tone': n.tone,
            'url': n.url,
        })
    return JsonResponse({'count': count, 'notifications': items})


@login_required
@require_workspace_permission('workspace', 'read')
def templates_view(request):
    """Redirect to the campaigns email template manager."""
    from django.shortcuts import redirect
    try:
        from django.urls import reverse
        return redirect(reverse('campaigns:template_list'))
    except Exception:
        return redirect('dashboard:dashboard')


@login_required
@require_workspace_permission('workspace', 'read')
def social_content_hub(request):
    """Social & Content Command Center — unified workspace for social posts, calendar, and media.

    Aggregates data from social_accounts, content_studio, and media_assets into
    a single tabbed command center view.

    Args:
        request: The HTTP request object containing the authenticated user.

    Returns:
        HttpResponse: Rendered social content hub template.
    """
    user = request.user
    now = timezone.now()
    today = now.date()

    # Import models safely
    SocialPost = _safe_model('social_accounts', 'SocialPost')
    MediaAsset = _safe_model('media_assets', 'MediaAsset')

    # ─── Posts & Publishing data ──────────────────────────────────────
    posts = []
    if SocialPost:
        platform_names = {
            'linkedin': 'LinkedIn',
            'twitter': 'X',
            'instagram': 'Instagram',
            'facebook': 'Facebook',
            'tiktok': 'TikTok',
            'youtube': 'YouTube',
        }
        for p in _safe_list(
            SocialPost.objects.filter(user=user)
            .order_by('-scheduled_at', '-created_at')[:50]
        ):
            sched_display = ''
            if p.scheduled_at:
                sched_dt = (
                    timezone.localtime(p.scheduled_at)
                    if timezone.is_aware(p.scheduled_at)
                    else p.scheduled_at
                )
                sched_display = sched_dt.strftime('%b %d, %Y at %I:%M %p')

            content_src = p.content or ''
            content_preview = (content_src[:200] + '...') if len(content_src) > 200 else content_src

            posts.append({
                'platform': p.platform or 'twitter',
                'platform_display': platform_names.get(p.platform, p.platform or 'X'),
                'content_preview': content_preview or '(no content)',
                'status': p.status or 'draft',
                'status_display': (p.status or 'draft').title(),
                'scheduled_display': sched_display,
            })

    # ─── Calendar data ───────────────────────────────────────────────
    year = request.GET.get('year')
    month = request.GET.get('month')
    try:
        cal_year = int(year) if year else today.year
        cal_month = int(month) if month else today.month
    except (ValueError, TypeError):
        cal_year = today.year
        cal_month = today.month

    import calendar as cal_module
    cal = cal_module.Calendar(firstweekday=0)
    month_days = cal.monthdayscalendar(cal_year, cal_month)

    month_names = [
        '', 'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ]
    calendar_month_label = f"{month_names[cal_month]} {cal_year}"

    # Gather scheduled events for this month
    events_by_date = {}
    if SocialPost:
        month_start = datetime(cal_year, cal_month, 1)
        if cal_month == 12:
            month_end = datetime(cal_year + 1, 1, 1)
        else:
            month_end = datetime(cal_year, cal_month + 1, 1)

        tz = timezone.get_current_timezone()
        month_start_dt = timezone.make_aware(month_start, tz) if not timezone.is_aware(month_start) else month_start
        month_end_dt = timezone.make_aware(month_end, tz) if not timezone.is_aware(month_end) else month_end

        for p in _safe_list(
            SocialPost.objects.filter(
                user=user,
                scheduled_at__gte=month_start_dt,
                scheduled_at__lt=month_end_dt,
            )
        ):
            sched = p.scheduled_at
            if timezone.is_aware(sched):
                sched = timezone.localtime(sched)
            day_key = sched.date().day
            label = (p.platform or 'post')[:4].upper()
            events_by_date.setdefault(day_key, []).append({
                'kind': 'social',
                'label': label,
                'title': (p.content or 'Post')[:40],
            })

    calendar_days = []
    for week in month_days:
        for day_num in week:
            is_today = (day_num == today.day and cal_month == today.month and cal_year == today.year)
            calendar_days.append({
                'number': day_num,
                'is_today': is_today,
                'events': events_by_date.get(day_num, []),
            })

    # ─── Media Library data ──────────────────────────────────────────
    media_assets = []
    media_assets_total = 0
    media_folders = []
    media_tags = []
    media_current_type = ''
    media_current_folder = ''
    media_query = ''

    if MediaAsset:
        from apps.media_assets.services import MediaService
        from apps.media_assets.models import MediaFolder, MediaTag

        service = MediaService(user)
        media_folders = _safe_list(service.get_folder_tree())
        media_tags = _safe_list(MediaTag.objects.filter(user=user))

        media_current_type = request.GET.get('media_type', '')
        media_current_folder = request.GET.get('media_folder', '')
        media_query = request.GET.get('media_q', '').strip()

        assets_qs = MediaAsset.objects.filter(user=user).select_related('folder').order_by('-created_at')
        media_assets_total = assets_qs.count()

        if media_query:
            assets_qs = service.search_assets(media_query)
        if media_current_type:
            assets_qs = assets_qs.filter(file_type=media_current_type)
        if media_current_folder and str(media_current_folder).isdigit():
            assets_qs = assets_qs.filter(folder_id=int(media_current_folder))
        asset_list = list(assets_qs[:32])
        for a in asset_list:
            a.display_url = service.get_asset_url(a)
            a.display_thumbnail_url = service.get_thumbnail_url(a)

        for a in asset_list:
            dims = ''
            if a.width and a.height:
                dims = f"{a.width} x {a.height}"
            media_assets.append({
                'id': a.id,
                'name': a.title or a.original_filename or 'Asset',
                'file_type': a.file_type or 'other',
                'file_type_display': a.get_file_type_display() if hasattr(a, 'get_file_type_display') else a.file_type,
                'file_size': a.file_size,
                'file_size_display': _format_file_size(a.file_size),
                'display_url': a.display_url,
                'display_thumbnail_url': a.display_thumbnail_url,
                'dimensions': dims,
                'duration': a.duration,
                'is_image': a.file_type == 'image',
                'is_video': a.file_type == 'video',
                'is_audio': a.file_type == 'audio',
            })

    # ─── Trending Topics & Automation data ────────────────────────────
    trending_topics = []
    automation_rule_count = 0
    active_automation_topic_ids = set()
    all_platforms = []
    automation_rules = []
    automation_rules_json = []
    content_items = []
    content_items_total = 0
    try:
        from apps.trending.models import Topic, TrendingAutomationRule
        trending_topics = _safe_list(Topic.objects.filter(is_active=True).order_by('-subscriber_count'))
        active_rules = TrendingAutomationRule.objects.filter(user=user, is_active=True)
        automation_rule_count = active_rules.count()
        active_automation_topic_ids = set(active_rules.values_list('topic_id', flat=True))

        from apps.social_accounts.models import SocialAccount
        connected_accounts = _safe_list(
            SocialAccount.objects.filter(user=user, is_active=True).values('platform', 'account_name')
        )
        connected_map = {a['platform']: a['account_name'] for a in connected_accounts}
        PLATFORM_DISPLAY = {
            'facebook': 'Facebook', 'instagram': 'Instagram', 'twitter': 'X (Twitter)',
            'linkedin': 'LinkedIn', 'tiktok': 'TikTok', 'youtube': 'YouTube',
        }
        all_platforms = [
            {
                'platform': p,
                'name': PLATFORM_DISPLAY.get(p, p.title()),
                'connected': p in connected_map,
                'account_name': connected_map.get(p, ''),
            }
            for p in ['linkedin', 'twitter', 'instagram', 'facebook', 'tiktok', 'youtube']
        ]
        automation_rules = _safe_list(
            TrendingAutomationRule.objects.filter(user=user).select_related('topic')
        )
        import json as _json
        automation_rules_json = {
            rule.topic_id: {
                'platforms': rule.platforms,
                'schedule_interval': rule.schedule_interval,
                'auto_publish': rule.auto_publish,
            }
            for rule in automation_rules
        }
        from apps.content_studio.models import ContentItem
        content_items_qs = filter_by_context(request, ContentItem.objects.all()).order_by('-created_at')
        content_items_total = content_items_qs.count()
        content_items = _safe_list(content_items_qs[:20])
    except Exception:
        pass

    context = {
        'posts': posts,
        'calendar_month_label': calendar_month_label,
        'calendar_days': calendar_days,
        'media_assets': media_assets,
        'media_assets_total': media_assets_total,
        'media_folders': media_folders,
        'media_tags': media_tags,
        'media_current_type': media_current_type,
        'media_current_folder': media_current_folder,
        'media_query': media_query,
        'trending_topics': trending_topics,
        'automation_rule_count': automation_rule_count,
        'active_automation_topic_ids': active_automation_topic_ids,
        'all_platforms': all_platforms,
        'automation_rules': automation_rules,
        'automation_rules_json': automation_rules_json,
        'content_items': content_items,
        'content_items_total': content_items_total,
    }
    return render(request, 'dashboard/social_content_hub.html', context)

