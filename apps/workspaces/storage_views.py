import json
import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import AuditLog, Workspace, WorkspaceMembership, WorkspaceStorageConfig, get_or_create_personal_workspace

logger = logging.getLogger(__name__)

OAUTH_STATE_SALT = 'workspace-storage-oauth'
OAUTH_STATE_MAX_AGE = 60 * 15


def _resolve_storage_workspace(request):
    """Use the active workspace if available (requires at least 'member' role),
    otherwise fall back to personal workspace."""
    ws_id = request.session.get('active_workspace_id')
    if ws_id:
        workspace = get_object_or_404(Workspace, id=ws_id)
        membership = WorkspaceMembership.objects.filter(workspace=workspace, user=request.user).first()
        if not membership:
            return None, 'Workspace not found.'
        if membership.role not in ('owner', 'admin', 'member'):
            return None, 'You do not have permission to manage storage settings in this workspace.'
        return workspace, None
    return get_or_create_personal_workspace(request.user), None


def _require_workspace_member(user, workspace):
    return WorkspaceMembership.objects.filter(workspace=workspace, user=user).exists()


def _log(workspace, user, action, details=None):
    AuditLog.objects.create(
        workspace=workspace,
        user=user,
        action=action,
        details=details or {},
        ip_address=None,
    )


def _signed_state(workspace_id, backend):
    return signing.dumps({'workspace_id': workspace_id, 'backend': backend}, salt=OAUTH_STATE_SALT)


def _unsign_state(state):
    try:
        return signing.loads(state, salt=OAUTH_STATE_SALT, max_age=OAUTH_STATE_MAX_AGE)
    except signing.BadSignature:
        return None
    except signing.SignatureExpired:
        return None


@login_required
def storage_settings(request):
    workspace, err = _resolve_storage_workspace(request)
    if err:
        messages.error(request, err)
        return redirect('workspaces:list')
    membership = WorkspaceMembership.objects.filter(workspace=workspace, user=request.user).first()

    config, _ = WorkspaceStorageConfig.objects.get_or_create(
        workspace=workspace,
        defaults={'backend': WorkspaceStorageConfig.BACKEND_LOCAL},
    )

    drive_credentials_saved = config.is_google_drive_credentials_configured()
    s3_filled = bool(
        settings.S3_ENDPOINT_URL
        and settings.S3_BUCKET
        and settings.S3_ACCESS_KEY
        and settings.S3_SECRET_KEY
    )
    dia_s3_configured = bool(
        settings.DIA_S3_ENDPOINT_URL
        and settings.DIA_S3_BUCKET
        and settings.DIA_S3_ACCESS_KEY
        and settings.DIA_S3_SECRET_KEY
    )

    context = {
        'workspace': workspace,
        'membership': membership,
        'config': config,
        'drive_credentials_saved': drive_credentials_saved,
        'google_drive_redirect_uri': settings.GOOGLE_DRIVE_REDIRECT_URI,
        's3_filled': s3_filled,
        'dia_s3_configured': dia_s3_configured,
        'backend_choices': WorkspaceStorageConfig.BACKEND_CHOICES,
    }
    return render(request, 'workspaces/storage_settings.html', context)


@login_required
@require_POST
def storage_select_backend(request):
    workspace, err = _resolve_storage_workspace(request)
    if err:
        messages.error(request, err)
        return redirect('workspaces:list')

    backend = request.POST.get('backend', '')
    if backend not in dict(WorkspaceStorageConfig.BACKEND_CHOICES):
        messages.error(request, 'Invalid storage backend.')
        return redirect('workspaces:storage_settings')

    config, _ = WorkspaceStorageConfig.objects.get_or_create(
        workspace=workspace,
        defaults={'backend': WorkspaceStorageConfig.BACKEND_LOCAL},
    )
    config.backend = backend
    config.last_error = ''
    config.save(update_fields=['backend', 'last_error', 'updated_at'])
    _log(workspace, request.user, f'Storage backend switched to {backend}')
    messages.success(request, f'Active storage switched to {dict(WorkspaceStorageConfig.BACKEND_CHOICES)[backend]}.')
    return redirect('workspaces:storage_settings')


@login_required
@require_POST
def storage_google_drive_save_credentials(request):
    workspace, err = _resolve_storage_workspace(request)
    if err:
        messages.error(request, err)
        return redirect('workspaces:list')
    if request.user != workspace.created_by and not WorkspaceMembership.objects.filter(
        workspace=workspace, user=request.user, role__in=('owner', 'admin')
    ).exists():
        messages.error(request, 'Only workspace owners and admins can change Google Drive credentials.')
        return redirect('workspaces:storage_settings')

    client_id = (request.POST.get('google_drive_client_id') or '').strip()
    client_secret = (request.POST.get('google_drive_client_secret') or '').strip()

    config, _ = WorkspaceStorageConfig.objects.get_or_create(
        workspace=workspace,
        defaults={'backend': WorkspaceStorageConfig.BACKEND_LOCAL},
    )

    had_id = bool(config.get_google_drive_client_id())
    had_secret = bool(config.get_google_drive_client_secret())

    if client_id:
        config.set_google_drive_client_id(client_id)
    if client_secret:
        config.set_google_drive_client_secret(client_secret)

    if not client_id and not client_secret and not had_id and not had_secret:
        messages.error(request, 'Please provide a Google OAuth Client ID and Client Secret.')
        return redirect('workspaces:storage_settings')

    if not config.get_google_drive_client_id() or not config.get_google_drive_client_secret():
        messages.error(
            request,
            'Both Client ID and Client Secret are required. '
            'You cannot save one without the other.',
        )
        return redirect('workspaces:storage_settings')

    config.last_error = ''
    config.save()
    _log(workspace, request.user, 'Google Drive OAuth credentials updated')

    if config.is_google_drive_connected():
        config.is_verified = False
        config.save(update_fields=['is_verified', 'updated_at'])
        messages.success(
            request,
            'Credentials saved. Because the OAuth client changed, please reconnect your '
            'Google Drive account to refresh the access token.',
        )
    else:
        messages.success(request, 'Google Drive credentials saved. You can now connect your Drive account.')

    return redirect('workspaces:storage_settings')


@login_required
@require_POST
def storage_google_drive_disconnect(request):
    workspace, err = _resolve_storage_workspace(request)
    if err:
        messages.error(request, err)
        return redirect('workspaces:list')

    config = WorkspaceStorageConfig.objects.filter(workspace=workspace).first()
    if config:
        config.google_drive_refresh_token_encrypted = ''
        config.google_drive_access_token = ''
        config.google_drive_token_expiry = None
        config.google_drive_folder_id = ''
        config.google_drive_folder_name = ''
        config.google_drive_connected_email = ''
        config.is_verified = False
        if config.backend == WorkspaceStorageConfig.BACKEND_GOOGLE_DRIVE:
            config.backend = WorkspaceStorageConfig.BACKEND_LOCAL
        config.save()
        _log(workspace, request.user, 'Google Drive disconnected')
    messages.success(request, 'Google Drive disconnected.')
    return redirect('workspaces:storage_settings')


@login_required
def storage_google_drive_start(request):
    workspace, err = _resolve_storage_workspace(request)
    if err:
        messages.error(request, err)
        return redirect('workspaces:list')

    config = WorkspaceStorageConfig.objects.filter(workspace=workspace).first()
    if not config or not config.is_google_drive_credentials_configured():
        messages.error(
            request,
            'Save your Google OAuth Client ID and Client Secret first, then come back to connect.',
        )
        return redirect('workspaces:storage_settings')

    client_id = config.get_google_drive_client_id()
    client_secret = config.get_google_drive_client_secret()

    state = _signed_state(workspace.id, WorkspaceStorageConfig.BACKEND_GOOGLE_DRIVE)
    params = {
        'client_id': client_id,
        'redirect_uri': settings.GOOGLE_DRIVE_REDIRECT_URI,
        'response_type': 'code',
        'scope': ' '.join(settings.GOOGLE_DRIVE_OAUTH_SCOPES),
        'access_type': 'offline',
        'prompt': 'consent',
        'include_granted_scopes': 'true',
        'state': state,
    }
    auth_url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(params)
    return HttpResponseRedirect(auth_url)


@login_required
def storage_google_drive_callback(request):
    error = request.GET.get('error')
    if error:
        messages.error(request, f'Google Drive authorization was cancelled or failed: {error}')
        return redirect('workspaces:storage_settings')

    code = request.GET.get('code')
    state = request.GET.get('state', '')
    payload = _unsign_state(state) if state else None
    if not code or not payload or payload.get('backend') != WorkspaceStorageConfig.BACKEND_GOOGLE_DRIVE:
        messages.error(request, 'Invalid OAuth callback. Please try again.')
        return redirect('workspaces:storage_settings')

    workspace = get_object_or_404(Workspace, id=payload['workspace_id'])
    if not WorkspaceMembership.objects.filter(
        workspace=workspace, user=request.user, role__in=('owner', 'admin', 'member')
    ).exists():
        messages.error(request, 'You do not have permission to connect Google Drive in this workspace.')
        return redirect('workspaces:storage_settings')

    config = WorkspaceStorageConfig.objects.filter(workspace=workspace).first()
    if not config or not config.is_google_drive_credentials_configured():
        messages.error(
            request,
            'Your Google OAuth credentials are missing. Save them and try connecting again.',
        )
        return redirect('workspaces:storage_settings')

    client_id = config.get_google_drive_client_id()
    client_secret = config.get_google_drive_client_secret()

    try:
        from google_auth_oauthlib.flow import Flow
        from googleapiclient.discovery import build

        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=settings.GOOGLE_DRIVE_OAUTH_SCOPES,
        )
        flow.redirect_uri = settings.GOOGLE_DRIVE_REDIRECT_URI
        flow.fetch_token(code=code)
        creds = flow.credentials

        service = build('drive', 'v3', credentials=creds, cache_discovery=False)

        about = service.about().get(fields='user').execute()
        user_email = about.get('user', {}).get('emailAddress', '')

        folder_name = 'DIA'
        existing = service.files().list(
            q=(
                f"name = '{folder_name.replace(chr(39), chr(39) + chr(39))}' "
                "and mimeType = 'application/vnd.google-apps.folder' "
                "and trashed = false"
            ),
            spaces='drive',
            fields='files(id,name)',
            pageSize=1,
        ).execute().get('files', [])

        if existing:
            folder_id = existing[0]['id']
        else:
            created = service.files().create(
                body={
                    'name': folder_name,
                    'mimeType': 'application/vnd.google-apps.folder',
                },
                fields='id,name',
            ).execute()
            folder_id = created['id']

        config.set_google_drive_refresh_token(creds.refresh_token or '')
        config.google_drive_access_token = creds.token or ''
        config.google_drive_token_expiry = creds.expiry
        config.google_drive_folder_id = folder_id
        config.google_drive_folder_name = folder_name
        config.google_drive_connected_email = user_email
        config.backend = WorkspaceStorageConfig.BACKEND_GOOGLE_DRIVE
        config.is_verified = True
        config.last_verified_at = timezone.now()
        config.last_error = ''
        config.save()

        _log(workspace, request.user, 'Google Drive connected', {'email': user_email})
        messages.success(
            request,
            f'Google Drive connected as {user_email}. A "{folder_name}" folder has been created in your Drive.',
        )
    except Exception as exc:
        logger.exception('Google Drive OAuth failed')
        config = WorkspaceStorageConfig.objects.filter(workspace=workspace).first()
        if config:
            config.last_error = str(exc)
            config.is_verified = False
            config.save(update_fields=['last_error', 'is_verified', 'updated_at'])
        messages.error(request, f'Google Drive connection failed: {exc}')

    return redirect('workspaces:storage_settings')


@login_required
@require_POST
def storage_dia_s3_test(request):
    workspace, err = _resolve_storage_workspace(request)
    if err:
        return JsonResponse({'ok': False, 'error': err}, status=403)

    from apps.media_assets.storage import DiaS3Storage
    try:
        backend = DiaS3Storage(workspace=workspace, user=request.user)
        ok, err = backend.test_connection()
    except Exception as exc:
        ok, err = False, str(exc)

    return JsonResponse({'ok': ok, 'error': err})


@login_required
@require_POST
def storage_s3_save(request):
    workspace, err = _resolve_storage_workspace(request)
    if err:
        messages.error(request, err)
        return redirect('workspaces:list')

    endpoint = (request.POST.get('s3_endpoint_url') or settings.S3_ENDPOINT_URL or '').strip()
    region = (request.POST.get('s3_region') or settings.S3_REGION or 'us-east-1').strip()
    bucket = (request.POST.get('s3_bucket') or settings.S3_BUCKET or '').strip()
    access_key = (request.POST.get('s3_access_key') or settings.S3_ACCESS_KEY or '').strip()
    secret_key = request.POST.get('s3_secret_key') or settings.S3_SECRET_KEY or ''
    public_base = (request.POST.get('s3_public_base_url') or '').strip()
    path_prefix = (request.POST.get('s3_path_prefix') or '').strip().strip('/')
    use_path_style = request.POST.get('s3_use_path_style') in ('on', 'true', '1')
    provider_label = (request.POST.get('s3_provider_label') or 'S3-Compatible').strip()
    make_active = request.POST.get('make_active') == '1'

    if not all([endpoint, region, bucket, access_key, secret_key]):
        messages.error(request, 'Endpoint, region, bucket, access key, and secret key are all required.')
        return redirect('workspaces:storage_settings')

    config, _ = WorkspaceStorageConfig.objects.get_or_create(
        workspace=workspace,
        defaults={'backend': WorkspaceStorageConfig.BACKEND_LOCAL},
    )

    config.s3_endpoint_url = endpoint
    config.s3_region = region
    config.s3_bucket = bucket
    config.set_s3_access_key(access_key)
    if secret_key:
        config.set_s3_secret_key(secret_key)
    config.s3_public_base_url = public_base
    config.s3_path_prefix = path_prefix
    config.s3_use_path_style = use_path_style
    config.s3_provider_label = provider_label

    if make_active:
        config.backend = WorkspaceStorageConfig.BACKEND_S3

    config.last_error = ''
    config.save()

    from apps.media_assets.storage import S3CompatibleStorage
    try:
        backend = S3CompatibleStorage(config, user=request.user, workspace=workspace)
        ok, err = backend.test_connection()
    except Exception as exc:
        ok, err = False, str(exc)

    config.is_verified = ok
    config.last_verified_at = timezone.now() if ok else None
    config.last_error = '' if ok else err
    config.save(update_fields=['is_verified', 'last_verified_at', 'last_error', 'updated_at'])

    _log(workspace, request.user, 'S3 storage configured', {'bucket': bucket, 'endpoint': endpoint, 'verified': ok})

    if ok:
        messages.success(request, f'{provider_label} connected and verified. You can now activate it as the active backend.')
    else:
        messages.error(request, f'{provider_label} settings saved, but verification failed: {err}')

    return redirect('workspaces:storage_settings')


@login_required
@require_POST
def storage_s3_test(request):
    workspace, err = _resolve_storage_workspace(request)
    if err:
        return JsonResponse({'ok': False, 'error': err}, status=403)

    config = WorkspaceStorageConfig.objects.filter(workspace=workspace).first()
    if not config or not config.is_s3_configured():
        return JsonResponse({'ok': False, 'error': 'S3 is not configured yet.'}, status=400)

    from apps.media_assets.storage import S3CompatibleStorage
    try:
        backend = S3CompatibleStorage(config, user=request.user, workspace=workspace)
        ok, err = backend.test_connection()
    except Exception as exc:
        ok, err = False, str(exc)

    config.is_verified = ok
    config.last_verified_at = timezone.now() if ok else None
    config.last_error = '' if ok else err
    config.save(update_fields=['is_verified', 'last_verified_at', 'last_error', 'updated_at'])

    return JsonResponse({'ok': ok, 'error': err})


@login_required
@require_POST
def storage_s3_disconnect(request):
    workspace, err = _resolve_storage_workspace(request)
    if err:
        messages.error(request, err)
        return redirect('workspaces:list')

    config = WorkspaceStorageConfig.objects.filter(workspace=workspace).first()
    if config:
        config.s3_endpoint_url = ''
        config.s3_region = ''
        config.s3_bucket = ''
        config.s3_access_key_encrypted = ''
        config.s3_secret_key_encrypted = ''
        config.s3_public_base_url = ''
        config.s3_path_prefix = ''
        config.s3_use_path_style = True
        config.s3_provider_label = 'S3-Compatible'
        config.is_verified = False
        config.last_verified_at = None
        if config.backend == WorkspaceStorageConfig.BACKEND_S3:
            config.backend = WorkspaceStorageConfig.BACKEND_LOCAL
        config.save()
        _log(workspace, request.user, 'S3 storage cleared')

    messages.success(request, 'S3 settings cleared. Active storage reverted to local disk.')
    return redirect('workspaces:storage_settings')


@login_required
@require_POST
def storage_test(request):
    workspace, err = _resolve_storage_workspace(request)
    if err:
        return JsonResponse({'ok': False, 'error': err}, status=403)

    from apps.media_assets.storage import StorageService
    try:
        service = StorageService.for_workspace(workspace, user=request.user)
        ok, err = service.test_connection()
    except Exception as exc:
        ok, err = False, str(exc)

    return JsonResponse({'ok': ok, 'error': err, 'backend': service.backend.backend_name})


@login_required
def storage_health(request):
    workspace, err = _resolve_storage_workspace(request)
    if err:
        return JsonResponse({'ok': False, 'error': err}, status=403)
    from apps.media_assets.storage import StorageService
    service = StorageService.for_workspace(workspace, user=request.user)
    return JsonResponse({
        'backend': service.backend.backend_name,
        'is_verified': getattr(service.config, 'is_verified', False),
        'last_verified_at': service.config.last_verified_at.isoformat() if getattr(service.config, 'last_verified_at', None) else None,
        'last_error': getattr(service.config, 'last_error', '') or '',
    })



