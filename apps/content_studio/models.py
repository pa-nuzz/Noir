from django.conf import settings
from django.db import models

from core.models import AuditMixin
from core.tenant import TenantManager


ALL_PLATFORMS = ['instagram', 'facebook', 'twitter', 'linkedin', 'tiktok', 'youtube']

CONTENT_TYPE_PLATFORMS = {
    'caption': ['instagram', 'facebook', 'twitter', 'linkedin', 'tiktok'],
    'script': ['tiktok', 'youtube', 'instagram'],
    'carousel': ['instagram', 'linkedin'],
    'hashtag_set': ['instagram', 'tiktok', 'twitter'],
    'cta': ALL_PLATFORMS,
    'full_post': ALL_PLATFORMS,
    'image_prompt': ALL_PLATFORMS,
}


class ContentItem(AuditMixin):
    objects = TenantManager()
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('pending_review', 'Pending Review'),
        ('approved', 'Approved'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ]

    CONTENT_TYPES = [
        ('caption', 'Caption'),
        ('hashtag_set', 'Hashtag Set'),
        ('carousel', 'Carousel'),
        ('script', 'Script'),
        ('image_prompt', 'Image Prompt'),
        ('cta', 'Call to Action'),
        ('full_post', 'Full Post'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='content_items')
    workspace = models.ForeignKey('workspaces.Workspace', on_delete=models.CASCADE, null=True, blank=True, related_name='content_items')
    title = models.CharField(max_length=255)
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPES)
    body = models.TextField()
    platform = models.CharField(max_length=20, blank=True, help_text='Target platform (facebook, instagram, etc.)')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    tags = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    attachments = models.ManyToManyField(
        'media_assets.MediaAsset',
        blank=True,
        related_name='content_items',
    )
    scheduled_at = models.DateTimeField(null=True, blank=True)
    platform_data = models.JSONField(default=dict, blank=True)
    is_auto_generated = models.BooleanField(default=False)
    source_prompt = models.TextField(blank=True)
    excel_source = models.ForeignKey(
        'ExcelSheetImport',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='content_items',
        help_text='The Excel sheet import this content was generated from',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_content_type_display()}] {self.title[:50]}"


class ContentVersion(AuditMixin):
    content_item = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name='versions')
    version_number = models.PositiveIntegerField()
    body = models.TextField()
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version_number']
        unique_together = ('content_item', 'version_number')

    def __str__(self):
        return f"{self.content_item.title} v{self.version_number}"


class ContentApproval(AuditMixin):
    content_item = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name='approvals')
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='content_reviews')
    decision = models.CharField(max_length=20, choices=[('approved', 'Approved'), ('changes_requested', 'Changes Requested'), ('rejected', 'Rejected')])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.content_item.title} — {self.get_decision_display()} by {self.reviewer.email}"


class ExcelSheetImport(AuditMixin):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='excel_sheet_imports',
    )
    spreadsheet_id = models.CharField(max_length=255, help_text='Google Drive spreadsheet ID')
    sheet_name = models.CharField(max_length=255, default='Sheet1', help_text='Name of the sheet/tab to read')
    title = models.CharField(max_length=255, help_text='User-friendly name for this import source')
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.spreadsheet_id} - {self.sheet_name})"


class ExcelSheetRowLog(AuditMixin):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    import_source = models.ForeignKey(
        ExcelSheetImport,
        on_delete=models.CASCADE,
        related_name='row_logs',
    )
    row_number = models.PositiveIntegerField(help_text='The row number in the spreadsheet (1-indexed, including header)')
    content_item = models.ForeignKey(
        ContentItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='excel_row_logs',
    )
    social_post = models.ForeignKey(
        'social_accounts.SocialPost',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='excel_row_logs',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    platform = models.CharField(max_length=20, blank=True, help_text='Target platform for this row')
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('import_source', 'row_number')

    def __str__(self):
        return f"Row {self.row_number} - {self.get_status_display()}"


class UserGoogleSheetsToken(AuditMixin):
    """Stores OAuth credentials for a user to access their Google Sheets."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='google_sheets_token',
    )
    refresh_token = models.TextField()
    access_token = models.TextField()
    token_expiry = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Google Sheets Token for {self.user.email}"


class UserGoogleSheet(AuditMixin):
    """Tracks which Google Sheet a user has selected as their active sheet."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='google_sheets',
    )
    spreadsheet_id = models.CharField(max_length=255)
    sheet_name = models.CharField(max_length=255, default='Sheet1')
    title = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('user', 'spreadsheet_id')

    def __str__(self):
        return f"{self.title} ({self.spreadsheet_id})"


class DeletedDriveSheet(AuditMixin):
    """Tracks spreadsheet IDs that should be hidden from the Drive list
    because the user deleted them from the app and Drive delete failed."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='deleted_drive_sheets',
    )
    spreadsheet_id = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'spreadsheet_id')
