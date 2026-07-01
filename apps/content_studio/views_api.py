import calendar
import logging
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .adapters import PlatformAdapter
from .models import ALL_PLATFORMS, ContentApproval, ContentItem, ContentVersion, DeletedDriveSheet, ExcelSheetImport, ExcelSheetRowLog, UserGoogleSheet
from .services import ContentService
from apps.social_accounts.models import SocialPost
from apps.social_accounts.services import SocialService
from apps.workspaces.query_helpers import filter_by_context
from apps.workspaces.decorators import require_workspace_permission
from core.tenant import get_current_tenant

logger = logging.getLogger(__name__)


@login_required
def dashboard(request):
    service = ContentService(request.user)
    items = service.list_content(workspace=get_current_tenant())[:20]
    generators = service.get_available_generators()
    stats = {
        'total': filter_by_context(request, ContentItem.objects.all()).count(),
        'drafts': filter_by_context(request, ContentItem.objects.all()).filter(status='draft').count(),
        'approved': filter_by_context(request, ContentItem.objects.all()).filter(status='approved').count(),
        'published': filter_by_context(request, ContentItem.objects.all()).filter(status='published').count(),
    }
    return render(request, 'content_studio/dashboard.html', {
        'items': items,
        'generators': generators,
        'stats': stats,
    })


@login_required
@require_workspace_permission('content_studio', 'create')
def generate(request):
    service = ContentService(request.user)

    if request.method == 'POST':
        content_type = request.POST.get('content_type', 'caption')
        prompt = request.POST.get('prompt', '').strip()
        platform = request.POST.get('platform', '')
        tone = request.POST.get('tone', 'professional')
        next_url = request.POST.get('next', 'content_studio:content_hub')

        if not prompt:
            messages.error(request, 'Please enter a prompt.')
        else:
            extra = {}
            if content_type == 'hashtag_set':
                extra['count'] = int(request.POST.get('hashtag_count', 10))
                extra['category'] = request.POST.get('category', 'general')
            if content_type == 'carousel':
                extra['slides'] = int(request.POST.get('slides', 5))
            if content_type == 'script':
                extra['format'] = request.POST.get('format', 'short')
            if content_type == 'image_prompt':
                extra['style'] = request.POST.get('style', '')
                extra['mood'] = request.POST.get('mood', '')
            if content_type == 'cta':
                extra['goal'] = request.POST.get('goal', 'engagement')
            if content_type == 'caption':
                extra['caption_hashtag_count'] = int(request.POST.get('caption_hashtag_count', 3))
                extra['target_audience'] = request.POST.get('target_audience', '')
            if content_type == 'full_post':
                extra['target_audience'] = request.POST.get('target_audience', '')
                extra['key_points'] = request.POST.get('key_points', '')

            item = service.generate_content(content_type, prompt, platform=platform, tone=tone, **extra)
            if item is None:
                messages.error(request, f'Unknown content type: {content_type}')
                return redirect(next_url)
            if item.body.startswith('['):
                error_msg = item.body
                item.delete()
                messages.error(request, error_msg)
                return redirect(next_url)
            asset_ids = request.POST.get('asset_ids', '')
            if asset_ids:
                ids = [int(x) for x in asset_ids.split(',') if x.strip().isdigit()]
                if ids:
                    item.attachments.set(ids)
            messages.success(request, f'{item.get_content_type_display()} generated!')
            return redirect(next_url)

    generators = service.get_available_generators()
    return render(request, 'content_studio/generate.html', {
        'generators': generators,
    })


@login_required
def detail(request, item_id):
    item = get_object_or_404(filter_by_context(request, ContentItem.objects.all()), id=item_id)
    versions = item.versions.all()[:10]
    approvals = item.approvals.all()[:5]
    adapter = PlatformAdapter(item.platform) if item.platform else None
    platform_issues = adapter.validate_content(item.content_type, item.body) if adapter else []
    from apps.social_accounts.services import SocialService
    s = SocialService(request.user)
    platform_filter = item.platform if item.platform and item.platform != 'all' else None
    social_accounts = s.get_accounts(platform=platform_filter)
    from django.middleware.csrf import get_token
    return render(request, 'content_studio/detail.html', {
        'item': item,
        'versions': versions,
        'approvals': approvals,
        'platform_issues': platform_issues,
        'social_accounts': social_accounts,
        'all_platforms': ALL_PLATFORMS,
        'csrf_token': get_token(request),
    })


@login_required
def calendar_view(request):
    today = timezone.localdate()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    month_start = datetime(year, month, 1).date()
    _, days_in_month = calendar.monthrange(year, month)
    month_end = datetime(year, month, days_in_month).date()

    items = filter_by_context(request, ContentItem.objects.all()).filter(
        scheduled_at__date__gte=month_start,
        scheduled_at__date__lte=month_end,
    ).order_by('scheduled_at')

    items_by_date = {}
    for item in items:
        d = item.scheduled_at.date()
        items_by_date.setdefault(d, []).append(item)

    cal_rows = []
    first_weekday = month_start.weekday()
    week = [None] * first_weekday
    for day in range(1, days_in_month + 1):
        date = datetime(year, month, day).date()
        week.append({
            'date': date,
            'day': day,
            'items': items_by_date.get(date, []),
            'is_today': date == today,
            'is_past': date < today,
        })
        if len(week) == 7:
            cal_rows.append(week)
            week = []
    if week:
        week.extend([None] * (7 - len(week)))
        cal_rows.append(week)

    prev_month = month - 1 or 12
    prev_year = year - 1 if month == 1 else year
    next_month = month + 1 if month < 12 else 1
    next_year = year + 1 if month == 12 else year

    month_name = calendar.month_name[month]

    unscheduled = filter_by_context(request, ContentItem.objects.all()).filter(
        scheduled_at__isnull=True
    ).order_by('-created_at')[:10]

    return render(request, 'content_studio/calendar.html', {
        'cal_rows': cal_rows,
        'year': year,
        'month': month,
        'month_name': month_name,
        'prev_month': prev_month,
        'prev_year': prev_year,
        'next_month': next_month,
        'next_year': next_year,
        'unscheduled': unscheduled,
        'today': today,
    })


@login_required
@require_workspace_permission('content_studio', 'edit')
def edit(request, item_id):
    item = get_object_or_404(filter_by_context(request, ContentItem.objects.all()), id=item_id)
    if request.method == 'POST':
        if request.POST.get('clear_schedule'):
            item.scheduled_at = None
            item.status = 'draft'
            item.save(update_fields=['scheduled_at', 'status', 'updated_at'])
            SocialPost.objects.filter(content_item=item).update(
                scheduled_at=None, status='draft'
            )
            messages.success(request, 'Schedule cleared.')
            return redirect('content_studio:detail', item_id=item.id)
        scheduled_at_raw = request.POST.get('scheduled_at', '').strip()
        if scheduled_at_raw:
            try:
                parsed = datetime.fromisoformat(scheduled_at_raw)
                if timezone.is_naive(parsed):
                    parsed = timezone.make_aware(parsed)
                item.scheduled_at = parsed
                item.status = 'scheduled'
                item.save(update_fields=['scheduled_at', 'status', 'updated_at'])
                SocialPost.objects.filter(content_item=item).update(
                    scheduled_at=parsed, status='scheduled'
                )
                messages.success(request, 'Content scheduled.')
            except (ValueError, TypeError):
                messages.error(request, 'Invalid date format.')
                return redirect('content_studio:detail', item_id=item.id)
        body = request.POST.get('body', '').strip()
        title = request.POST.get('title', '').strip()
        if body and title:
            item.body = body
            item.title = title
            item.save(update_fields=['body', 'title', 'updated_at'])
            messages.success(request, 'Content updated.')
            return redirect('content_studio:detail', item_id=item.id)
    return render(request, 'content_studio/edit.html', {
        'item': item,
    })


@login_required
@require_workspace_permission('content_studio', 'edit')
def refine(request, item_id):
    item = get_object_or_404(filter_by_context(request, ContentItem.objects.all()), id=item_id)
    if request.method == 'POST':
        feedback = request.POST.get('feedback', '').strip()
        if feedback:
            service = ContentService(request.user)
            result = service.refine_content(item_id, feedback)
            if result.body.startswith('['):
                messages.error(request, result.body)
                return redirect('content_studio:detail', item_id=item_id)
            messages.success(request, 'Content refined.')
            return redirect('content_studio:detail', item_id=item_id)
    return render(request, 'content_studio/refine.html', {
        'item': item,
    })


@login_required
@require_workspace_permission('content_studio', 'edit')
def approve(request, item_id):
    item = get_object_or_404(filter_by_context(request, ContentItem.objects.all()), id=item_id)
    if request.method == 'POST':
        service = ContentService(request.user)
        decision = request.POST.get('decision', 'approved')
        comment = request.POST.get('comment', '').strip()
        service.approve_content(item_id, request.user, decision, comment)
        messages.success(request, f'Content {decision}.')
        return redirect('content_studio:detail', item_id=item_id)
    return render(request, 'content_studio/approve.html', {
        'item': item,
    })


@login_required
@require_workspace_permission('content_studio', 'delete')
def delete(request, item_id):
    item = get_object_or_404(filter_by_context(request, ContentItem.objects.all()), id=item_id)
    if request.method == 'POST':
        item.delete()
        messages.success(request, 'Content deleted.')
        return redirect('content_studio:content_hub')


@login_required
@require_workspace_permission('content_studio', 'delete')
def bulk_delete(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    import json
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    ids = body.get('ids', [])
    if not ids:
        return JsonResponse({'deleted': 0})
    qs = filter_by_context(request, ContentItem.objects.filter(id__in=ids))
    count = qs.count()
    qs.delete()
    messages.success(request, f'{count} item(s) deleted.')
    return JsonResponse({'deleted': count})


@login_required
@require_workspace_permission('content_studio', 'create')
def save_as_draft(request, item_id):
    item = get_object_or_404(filter_by_context(request, ContentItem.objects.all()), id=item_id)
    if request.method == 'POST':
        from apps.social_accounts.services import SocialService
        s = SocialService(request.user)
        platform_filter = item.platform if item.platform and item.platform != 'all' else None
        accounts = s.get_accounts(platform=platform_filter)
        if not accounts.exists():
            platform_name = item.platform.title() if item.platform else 'social'
            messages.warning(request, f'Please connect a {platform_name} account first.')
            return redirect('social_accounts:social_hub')
        account_ids = request.POST.getlist('account_ids')
        if not account_ids:
            messages.error(request, 'Select at least one social account.')
            return redirect('content_studio:detail', item_id=item_id)
        service = ContentService(request.user)
        service.save_as_draft(item_id, [int(a) for a in account_ids])
        messages.success(request, 'Saved as draft.')
        return redirect('content_studio:detail', item_id=item_id)
    return redirect('content_studio:detail', item_id=item_id)


@login_required
def history(request):
    status_filter = request.GET.get('status', '')
    search_query = request.GET.get('q', '').strip()
    from django.core.paginator import Paginator

    all_items_qs = filter_by_context(request, ContentItem.objects.all()).order_by('-created_at')
    if status_filter:
        all_items_qs = all_items_qs.filter(status=status_filter)
    if search_query:
        all_items_qs = all_items_qs.filter(
            models.Q(title__icontains=search_query) | models.Q(body__icontains=search_query)
        )
    paginator = Paginator(all_items_qs, 50)
    try:
        page_number = int(request.GET.get('page', 1))
    except (ValueError, TypeError):
        page_number = 1
    if page_number > paginator.num_pages and paginator.num_pages > 0:
        params = request.GET.copy()
        params['page'] = paginator.num_pages
        return redirect(request.path + '?' + params.urlencode())
    page_obj = paginator.page(page_number)

    return render(request, 'content_studio/history.html', {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search_query': search_query,
        'status_choices': ContentItem.STATUS_CHOICES,
    })


@login_required
def content_hub(request):
    """Unified Content Studio hub — combines overview, generate, and history in tabs."""
    service = ContentService(request.user)

    # Overview tab data
    items = service.list_content(workspace=get_current_tenant())[:20]
    generators = service.get_available_generators()
    stats = {
        'total': filter_by_context(request, ContentItem.objects.all()).count(),
        'drafts': filter_by_context(request, ContentItem.objects.all()).filter(status='draft').count(),
        'approved': filter_by_context(request, ContentItem.objects.all()).filter(status='approved').count(),
        'published': filter_by_context(request, ContentItem.objects.all()).filter(status='published').count(),
    }

    # History tab: filterable + paginated
    status_filter = request.GET.get('status', '')
    search_query = request.GET.get('q', '').strip()
    active_tab = request.GET.get('tab', 'overview')

    from django.core.paginator import Paginator

    all_items_qs = filter_by_context(request, ContentItem.objects.all()).order_by('-created_at')
    if status_filter:
        all_items_qs = all_items_qs.filter(status=status_filter)
    if search_query:
        all_items_qs = all_items_qs.filter(
            models.Q(title__icontains=search_query) | models.Q(body__icontains=search_query)
        )
    paginator = Paginator(all_items_qs, 50)
    try:
        page_number = int(request.GET.get('page', 1))
    except (ValueError, TypeError):
        page_number = 1
    if page_number > paginator.num_pages and paginator.num_pages > 0:
        params = request.GET.copy()
        params['page'] = paginator.num_pages
        return redirect(request.path + '?' + params.urlencode())
    page_obj = paginator.page(page_number)

    return render(request, 'content_studio/content_hub.html', {
        'items': items,
        'page_obj': page_obj,
        'generators': generators,
        'stats': stats,
        'status_filter': status_filter,
        'search_query': search_query,
        'active_tab': active_tab,
        'status_choices': ContentItem.STATUS_CHOICES,
    })


# ---------------------------------------------------------------------------
# Excel Sheet Import Views
# ---------------------------------------------------------------------------

@login_required
def excel_sheets(request):
    """Show Excel Sheet Imports with Google Sheets integration status."""
    from django.db.models import Count, Q
    from django.conf import settings as django_settings
    from apps.workspaces.models import WorkspaceStorageConfig, get_or_create_personal_workspace

    sheets = ExcelSheetImport.objects.filter(user=request.user).annotate(
        completed_count=Count('row_logs', filter=Q(row_logs__status='completed')),
        failed_count=Count('row_logs', filter=Q(row_logs__status='failed')),
        total_processed=Count('row_logs'),
    )

    workspace = get_or_create_personal_workspace(request.user)
    config = WorkspaceStorageConfig.objects.filter(workspace=workspace).first()

    sheets_credentials_saved = bool(config and config.is_google_sheets_credentials_configured())

    # Check if user has connected Google Sheets (workspace-level or legacy per-user)
    is_connected = bool(config and config.is_google_sheets_connected())
    if not is_connected:
        try:
            token = request.user.google_sheets_token
            is_connected = bool(token and token.refresh_token)
        except AttributeError:
            pass

    # Get list of user's Google Sheets (if connected), excluding hidden ones
    google_sheets = []
    if is_connected:
        try:
            from .services.google_sheets import GoogleSheetsService
            service = GoogleSheetsService(workspace=workspace)
            raw_sheets = service.list_spreadsheets()
            hidden_ids = set(
                DeletedDriveSheet.objects.filter(user=request.user)
                .values_list('spreadsheet_id', flat=True)
            )
            google_sheets = [s for s in raw_sheets if s['id'] not in hidden_ids]
        except Exception:
            pass

    # Get active sheet for the user
    active_sheet = UserGoogleSheet.objects.filter(user=request.user, is_active=True).first()
    active_import_id = None
    if active_sheet:
        sheet_import = ExcelSheetImport.objects.filter(
            user=request.user, spreadsheet_id=active_sheet.spreadsheet_id
        ).first()
        if sheet_import:
            active_import_id = sheet_import.id

    # KPI stats
    from django.utils import timezone as tz
    sheets_count = sheets.count()
    imports_today = sheets.filter(last_synced_at__date=tz.localdate()).count()
    rows_processed = sum(s.total_processed for s in sheets)
    active_sheet_name = active_sheet.title if active_sheet else None

    return render(request, 'content_studio/excel_sheets.html', {
        'sheets': sheets,
        'is_connected': is_connected,
        'google_sheets': google_sheets,
        'active_sheet': active_sheet,
        'active_import_id': active_import_id,
        'config': config,
        'sheets_credentials_saved': sheets_credentials_saved,
        'google_sheets_redirect_uri': django_settings.GOOGLE_SHEETS_REDIRECT_URI,
        'sheets_count': sheets_count,
        'imports_today': imports_today,
        'rows_processed': rows_processed,
        'active_sheet_name': active_sheet_name,
    })


@login_required
def excel_sheets_add(request):
    """Form to add a new Google Sheet import source."""
    if request.method == 'POST':
        spreadsheet_id = request.POST.get('spreadsheet_id', '').strip()
        sheet_name = request.POST.get('sheet_name', 'Sheet1').strip()
        title = request.POST.get('title', '').strip()

        if not spreadsheet_id:
            messages.error(request, 'Google Spreadsheet ID is required.')
            return redirect('content_studio:excel_sheets')

        if not title:
            title = f"Sheet {spreadsheet_id[:12]}"

        # Check user has OAuth connected (workspace-level preferred, fallback to per-user)
        from apps.workspaces.models import WorkspaceStorageConfig, get_or_create_personal_workspace
        workspace = get_or_create_personal_workspace(request.user)
        has_oauth = False
        try:
            config = WorkspaceStorageConfig.objects.get(workspace=workspace)
            has_oauth = config.is_google_sheets_connected()
        except WorkspaceStorageConfig.DoesNotExist:
            pass
        if not has_oauth:
            has_oauth = hasattr(request.user, 'google_sheets_token') and request.user.google_sheets_token and request.user.google_sheets_token.refresh_token
        if not has_oauth:
            messages.error(request, 'Please connect your Google account from Storage Settings first.')
            return redirect('workspaces:storage_settings')

        from .services.google_sheets import GoogleSheetsService

        try:
            service = GoogleSheetsService(workspace=workspace)
            rows = service.read_rows(spreadsheet_id, sheet_name)

            if not rows:
                messages.error(request, 'Could not read the sheet (empty or invalid).')
                return redirect('content_studio:excel_sheets')

        except Exception as exc:
            messages.error(request, f'Failed to read the sheet: {exc}')
            return redirect('content_studio:excel_sheets')

        ExcelSheetImport.objects.create(
            user=request.user,
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_name or 'Sheet1',
            title=title,
        )
        messages.success(request, 'Excel sheet import source added successfully.')
        return redirect('content_studio:excel_sheets')

    return render(request, 'content_studio/excel_sheets_add.html')


@login_required
def excel_sheets_sync(request, sheet_id):
    """Trigger a sync for a specific Excel sheet import."""
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('content_studio:excel_sheets')

    source = get_object_or_404(ExcelSheetImport, id=sheet_id, user=request.user)

    try:
        from .services.excel_processor import ExcelSheetProcessor
        from apps.workspaces.models import get_or_create_personal_workspace
        processor = ExcelSheetProcessor(user=request.user, workspace=get_or_create_personal_workspace(request.user))
        result = processor.sync_sheet(source)
        messages.success(
            request,
            f"Sync completed: {result['processed']} processed, {result['failed']} failed, {result['skipped']} skipped."
        )
    except Exception as exc:
        messages.error(request, f'Sync failed: {exc}')

    return redirect('content_studio:excel_sheets')


@login_required
def excel_sheets_delete(request, sheet_id):
    """Delete an Excel sheet import source, its logs, and attempt to delete the
    actual Google Sheet from Drive. If Drive deletion fails (e.g. insufficient
    permissions), the local record is still removed."""
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('content_studio:excel_sheets')

    source = get_object_or_404(ExcelSheetImport, id=sheet_id, user=request.user)
    spreadsheet_id = source.spreadsheet_id

    # Try to delete the actual Google Sheet from Drive
    from .services.google_sheets import GoogleSheetsService
    from apps.workspaces.models import get_or_create_personal_workspace
    deleted = False
    try:
        service = GoogleSheetsService(
            user=request.user,
            workspace=get_or_create_personal_workspace(request.user),
        )
        deleted = service.delete_spreadsheet(spreadsheet_id)
    except Exception:
        pass

    source.delete()

    # Remove the active-sheet tracking record for this spreadsheet
    UserGoogleSheet.objects.filter(user=request.user, spreadsheet_id=spreadsheet_id).delete()

    if deleted:
        messages.success(request, 'Import and Google Sheet deleted from Drive.')
    else:
        # Track the spreadsheet_id so it gets hidden from "Your Google Drive Sheets"
        DeletedDriveSheet.objects.get_or_create(
            user=request.user,
            spreadsheet_id=spreadsheet_id,
        )
        messages.warning(
            request,
            'Import removed. Could not delete the Google Sheet from Drive — '
            'you may need to delete it manually.',
        )

    return redirect('content_studio:excel_sheets')


# ---------------------------------------------------------------------------
# Google Sheets Integration Views
# ---------------------------------------------------------------------------

@login_required
def google_sheets_list(request):
    """Return a JSON list of the user's Google Sheets, excluding hidden ones."""
    from .services.google_sheets import GoogleSheetsService
    from apps.workspaces.models import get_or_create_personal_workspace
    try:
        service = GoogleSheetsService(workspace=get_or_create_personal_workspace(request.user))
        raw_sheets = service.list_spreadsheets()
        hidden_ids = set(
            DeletedDriveSheet.objects.filter(user=request.user)
            .values_list('spreadsheet_id', flat=True)
        )
        sheets = [s for s in raw_sheets if s['id'] not in hidden_ids]
        return JsonResponse({'sheets': sheets})
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=400)


@login_required
def google_sheets_create(request):
    """Create a new Google Sheet with required headers and select it."""
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('content_studio:excel_sheets')

    from .services.google_sheets import GoogleSheetsService
    from apps.workspaces.models import get_or_create_personal_workspace
    try:
        service = GoogleSheetsService(workspace=get_or_create_personal_workspace(request.user))
        title = request.POST.get('title', 'Content Generator')
        result = service.create_sheet(title)
        spreadsheet_id = result['spreadsheetId']
        sheet_name = 'Sheet1'

        UserGoogleSheet.objects.update_or_create(
            user=request.user,
            defaults={
                'spreadsheet_id': spreadsheet_id,
                'title': title,
                'sheet_name': sheet_name,
                'is_active': True,
            },
        )

        ExcelSheetImport.objects.get_or_create(
            user=request.user,
            spreadsheet_id=spreadsheet_id,
            defaults={
                'sheet_name': sheet_name,
                'title': title,
            },
        )

        messages.success(request, f'Google Sheet "{title}" created and selected.')
        return redirect('content_studio:excel_sheets')
    except Exception as exc:
        messages.error(request, f'Failed to create sheet: {exc}')
        return redirect('content_studio:excel_sheets')


@login_required
def google_sheets_select(request):
    """Select an existing Google Sheet as the active sheet for the user."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=400)

    spreadsheet_id = request.POST.get('spreadsheet_id')
    title = request.POST.get('title', 'Untitled')
    sheet_name = request.POST.get('sheet_name', 'Sheet1')

    if not spreadsheet_id:
        messages.error(request, 'Spreadsheet ID is required.')
        return redirect('content_studio:excel_sheets')

    UserGoogleSheet.objects.update_or_create(
        user=request.user,
        defaults={
            'spreadsheet_id': spreadsheet_id,
            'title': title,
            'sheet_name': sheet_name,
            'is_active': True,
        },
    )

    ExcelSheetImport.objects.get_or_create(
        user=request.user,
        spreadsheet_id=spreadsheet_id,
        defaults={
            'sheet_name': sheet_name,
            'title': title,
        },
    )

    messages.success(request, f'Google Sheet "{title}" selected.')
    return redirect('content_studio:excel_sheets')


# ---------------------------------------------------------------------------
# Content Publish Endpoint
# ---------------------------------------------------------------------------

@login_required
@require_workspace_permission('content_studio', 'edit')
def publish_content_item(request, item_id):
    """Publish a content item to connected social accounts"""
    item = get_object_or_404(filter_by_context(request, ContentItem.objects.all()), id=item_id)
    
    if item.status == 'published':
        return JsonResponse({'published': True, 'message': 'Already published'})
    
    # Check if user has connected account for this platform
    if item.platform == 'all':
        # For 'all' platform, use the first connected account across all platforms
        account = SocialService(request.user).get_accounts().first()
        if not account:
            return JsonResponse({
                'error': 'not_connected',
                'message': 'Connect at least one social account to publish.'
            }, status=400)
    else:
        account = SocialService(request.user).get_accounts(platform=item.platform).first()
        if not account:
            return JsonResponse({
                'error': 'not_connected',
                'message': f'Connect your {item.platform.title()} account to publish.'
            }, status=400)
    
    try:
        # Get full content from platform_data if available, fallback to item.body
        full_content = item.body
        if item.platform_data and item.platform and item.platform in item.platform_data:
            platform_content = item.platform_data[item.platform]
            if isinstance(platform_content, dict) and 'content' in platform_content:
                full_content = platform_content['content']
        
        # Create social post
        post = SocialPost.objects.create(
            user=request.user,
            account=account,
            content_item=item,
            platform=item.platform,
            content=full_content,
            hashtags=item.tags or [],
            status='scheduled',
            workspace=get_current_tenant(),
        )
        
        # Publish via service
        svc = SocialService(request.user)
        result = svc.publish_post(post.id)
        
        if result:
            item.status = 'published'
            item.save(update_fields=['status'])
            return JsonResponse({
                'published': True,
                'post_id': post.id,
                'platform_post_url': post.platform_post_url,
            })
        else:
            post.refresh_from_db()
            return JsonResponse({
                'error': 'publish_failed',
                'message': post.error_message or 'Platform returned empty result',
            }, status=500)
        
    except Exception as e:
        return JsonResponse({
            'error': 'publish_failed',
            'message': str(e)
        }, status=500)