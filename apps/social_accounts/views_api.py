import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from django.contrib import messages

from .models import SocialAccount, SocialAnalytics, SocialPost
from .oauth import OAuth2Flow
from .platforms import FacebookPlatform, get_platform
from .services import SocialService

logger = logging.getLogger(__name__)


def _save_social_post_media(uploaded_file):
    import mimetypes
    import os
    import re
    import uuid

    from django.core.files.storage import default_storage
    from django.utils import timezone

    if not uploaded_file:
        raise ValueError('No file selected.')

    content_type = getattr(uploaded_file, 'content_type', '') or ''
    guessed_type, _encoding = mimetypes.guess_type(uploaded_file.name)
    effective_type = content_type or guessed_type or 'application/octet-stream'
    if not (effective_type.startswith('image/') or effective_type.startswith('video/')):
        raise ValueError('Only image and video files can be attached to social posts.')

    safe_name = (uploaded_file.name or 'media').replace('\\', '/').split('/')[-1]
    safe_name = re.sub(r'[^A-Za-z0-9._-]+', '_', safe_name).strip('._') or 'media'
    stem, ext = os.path.splitext(safe_name)
    saved_name = f"{stem[:80]}_{uuid.uuid4().hex[:10]}{ext.lower()}"
    prefix = timezone.now().strftime('social_post_uploads/%Y/%m/%d')
    storage_path = default_storage.save(f"{prefix}/{saved_name}", uploaded_file)
    return {
        'url': default_storage.url(storage_path),
        'storage_path': storage_path.replace('\\', '/'),
        'title': safe_name,
        'file_type': 'video' if effective_type.startswith('video/') else 'image',
        'mime_type': effective_type,
        'file_size': getattr(uploaded_file, 'size', 0),
    }


@login_required
def social_hub(request):
    import calendar as cal_mod
    from datetime import date, datetime
    from collections import Counter, defaultdict
    from django.utils import timezone
    from django.db.models import Q

    service = SocialService(request.user)
    accounts = service.get_accounts()
    summary = service.get_connected_platforms_summary()
    platforms = service.get_available_platforms()

    all_posts = SocialPost.objects.filter(user=request.user).select_related('account').order_by('-created_at')
    recent_posts = all_posts[:10]
    posts = all_posts

    status_filter = request.GET.get('status', '')
    if status_filter:
        posts = posts.filter(status=status_filter)
    status_counts = dict(Counter(SocialPost.objects.filter(user=request.user).values_list('status', flat=True)))
    total = sum(status_counts.values()) or 1
    for k in ['draft', 'scheduled', 'publishing', 'published', 'failed']:
        status_counts[f'{k}_pct'] = round(status_counts.get(k, 0) / total * 100)

    today = timezone.localdate()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    month_start = timezone.make_aware(datetime(year, month, 1))
    if month == 12:
        month_end = timezone.make_aware(datetime(year + 1, 1, 1))
    else:
        month_end = timezone.make_aware(datetime(year, month + 1, 1))
    cal = cal_mod.Calendar()
    cal_posts = SocialPost.objects.filter(
        user=request.user, scheduled_at__gte=month_start, scheduled_at__lt=month_end,
    ).select_related('account').order_by('scheduled_at')
    posts_by_day = defaultdict(list)
    for p in cal_posts:
        day_key = p.scheduled_at.day if p.scheduled_at else p.created_at.day
        posts_by_day[day_key].append(p)
    month_days = []
    for day in cal.itermonthdays(year, month):
        if day == 0:
            month_days.append(None)
        else:
            month_days.append((date(year, month, day), posts_by_day.get(day, [])))
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    platform_colors = {
        'facebook': '#1877F2', 'instagram': '#E4405F', 'twitter': '#1DA1F2',
        'linkedin': '#0A66C2', 'tiktok': '#FE2C55', 'youtube': '#FF0000',
    }

    # Nepali calendar events (Gregorian dates for 2025-2027 range)
    nepali_events = {
        # Fixed or annually recurring
        (1, 1): [{'name': 'New Year\'s Day', 'emoji': '🎆', 'color': '#6D28D9'}],
        (1, 14): [{'name': 'Maghe Sankranti', 'emoji': '🪔', 'color': '#F59E0B'}],
        (1, 15): [{'name': 'Sonam Lhosar', 'emoji': '🎊', 'color': '#10B981'}],
        (1, 29): [{'name': 'Tamang Lhosar', 'emoji': '🎊', 'color': '#10B981'}],
        (2, 1): [{'name': 'Martyrs\' Day', 'emoji': '🇮🇳', 'color': '#EF4444'}],
        (2, 12): [{'name': 'Shivaratri', 'emoji': '🔱', 'color': '#8B5CF6'}],
        (2, 26): [{'name': 'Gyalpo Lhosar', 'emoji': '🎊', 'color': '#10B981'}],
        (3, 11): [{'name': 'Falgu Purnima (Holi)', 'emoji': '🌈', 'color': '#EC4899'}],
        (4, 13): [{'name': 'Bisket / Nepali New Year', 'emoji': '🇳🇵', 'color': '#6D28D9'}],
        (4, 14): [{'name': 'Bisket Jatra', 'emoji': '🎊', 'color': '#8B5CF6'}],
        (4, 28): [{'name': 'Buddha Jayanti', 'emoji': '☸️', 'color': '#F59E0B'}],
        (5, 1): [{'name': 'Labor Day', 'emoji': '⚒️', 'color': '#EF4444'}],
        (5, 23): [{'name': 'Rhododendron Festival', 'emoji': '🌺', 'color': '#EC4899'}],
        (6, 15): [{'name': 'Ganga Dussehra', 'emoji': '🙏', 'color': '#3B82F6'}],
        (7, 7): [{'name': 'Gai Jatra', 'emoji': '🐄', 'color': '#F59E0B'}],
        (7, 18): [{'name': 'Raksha Bandhan', 'emoji': '🧵', 'color': '#EC4899'}],
        (7, 26): [{'name': 'Janai Purnima', 'emoji': '🙏', 'color': '#8B5CF6'}],
        (8, 11): [{'name': 'Krishna Janmashtami', 'emoji': '🦚', 'color': '#3B82F6'}],
        (8, 18): [{'name': 'Haritalika Teej', 'emoji': '🪔', 'color': '#EF4444'}],
        (8, 26): [{'name': 'Indra Jatra', 'emoji': '🎭', 'color': '#F59E0B'}],
        (9, 1): [{'name': 'Rishi Panchami', 'emoji': '🙏', 'color': '#8B5CF6'}],
        (9, 2): [{'name': 'Maha Ashtami', 'emoji': '⚔️', 'color': '#EF4444'}],
        (9, 3): [{'name': 'Maha Navami', 'emoji': '⚔️', 'color': '#EF4444'}],
        (9, 4): [{'name': 'Vijaya Dashami (Dashain)', 'emoji': '🪁', 'color': '#10B981'}],
        (9, 5): [{'name': 'Dashain', 'emoji': '🪁', 'color': '#10B981'}],
        (9, 6): [{'name': 'Dashain', 'emoji': '🪁', 'color': '#10B981'}],
        (9, 7): [{'name': 'Dashain', 'emoji': '🪁', 'color': '#10B981'}],
        (10, 20): [{'name': 'Tihar (Deepawali)', 'emoji': '🪔', 'color': '#F59E0B'}],
        (10, 21): [{'name': 'Laxmi Puja', 'emoji': '🪔', 'color': '#F59E0B'}],
        (10, 22): [{'name': 'Gai Tihar / Govardhan', 'emoji': '🐄', 'color': '#10B981'}],
        (10, 23): [{'name': 'Mha Puja / Bhai Tika', 'emoji': '🎊', 'color': '#EC4899'}],
        (10, 24): [{'name': 'Yama Panchak', 'emoji': '🪔', 'color': '#F59E0B'}],
        (11, 7): [{'name': 'Chhath Puja', 'emoji': '🙏', 'color': '#F59E0B'}],
        (11, 26): [{'name': 'Yomari Punhi', 'emoji': '🍡', 'color': '#10B981'}],
        (12, 16): [{'name': 'Udhauli Parba', 'emoji': '🌾', 'color': '#F59E0B'}],
        (12, 24): [{'name': 'Christmas', 'emoji': '🎄', 'color': '#EF4444'}],
        (12, 31): [{'name': 'New Year\'s Eve', 'emoji': '🎆', 'color': '#6D28D9'}],
    }

    # Merge events into month_days
    month_days_with_events = []
    for day_info in month_days:
        if day_info is None:
            month_days_with_events.append(None)
        else:
            d, day_posts = day_info
            events = nepali_events.get((d.month, d.day), [])
            month_days_with_events.append((d, day_posts, events))

    published_posts = SocialPost.objects.filter(user=request.user, status='published')
    total_likes = sum(sum(a.likes for a in p.analytics.all()) for p in published_posts)
    total_comments = sum(sum(a.comments for a in p.analytics.all()) for p in published_posts)
    platform_counts = Counter(p.platform for p in published_posts)
    total_pub = len(published_posts) or 1
    platform_data = [
        {'key': k, 'name': k.title(), 'count': v, 'pct': round(v / total_pub * 100),
         'color': platform_colors.get(k, '#64748B')}
        for k, v in platform_counts.most_common()
    ]

    return render(request, 'social_accounts/social_hub.html', {
        'accounts': accounts,
        'recent_posts': recent_posts,
        'posts': posts,
        'summary': summary,
        'platforms': platforms,
        'current_status': status_filter,
        'status_counts': status_counts,
        'year': year,
        'month': month,
        'month_days': month_days_with_events,
        'prev_month': prev_month,
        'prev_year': prev_year,
        'next_month': next_month,
        'next_year': next_year,
        'month_name': cal_mod.month_name[month],
        'today': today,
        'platform_colors': platform_colors,
        'published_posts': published_posts,
        'total_likes': total_likes,
        'total_comments': total_comments,
        'platform_data': platform_data,
    })


@login_required
def dashboard(request):
    return redirect('social_accounts:social_hub')


@login_required
def connect_platform(request, platform):
    tiktok_client_id = tiktok_client_secret = None
    if platform == 'tiktok':
        tiktok_client_id = request.session.get('tiktok_app_key')
        if not tiktok_client_id:
            return redirect('social_accounts:tiktok_setup')
        tiktok_client_secret = request.session.get('tiktok_app_secret', '')

    oauth = OAuth2Flow(platform, client_id=tiktok_client_id, client_secret=tiktok_client_secret)
    authorize_url = oauth.get_authorize_url(request)
    return redirect(authorize_url)


@login_required
def oauth_callback(request, platform):
    error = request.GET.get('error')
    if error:
        error_desc = request.GET.get('error_description', '')
        logger.warning(f"OAuth callback error for {platform}: {error} - {error_desc}")
        messages.error(request, f'{platform.title()} authorization failed: {error_desc or error}')
        return redirect('social_accounts:social_hub')

    code = request.GET.get('code')
    if not code:
        messages.error(request, 'Authorization cancelled or failed.')
        return redirect('social_accounts:social_hub')

    tiktok_client_id = tiktok_client_secret = None
    if platform == 'tiktok':
        tiktok_client_id = request.session.pop('tiktok_app_key', None)
        tiktok_client_secret = request.session.pop('tiktok_app_secret', None)

    oauth = OAuth2Flow(platform, client_id=tiktok_client_id, client_secret=tiktok_client_secret)
    state = request.GET.get('state')
    token_data = oauth.exchange_code(code, request, state=state)
    if not token_data:
        messages.error(request, f'Failed to authenticate with {platform.title()}.')
        return redirect('social_accounts:social_hub')

    access_token = token_data.get('access_token')
    platform_instance = get_platform(platform)
    platform_instance.access_token = access_token
    profile = platform_instance.get_profile()

    if not profile:
        messages.error(request, f'Could not fetch profile from {platform.title()}.')
        return redirect('social_accounts:social_hub')

    service = SocialService(request.user)

    active_workspace = None
    ws_id = request.session.get('active_workspace_id')
    if ws_id:
        from apps.workspaces.models import WorkspaceMembership
        m = WorkspaceMembership.objects.filter(workspace_id=ws_id, user=request.user).select_related('workspace').first()
        if m:
            active_workspace = m.workspace

    if platform == 'facebook' and isinstance(platform_instance, FacebookPlatform):
        pages = platform_instance.get_pages()
        if len(pages) > 1:
            request.session['fb_pages'] = pages
            request.session['fb_user_token'] = access_token
            return redirect('social_accounts:select_page')
        elif len(pages) == 1:
            page = pages[0]
            profile.update(
                account_id=page['id'],
                account_name=page['name'],
                avatar_url=page.get('picture', {}).get('data', {}).get('url', ''),
                profile_url=page.get('link', ''),
            )
            service.connect_account(platform, page['access_token'], profile, workspace=active_workspace)
            messages.success(request, f'Facebook Page "{page["name"]}" connected.')
            return redirect('social_accounts:social_hub')

    service.connect_account(platform, access_token, profile, workspace=active_workspace)
    messages.success(request, f'{platform.title()} account connected.')
    return redirect('social_accounts:social_hub')

@login_required
def select_page(request):
    pages = request.session.pop('fb_pages', None)
    user_token = request.session.pop('fb_user_token', None)
    if not pages or not user_token:
        messages.error(request, 'Session expired. Please reconnect Facebook.')
        return redirect('social_accounts:social_hub')

    if request.method == 'POST':
        page_id = request.POST.get('page_id')
        selected = next((p for p in pages if p['id'] == page_id), None)
        if not selected:
            messages.error(request, 'Please select a page.')
            return render(request, 'social_accounts/select_page.html', {'pages': pages})

        profile = {
            'account_id': selected['id'],
            'account_name': selected['name'],
            'avatar_url': selected.get('picture', {}).get('data', {}).get('url', ''),
            'profile_url': selected.get('link', ''),
        }
        service = SocialService(request.user)
        active_workspace = None
        ws_id = request.session.get('active_workspace_id')
        if ws_id:
            from apps.workspaces.models import WorkspaceMembership
            m = WorkspaceMembership.objects.filter(workspace_id=ws_id, user=request.user).select_related('workspace').first()
            if m:
                active_workspace = m.workspace
        service.connect_account('facebook', selected['access_token'], profile, workspace=active_workspace)
        messages.success(request, f'Facebook Page "{selected["name"]}" connected.')
        return redirect('social_accounts:social_hub')

    return render(request, 'social_accounts/select_page.html', {'pages': pages})


@login_required
def disconnect_account(request, account_id):
    account = get_object_or_404(SocialAccount, id=account_id, user=request.user)
    platform = account.get_platform_display()

    oauth = OAuth2Flow(account.platform)
    oauth.revoke_token(account.access_token)

    account.delete()
    request.session.pop('tiktok_app_key', None)
    request.session.pop('tiktok_app_secret', None)
    messages.success(request, f'{platform} account disconnected.')
    return redirect('social_accounts:social_hub')


@login_required
def post_list(request):
    posts = SocialPost.objects.filter(user=request.user).select_related('account').order_by('-created_at')
    
    status_filter = request.GET.get('status', '')
    if status_filter:
        posts = posts.filter(status=status_filter)
    
    source_filter = request.GET.get('source', '')
    if source_filter == 'content_studio':
        posts = posts.filter(content_item__isnull=False)
    
    from collections import Counter
    all_posts = SocialPost.objects.filter(user=request.user)
    status_counts = dict(Counter(all_posts.values_list('status', flat=True)))
    total = sum(status_counts.values()) or 1
    status_counts['draft_pct'] = round(status_counts.get('draft', 0) / total * 100)
    status_counts['scheduled_pct'] = round(status_counts.get('scheduled', 0) / total * 100)
    status_counts['publishing_pct'] = round(status_counts.get('publishing', 0) / total * 100)
    status_counts['published_pct'] = round(status_counts.get('published', 0) / total * 100)
    status_counts['failed_pct'] = round(status_counts.get('failed', 0) / total * 100)
    return render(request, 'social_accounts/post_list.html', {
        'posts': posts,
        'current_status': status_filter,
        'current_source': source_filter,
        'status_counts': status_counts,
    })


@login_required
def tiktok_setup(request):
    if request.method == 'POST':
        app_key = request.POST.get('app_key', '').strip()
        app_secret = request.POST.get('app_secret', '').strip()
        if not app_key or not app_secret:
            messages.error(request, 'Both App Key and App Secret are required.')
            return render(request, 'social_accounts/tiktok_setup.html')
        request.session['tiktok_app_key'] = app_key
        request.session['tiktok_app_secret'] = app_secret
        messages.success(request, 'TikTok app credentials saved. Now connect your TikTok account.')
        return redirect('social_accounts:connect_platform', platform='tiktok')
    return render(request, 'social_accounts/tiktok_setup.html')


def _group_accounts_by_platform(accounts):
    grouped = {}
    for acct in accounts:
        grouped.setdefault(acct.platform, []).append(acct)
    return grouped


@login_required
def post_create(request):
    service = SocialService(request.user)
    accounts = service.get_accounts()
    grouped_accounts = _group_accounts_by_platform(accounts)

    active_workspace = None
    ws_id = request.session.get('active_workspace_id')
    if ws_id:
        from apps.workspaces.models import WorkspaceMembership
        m = WorkspaceMembership.objects.filter(workspace_id=ws_id, user=request.user).select_related('workspace').first()
        if m:
            active_workspace = m.workspace

    form_data = {}

    if request.method == 'POST':
        account_ids = request.POST.getlist('account_ids')
        content = request.POST.get('content', '').strip()
        scheduled_at = request.POST.get('scheduled_at') or None
        link_url = request.POST.get('link_url', '').strip()
        hashtags_raw = request.POST.get('hashtags', '').strip()

        hashtags = [h.strip().lstrip('#').strip() for h in hashtags_raw.split(',') if h.strip()] if hashtags_raw else []
        media_urls = [url.strip() for url in request.POST.getlist('media_urls') if url.strip()]

        media_asset_ids = [
            asset_id for asset_id in request.POST.getlist('media_asset_ids')
            if asset_id and asset_id.isdigit()
        ]
        if media_asset_ids:
            from apps.media_assets.models import MediaAsset
            from apps.media_assets.services import MediaService

            media_service = MediaService(request.user)
            selected_assets = MediaAsset.objects.filter(
                id__in=media_asset_ids,
                user=request.user,
            )
            if active_workspace:
                from django.db.models import Q
                selected_assets = selected_assets.filter(
                    Q(workspace=active_workspace) | Q(workspace__isnull=True)
                )

            selected_by_id = {str(asset.id): asset for asset in selected_assets}
            for asset_id in media_asset_ids:
                asset = selected_by_id.get(asset_id)
                if not asset:
                    continue
                asset_url = media_service.get_asset_url(asset)
                if asset_url:
                    media_urls.append(asset_url)

        # Upload files submitted directly via the form (fallback for AJAX).
        # These are social post attachments only; they are not saved to the IDA media library.
        uploaded_files = request.FILES.getlist('media_files')
        if uploaded_files:
            for f in uploaded_files:
                try:
                    upload = _save_social_post_media(f)
                    media_urls.append(upload['url'])
                except Exception as e:
                    logger.error('Media upload via form failed: %s', e)

        media_urls = list(dict.fromkeys(media_urls))

        if not account_ids:
            messages.error(request, 'Please select at least one social account.')
        elif not content and not media_urls:
            messages.error(request, 'Please provide content or media.')
        else:
            posts = service.create_bulk_posts(
                account_ids=account_ids,
                content=content,
                media_urls=media_urls,
                link_url=link_url,
                hashtags=hashtags,
                scheduled_at=scheduled_at,
                workspace=active_workspace,
            )
            if request.POST.get('publish_now'):
                post_ids = [p.id for p in posts]
                service.publish_bulk_posts(post_ids)
                messages.success(request, f'Post published to {len(post_ids)} account(s)!')
            elif scheduled_at:
                messages.success(request, f'Post scheduled to {len(posts)} account(s).')
            else:
                messages.success(request, 'Post saved as draft.')
            return redirect('social_accounts:post_list')

        form_data = {
            'account_ids': account_ids,
            'content': request.POST.get('content', ''),
            'hashtags': request.POST.get('hashtags', ''),
            'link_url': request.POST.get('link_url', ''),
            'scheduled_at': request.POST.get('scheduled_at', ''),
            'media_urls': media_urls,
            'media_asset_ids': media_asset_ids,
        }

    return render(request, 'social_accounts/post_form.html', {
        'accounts': accounts,
        'grouped_accounts': grouped_accounts,
        'form_data': form_data,
    })


@login_required
def post_media_upload(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required.'}, status=405)

    uploaded_file = request.FILES.get('file')
    try:
        upload = _save_social_post_media(uploaded_file)
    except Exception as e:
        logger.exception('Social post media upload failed')
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

    return JsonResponse({
        'success': True,
        'title': upload['title'],
        'file_type': upload['file_type'],
        'url': upload['url'],
        'thumbnail_url': upload['url'] if upload['file_type'] == 'image' else '',
        'file_size': upload['file_size'],
    })


@login_required
def post_detail(request, post_id):
    post = get_object_or_404(SocialPost, id=post_id, user=request.user)
    analytics = post.analytics.order_by('-fetched_at').first()
    return render(request, 'social_accounts/post_detail.html', {
        'post': post,
        'analytics': analytics,
    })


@login_required
def post_delete(request, post_id):
    post = get_object_or_404(SocialPost, id=post_id, user=request.user)
    if request.method == 'POST':
        post.delete()
        messages.success(request, 'Post deleted.')
    return redirect('social_accounts:post_list')


@login_required
def publish_post(request, post_id):
    post = get_object_or_404(SocialPost, id=post_id, user=request.user)
    service = SocialService(request.user)
    result = service.publish_post(post_id)
    if result:
        messages.success(request, 'Post published successfully!')
    else:
        messages.error(request, f'Failed to publish: {post.error_message}')
    return redirect('social_accounts:post_detail', post_id=post.id)


@login_required
def calendar_view(request, year=None, month=None):
    import calendar
    from datetime import date, datetime
    from django.utils import timezone
    from django.db.models import Q
    today = timezone.localdate()
    if year is None: year = today.year
    if month is None: month = today.month
    year, month = int(year), int(month)

    # Build date range for the month
    month_start = timezone.make_aware(datetime(year, month, 1))
    if month == 12:
        month_end = timezone.make_aware(datetime(year + 1, 1, 1))
    else:
        month_end = timezone.make_aware(datetime(year, month + 1, 1))

    cal = calendar.Calendar()
    posts = SocialPost.objects.filter(
        user=request.user,
        scheduled_at__gte=month_start,
        scheduled_at__lt=month_end,
    ).select_related('account').order_by('scheduled_at')

    from collections import defaultdict
    posts_by_day = defaultdict(list)
    for p in posts:
        day_key = p.scheduled_at.day if p.scheduled_at else p.created_at.day
        posts_by_day[day_key].append(p)

    month_days = []
    for day in cal.itermonthdays(year, month):
        if day == 0:
            month_days.append(None)
        else:
            d = date(year, month, day)
            month_days.append((d, posts_by_day.get(day, [])))

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    platform_colors = {
        'facebook': '#1877F2', 'instagram': '#E4405F', 'twitter': '#1DA1F2',
        'linkedin': '#0A66C2', 'tiktok': '#FE2C55', 'youtube': '#FF0000',
    }

    return render(request, 'social_accounts/calendar.html', {
        'year': year,
        'month': month,
        'month_days': month_days,
        'prev_month': prev_month,
        'prev_year': prev_year,
        'next_month': next_month,
        'next_year': next_year,
        'month_name': calendar.month_name[month],
        'today': today,
        'platform_colors': platform_colors,
    })


@login_required
def analytics_view(request, post_id=None):
    if post_id:
        post = get_object_or_404(SocialPost, id=post_id, user=request.user)
        analytics = post.analytics.order_by('-fetched_at').first()
        return render(request, 'social_accounts/analytics_detail.html', {
            'post': post,
            'analytics': analytics,
        })
    posts = SocialPost.objects.filter(user=request.user, status='published').prefetch_related('analytics')
    accounts = SocialAccount.objects.filter(user=request.user)
    total_likes = sum(sum(a.likes for a in p.analytics.all()) for p in posts)
    total_comments = sum(sum(a.comments for a in p.analytics.all()) for p in posts)
    from collections import Counter
    platform_counts = Counter(p.platform for p in posts)
    total_posts = len(posts) or 1
    platform_colors = {
        'facebook': '#1877F2', 'instagram': '#E4405F', 'twitter': '#1DA1F2',
        'linkedin': '#0A66C2', 'tiktok': '#FE2C55', 'youtube': '#FF0000',
    }
    platform_data = [
        {'key': k, 'name': k.title(), 'count': v, 'pct': round(v / total_posts * 100),
         'color': platform_colors.get(k, '#64748B')}
        for k, v in platform_counts.most_common()
    ]
    return render(request, 'social_accounts/analytics_overview.html', {
        'posts': posts,
        'accounts': accounts,
        'total_likes': total_likes,
        'total_comments': total_comments,
        'platform_data': platform_data,
        'range': request.GET.get('range', '30d'),
    })
