import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.workspaces.models import Workspace, WorkspaceMembership, WorkspaceStorageConfig, get_or_create_personal_workspace

from .models import UserGoogleSheetsToken

logger = logging.getLogger(__name__)

OAUTH_STATE_SALT = 'content-studio-sheets-oauth'
OAUTH_STATE_MAX_AGE = 60 * 15


def _signed_state(workspace_id):
    return signing.dumps({'workspace_id': workspace_id}, salt=OAUTH_STATE_SALT)


def _unsign_state(state):
    try:
        return signing.loads(state, salt=OAUTH_STATE_SALT, max_age=OAUTH_STATE_MAX_AGE)
    except (signing.BadSignature, signing.SignatureExpired):
        return None


def _require_workspace_member(user, workspace):
    return WorkspaceMembership.objects.filter(workspace=workspace, user=user).exists()


@login_required
@require_POST
def google_sheets_save_credentials(request):
    """Save the user's Google OAuth Client ID and Client Secret (encrypted) for their workspace."""
    workspace = get_or_create_personal_workspace(request.user)
    if not _require_workspace_member(request.user, workspace):
        return JsonResponse({'ok': False, 'error': 'Forbidden'}, status=403)
    if request.user != workspace.created_by and not WorkspaceMembership.objects.filter(
        workspace=workspace, user=request.user, role__in=('owner', 'admin')
    ).exists():
        messages.error(request, 'Only workspace owners and admins can change Google Sheets credentials.')
        return redirect('content_studio:excel_sheets')

    client_id = (request.POST.get('google_sheets_client_id') or '').strip()
    client_secret = (request.POST.get('google_sheets_client_secret') or '').strip()

    config, _ = WorkspaceStorageConfig.objects.get_or_create(workspace=workspace)

    had_id = bool(config.get_google_sheets_client_id())
    had_secret = bool(config.get_google_sheets_client_secret())

    if client_id:
        config.set_google_sheets_client_id(client_id)
    if client_secret:
        config.set_google_sheets_client_secret(client_secret)

    if not client_id and not client_secret and not had_id and not had_secret:
        messages.error(request, 'Please provide a Google OAuth Client ID and Client Secret.')
        return redirect('content_studio:excel_sheets')

    if not config.get_google_sheets_client_id() or not config.get_google_sheets_client_secret():
        messages.error(request, 'Both Client ID and Client Secret are required.')
        return redirect('content_studio:excel_sheets')

    config.last_error = ''
    config.save()

    if config.is_google_sheets_connected():
        config.is_verified = False
        config.save(update_fields=['is_verified', 'updated_at'])
        messages.success(request, 'Credentials saved. Please reconnect your Google Sheets account to refresh the access token.')
    else:
        messages.success(request, 'Google Sheets credentials saved. You can now connect your account.')

    return redirect('content_studio:excel_sheets')


@login_required
def google_sheets_auth_start(request):
    """Redirect the user to Google OAuth to authorize Sheets access."""
    workspace = get_or_create_personal_workspace(request.user)
    if not _require_workspace_member(request.user, workspace):
        return JsonResponse({'ok': False, 'error': 'Forbidden'}, status=403)

    config = WorkspaceStorageConfig.objects.filter(workspace=workspace).first()
    if not config or not config.is_google_sheets_credentials_configured():
        messages.error(request, 'Save your Google OAuth Client ID and Client Secret first, then come back to connect.')
        return redirect('content_studio:excel_sheets')

    client_id = config.get_google_sheets_client_id()

    state = _signed_state(workspace.id)
    params = {
        'client_id': client_id,
        'redirect_uri': settings.GOOGLE_SHEETS_REDIRECT_URI,
        'response_type': 'code',
        'scope': ' '.join(settings.GOOGLE_SHEETS_SCOPES),
        'access_type': 'offline',
        'prompt': 'consent',
        'include_granted_scopes': 'true',
        'state': state,
    }
    auth_url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(params)
    return HttpResponseRedirect(auth_url)


@login_required
def google_sheets_auth_callback(request):
    """Handle the OAuth callback from Google and store tokens in WorkspaceStorageConfig."""
    error = request.GET.get('error')
    if error:
        messages.error(request, f'Google Sheets authorization was cancelled or failed: {error}')
        return redirect('content_studio:excel_sheets')

    code = request.GET.get('code')
    state = request.GET.get('state', '')
    payload = _unsign_state(state) if state else None
    if not code or not payload:
        messages.error(request, 'Invalid OAuth callback. Please try again.')
        return redirect('content_studio:excel_sheets')

    workspace = get_object_or_404(Workspace, id=payload['workspace_id'])
    if not _require_workspace_member(request.user, workspace):
        return JsonResponse({'ok': False, 'error': 'Forbidden'}, status=403)

    config = WorkspaceStorageConfig.objects.filter(workspace=workspace).first()
    if not config or not config.is_google_sheets_credentials_configured():
        messages.error(request, 'Your Google OAuth credentials are missing. Save them and try connecting again.')
        return redirect('content_studio:excel_sheets')

    client_id = config.get_google_sheets_client_id()
    client_secret = config.get_google_sheets_client_secret()

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
            scopes=settings.GOOGLE_SHEETS_SCOPES,
        )
        flow.redirect_uri = settings.GOOGLE_SHEETS_REDIRECT_URI
        flow.fetch_token(code=code)
        creds = flow.credentials

        # Get the connected user's email
        drive_service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        about = drive_service.about().get(fields='user').execute()
        user_email = about.get('user', {}).get('emailAddress', '')

        # Create a default Google Sheet with required headers
        sheets_service = build('sheets', 'v4', credentials=creds, cache_discovery=False)
        sheet_title = 'Content Generator'
        body = {
            'properties': {'title': sheet_title},
            'sheets': [
                {
                    'properties': {
                        'title': 'Sheet1',
                        'gridProperties': {'frozenRowCount': 1},
                    },
                }
            ],
        }
        spreadsheet = sheets_service.spreadsheets().create(body=body).execute()
        spreadsheet_id = spreadsheet['spreadsheetId']

        # Write headers: S.N., Description, URL, Images, Platform, Content Link, Status
        headers = ['S.N.', 'Description', 'URL', 'Images', 'Platform', 'Content Link', 'Status']
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range='Sheet1!A1:G1',
            valueInputOption='RAW',
            body={'values': [headers]},
        ).execute()

        config.set_google_sheets_refresh_token(creds.refresh_token or '')
        config.google_sheets_access_token = creds.token or ''
        config.google_sheets_token_expiry = creds.expiry
        config.google_sheets_spreadsheet_id = spreadsheet_id
        config.google_sheets_spreadsheet_name = sheet_title
        config.google_sheets_connected_email = user_email
        config.is_verified = True
        config.last_verified_at = timezone.now()
        config.last_error = ''
        config.save()

        messages.success(
            request,
            f'Google Sheet connected as {user_email}. A "{sheet_title}" sheet has been created in your Google Drive.',
        )
    except Exception as exc:
        logger.exception('Google Sheets OAuth failed')
        config = WorkspaceStorageConfig.objects.filter(workspace=workspace).first()
        if config:
            config.last_error = str(exc)
            config.is_verified = False
            config.save(update_fields=['last_error', 'is_verified', 'updated_at'])
        messages.error(request, f'Google Sheets connection failed: {exc}')

    return redirect('content_studio:excel_sheets')


@login_required
@require_POST
def google_sheets_auth_disconnect(request):
    """Disconnect the workspace Google Sheets connection."""
    workspace = get_or_create_personal_workspace(request.user)
    if not _require_workspace_member(request.user, workspace):
        return JsonResponse({'ok': False, 'error': 'Forbidden'}, status=403)

    config = WorkspaceStorageConfig.objects.filter(workspace=workspace).first()
    if config:
        config.google_sheets_refresh_token_encrypted = ''
        config.google_sheets_access_token = ''
        config.google_sheets_token_expiry = None
        config.google_sheets_spreadsheet_id = ''
        config.google_sheets_spreadsheet_name = ''
        config.google_sheets_connected_email = ''
        config.is_verified = False
        config.save()

    # Also clean up legacy per-user token if it exists
    UserGoogleSheetsToken.objects.filter(user=request.user).delete()

    messages.success(request, 'Google Sheets disconnected.')
    return redirect('content_studio:excel_sheets')
