import logging
from typing import List, Optional

from django.conf import settings

from ..models import UserGoogleSheetsToken

logger = logging.getLogger(__name__)


class GoogleSheetsService:
    """Read from and write to Google Sheets using OAuth tokens.

    Supports two credential sources:
    1. Per-user tokens stored in UserGoogleSheetsToken (legacy, app-level credentials).
    2. Per-workspace tokens stored in WorkspaceStorageConfig (encrypted, user-provided
       client ID/secret — same pattern as Google Drive storage).

    Pass a ``workspace`` to use workspace-level credentials, or a ``user`` to use
    the legacy per-user token approach.
    """

    def __init__(self, user=None, workspace=None):
        """
        :param user:      Django user (required for legacy per-user token path).
        :param workspace: Workspace whose storage config holds encrypted credentials.
        """
        self.user = user
        self.workspace = workspace
        self._config = None
        self._token = None
        self._service = None

    def _get_workspace_config(self):
        if self._config is None:
            if not self.workspace:
                raise RuntimeError('No workspace provided for Sheets credentials lookup.')
            from apps.workspaces.models import WorkspaceStorageConfig
            try:
                self._config = WorkspaceStorageConfig.objects.get(workspace=self.workspace)
            except WorkspaceStorageConfig.DoesNotExist:
                raise RuntimeError(
                    'Google Sheets is not configured for this workspace.'
                )
            if not self._config.is_google_sheets_connected():
                raise RuntimeError(
                    'Google Sheets is not connected. Please connect your Google account.'
                )
        return self._config

    def _get_token(self):
        if self._token is None:
            try:
                self._token = UserGoogleSheetsToken.objects.get(user=self.user)
            except UserGoogleSheetsToken.DoesNotExist:
                raise RuntimeError(
                    'Google Sheets is not connected. Please connect your Google account.'
                )
        return self._token

    def _build_credentials(self):
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        # Use workspace-level credentials if a workspace is given
        if self.workspace:
            config = self._get_workspace_config()
            creds = Credentials(
                token=config.google_sheets_access_token or None,
                refresh_token=config.get_google_sheets_refresh_token(),
                token_uri='https://oauth2.googleapis.com/token',
                client_id=config.get_google_sheets_client_id(),
                client_secret=config.get_google_sheets_client_secret(),
                scopes=settings.GOOGLE_SHEETS_SCOPES,
            )
            _request = Request()
            if creds.expired or not creds.valid:
                creds.refresh(_request)
                config.google_sheets_access_token = creds.token or ''
                config.google_sheets_token_expiry = creds.expiry
                config.save(update_fields=['google_sheets_access_token', 'google_sheets_token_expiry', 'updated_at'])
            return creds

        # Fall back to legacy per-user token
        token = self._get_token()

        creds = Credentials(
            token=token.access_token or None,
            refresh_token=token.refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=settings.GOOGLE_SHEETS_CLIENT_ID,
            client_secret=settings.GOOGLE_SHEETS_CLIENT_SECRET,
            scopes=settings.GOOGLE_SHEETS_SCOPES,
        )
        _request = Request()
        if creds.expired or not creds.valid:
            creds.refresh(_request)
            token.access_token = creds.token or ''
            token.token_expiry = creds.expiry
            token.save(update_fields=['access_token', 'token_expiry'])
        return creds

    def _get_service(self):
        if self._service is None:
            from googleapiclient.discovery import build
            creds = self._build_credentials()
            self._service = build('sheets', 'v4', credentials=creds, cache_discovery=False)
        return self._service

    def list_spreadsheets(self) -> List[dict]:
        """Return a list of the user's Google Sheets."""
        from googleapiclient.discovery import build
        creds = self._build_credentials()
        drive_service = build('drive', 'v3', credentials=creds, cache_discovery=False)
        results = drive_service.files().list(
            q="mimeType='application/vnd.google-apps.spreadsheet'",
            spaces='drive',
            fields='files(id, name, modifiedTime)',
        ).execute()
        return results.get('files', [])

    def delete_spreadsheet(self, spreadsheet_id: str) -> bool:
        """Delete a spreadsheet from Google Drive. Returns True on success."""
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        try:
            creds = self._build_credentials()
            drive_service = build('drive', 'v3', credentials=creds, cache_discovery=False)
            drive_service.files().delete(fileId=spreadsheet_id).execute()
            return True
        except HttpError as exc:
            logger.warning("Failed to delete spreadsheet %s from Drive: %s", spreadsheet_id, exc)
            return False

    def create_sheet(self, title='Content Generator') -> dict:
        """
        Create a new Google Sheet with the required headers:
        S.N., Description, URL, Images, Platform, Content Link, Status
        """
        service = self._get_service()
        body = {
            'properties': {
                'title': title,
            },
            'sheets': [
                {
                    'properties': {
                        'title': 'Sheet1',
                        'gridProperties': {
                            'frozenRowCount': 1,  # Freeze header row
                        },
                    },
                }
            ],
        }
        spreadsheet = service.spreadsheets().create(body=body).execute()
        spreadsheet_id = spreadsheet['spreadsheetId']

        # Write headers
        self._write_headers(spreadsheet_id, 'Sheet1')

        # Apply dropdown validation and pre-fill Status column with "Pending"
        self.apply_data_validation(spreadsheet_id, 'Sheet1', fill_defaults=True)

        return {
            'spreadsheetId': spreadsheet_id,
            'spreadsheetUrl': f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
        }

    def _write_headers(self, spreadsheet_id: str, sheet_name: str):
        headers = ['S.N.', 'Description', 'URL', 'Images', 'Platform', 'Content Link', 'Status']
        body = {
            'values': [headers]
        }
        service = self._get_service()
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1:G1",
            valueInputOption='RAW',
            body=body,
        ).execute()

    def _get_sheet_id(self, spreadsheet_id: str, sheet_name: str = 'Sheet1') -> Optional[int]:
        """Get the numeric sheet ID for a given sheet tab name."""
        service = self._get_service()
        metadata = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            ranges=[],
            includeGridData=False,
        ).execute()
        for sheet in metadata.get('sheets', []):
            props = sheet.get('properties', {})
            if props.get('title') == sheet_name:
                return props.get('sheetId')
        return None

    def apply_data_validation(self, spreadsheet_id: str, sheet_name: str = 'Sheet1', fill_defaults: bool = False):
        """Add dropdown data validation to Platform (E) and Status (G) columns.

        When *fill_defaults* is ``True``, also pre-fills the Status column (G)
        with "Pending" for rows 2-5000 so new rows automatically show "Pending".
        This should only be ``True`` when the sheet is first created.
        """
        from googleapiclient.errors import HttpError

        sheet_id = self._get_sheet_id(spreadsheet_id, sheet_name)
        if sheet_id is None:
            logger.warning("apply_data_validation: sheet '%s' not found in %s", sheet_name, spreadsheet_id)
            return

        platform_options = [
            'All Platforms',
            'facebook', 'instagram', 'twitter',
            'linkedin', 'tiktok', 'youtube',
        ]
        status_options = ['Pending', 'Completed']

        service = self._get_service()
        requests = [
            {
                "setDataValidation": {
                    "range": {
                        "sheetId": sheet_id,
                        "startColumnIndex": 4,
                        "endColumnIndex": 5,
                        "startRowIndex": 1,
                    },
                    "rule": {
                        "condition": {
                            "type": "ONE_OF_LIST",
                            "values": [{"userEnteredValue": v} for v in platform_options],
                        },
                        "showCustomUi": True,
                        "strict": True,
                    },
                }
            },
            {
                "setDataValidation": {
                    "range": {
                        "sheetId": sheet_id,
                        "startColumnIndex": 6,
                        "endColumnIndex": 7,
                        "startRowIndex": 1,
                    },
                    "rule": {
                        "condition": {
                            "type": "ONE_OF_LIST",
                            "values": [{"userEnteredValue": v} for v in status_options],
                        },
                        "showCustomUi": True,
                        "strict": True,
                    },
                }
            },
        ]

        if fill_defaults:
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startColumnIndex": 6,
                        "endColumnIndex": 7,
                        "startRowIndex": 1,
                        "endRowIndex": 5000,
                    },
                    "cell": {"userEnteredValue": {"stringValue": "Pending"}},
                    "fields": "userEnteredValue",
                }
            })

        body = {"requests": requests}
        try:
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body=body,
            ).execute()
        except HttpError as exc:
            logger.warning("Failed to apply data validation: %s", exc)

    def ensure_headers(self, spreadsheet_id: str, sheet_name: str = 'Sheet1'):
        """Create headers if row 1 is empty."""
        try:
            rows = self.read_rows(spreadsheet_id, sheet_name)
            if not rows or not rows[0]:
                self._write_headers(spreadsheet_id, sheet_name)
        except Exception:
            # If reading fails, try writing headers anyway
            self._write_headers(spreadsheet_id, sheet_name)

    def read_rows(self, spreadsheet_id: str, sheet_name: str = 'Sheet1') -> List[List[str]]:
        service = self._get_service()
        range_str = f"{sheet_name}!A:Z"
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_str,
        ).execute()
        return result.get('values', [])

    def write_cell(self, spreadsheet_id: str, sheet_name: str, row: int, col: int, value: str) -> None:
        service = self._get_service()
        cell_range = self._cell_ref(row, col)
        body = {
            'values': [[value]]
        }
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!{cell_range}",
            valueInputOption='RAW',
            body=body,
        ).execute()

    def write_cells(self, spreadsheet_id: str, sheet_name: str, cell_range: str, values: List[List[str]]) -> None:
        service = self._get_service()
        body = {
            'values': values
        }
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=cell_range,
            valueInputOption='RAW',
            body=body,
        ).execute()

    @staticmethod
    def _cell_ref(row: int, col: int) -> str:
        """Convert 1-indexed row/col to A1 notation."""
        col_str = ''
        while col > 0:
            col, remainder = divmod(col - 1, 26)
            col_str = chr(65 + remainder) + col_str
        return f"{col_str}{row}"
