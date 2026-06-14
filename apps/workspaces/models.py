import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from .encryption import decrypt_secret, encrypt_secret


class Workspace(models.Model):
    PLAN_CHOICES = [
        ('free', 'Free'),
        ('pro', 'Pro'),
        ('enterprise', 'Enterprise'),
    ]

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_workspaces')
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='free')
    stripe_customer_id = models.CharField(max_length=255, blank=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def plan_display(self):
        return dict(self.PLAN_CHOICES).get(self.plan, 'Free')

    @property
    def is_trial_active(self):
        if self.trial_ends_at is None:
            return False
        from django.utils import timezone
        return timezone.now() < self.trial_ends_at

    def get_plan_limits(self):
        from django.conf import settings
        return settings.PLAN_LIMITS.get(self.plan, settings.PLAN_LIMITS['free'])

    def quota(self):
        return WorkspaceQuota.objects.get_or_create(workspace=self)[0]


class WorkspaceMembership(models.Model):
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('admin', 'Admin'),
        ('member', 'Member'),
    ]

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='workspace_memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('workspace', 'user')
        verbose_name_plural = 'Workspace memberships'

    def __str__(self):
        return f"{self.user.email} — {self.workspace.name} ({self.get_role_display()})"


class TeamInvitation(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
    ]

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField()
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_invitations')
    role = models.CharField(max_length=20, choices=WorkspaceMembership.ROLE_CHOICES, default='member')
    token = models.CharField(max_length=64, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    message = models.TextField(blank=True, help_text='Optional personal message')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    notified_inviter = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(48)
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Invite {self.email} → {self.workspace.name}"

    def is_expired(self):
        return timezone.now() >= self.expires_at


class AuditLog(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='audit_logs')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='workspace_audit_logs')
    action = models.CharField(max_length=255)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Audit log entry'
        verbose_name_plural = 'Audit logs'

    def __str__(self):
        return f"[{self.workspace.name}] {self.action} @ {self.created_at.date()}"


class WorkspaceSocialAccount(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='shared_accounts')
    account = models.ForeignKey('social_accounts.SocialAccount', on_delete=models.CASCADE, related_name='workspace_links')
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='added_workspace_accounts')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('workspace', 'account')
        verbose_name = 'Workspace social account'
        verbose_name_plural = 'Workspace social accounts'

    def __str__(self):
        return f"{self.account} → {self.workspace.name}"


class WorkspacePermission(models.Model):
    MODULE_CHOICES = [
        ('campaigns', 'Campaigns'),
        ('contacts', 'Contacts'),
        ('social', 'Social'),
        ('media', 'Media'),
        ('workflows', 'Workflows'),
        ('inbox', 'Inbox'),
        ('content_studio', 'Content Studio'),
        ('workspace', 'Workspace Settings'),
        ('billing', 'Billing'),
        ('audit_log', 'Audit Log'),
        ('storage', 'Storage'),
        ('members', 'Members'),
        ('export', 'Export Data'),
    ]

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='permissions')
    role = models.CharField(max_length=20, choices=WorkspaceMembership.ROLE_CHOICES)
    module = models.CharField(max_length=30, choices=MODULE_CHOICES)
    can_read = models.BooleanField(default=True)
    can_create = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('workspace', 'role', 'module')
        verbose_name = 'Workspace permission'
        verbose_name_plural = 'Workspace permissions'

    def __str__(self):
        return f"{self.workspace.name} — {self.get_role_display()} — {self.get_module_display()}"

    @classmethod
    def get_role_permissions(cls, workspace, role):
        """Return a dict of {module: {read, create, edit, delete}} for a given role."""
        perms = cls.objects.filter(workspace=workspace, role=role)
        return {
            p.module: {
                'read': p.can_read,
                'create': p.can_create,
                'edit': p.can_edit,
                'delete': p.can_delete,
            }
            for p in perms
        }

    @classmethod
    def user_permissions_dict(cls, workspace, user):
        """Return permissions dict for a user's role in a workspace."""
        membership = WorkspaceMembership.objects.filter(workspace=workspace, user=user).first()
        if not membership:
            return {}
        return cls.get_role_permissions(workspace, membership.role)


DEFAULT_PERMISSIONS = {
    'owner': {
        'campaigns': {'read': True, 'create': True, 'edit': True, 'delete': True},
        'contacts': {'read': True, 'create': True, 'edit': True, 'delete': True},
        'social': {'read': True, 'create': True, 'edit': True, 'delete': True},
        'media': {'read': True, 'create': True, 'edit': True, 'delete': True},
        'workflows': {'read': True, 'create': True, 'edit': True, 'delete': True},
        'inbox': {'read': True, 'create': True, 'edit': True, 'delete': True},
        'content_studio': {'read': True, 'create': True, 'edit': True, 'delete': True},
        'workspace': {'read': True, 'create': True, 'edit': True, 'delete': True},
        'billing': {'read': True, 'create': True, 'edit': True, 'delete': True},
        'audit_log': {'read': True, 'create': True, 'edit': True, 'delete': True},
        'storage': {'read': True, 'create': True, 'edit': True, 'delete': True},
        'members': {'read': True, 'create': True, 'edit': True, 'delete': True},
        'export': {'read': True, 'create': True, 'edit': True, 'delete': True},
    },
    'admin': {
        'campaigns': {'read': True, 'create': True, 'edit': True, 'delete': True},
        'contacts': {'read': True, 'create': True, 'edit': True, 'delete': True},
        'social': {'read': True, 'create': True, 'edit': True, 'delete': True},
        'media': {'read': True, 'create': True, 'edit': True, 'delete': True},
        'workflows': {'read': True, 'create': True, 'edit': True, 'delete': False},
        'inbox': {'read': True, 'create': True, 'edit': True, 'delete': False},
        'content_studio': {'read': True, 'create': True, 'edit': True, 'delete': True},
        'workspace': {'read': True, 'create': False, 'edit': True, 'delete': False},
        'billing': {'read': True, 'create': False, 'edit': False, 'delete': False},
        'audit_log': {'read': True, 'create': False, 'edit': False, 'delete': False},
        'storage': {'read': True, 'create': False, 'edit': True, 'delete': False},
        'members': {'read': True, 'create': True, 'edit': True, 'delete': False},
        'export': {'read': True, 'create': True, 'edit': True, 'delete': True},
    },
    'member': {
        'campaigns': {'read': True, 'create': True, 'edit': True, 'delete': False},
        'contacts': {'read': True, 'create': True, 'edit': True, 'delete': False},
        'social': {'read': True, 'create': True, 'edit': True, 'delete': False},
        'media': {'read': True, 'create': True, 'edit': True, 'delete': False},
        'workflows': {'read': True, 'create': False, 'edit': False, 'delete': False},
        'inbox': {'read': True, 'create': True, 'edit': True, 'delete': False},
        'content_studio': {'read': True, 'create': True, 'edit': True, 'delete': False},
        'workspace': {'read': True, 'create': False, 'edit': False, 'delete': False},
        'billing': {'read': True, 'create': False, 'edit': False, 'delete': False},
        'audit_log': {'read': True, 'create': False, 'edit': False, 'delete': False},
        'storage': {'read': True, 'create': False, 'edit': False, 'delete': False},
        'members': {'read': True, 'create': False, 'edit': False, 'delete': False},
        'export': {'read': True, 'create': True, 'edit': True, 'delete': True},
    },
    
}


def seed_default_permissions(workspace):
    """Create default permission rows for all roles in a workspace."""
    field_map = {'read': 'can_read', 'create': 'can_create', 'edit': 'can_edit', 'delete': 'can_delete'}
    for role, modules in DEFAULT_PERMISSIONS.items():
        for module, perms in modules.items():
            defaults = {field_map[k]: v for k, v in perms.items()}
            WorkspacePermission.objects.get_or_create(
                workspace=workspace,
                role=role,
                module=module,
                defaults=defaults,
            )
class WorkspaceStorageConfig(models.Model):
    BACKEND_LOCAL = 'local'
    BACKEND_DIA_S3 = 'dia_s3'
    BACKEND_GOOGLE_DRIVE = 'google_drive'
    BACKEND_S3 = 's3_compatible'

    BACKEND_CHOICES = [
        (BACKEND_LOCAL, 'Local Disk'),
        (BACKEND_DIA_S3, 'DIA Managed S3'),
        (BACKEND_GOOGLE_DRIVE, 'Google Drive'),
        (BACKEND_S3, 'S3-Compatible (AWS S3 / R2 / MinIO / Wasabi / etc.)'),
    ]

    workspace = models.OneToOneField(
        Workspace,
        on_delete=models.CASCADE,
        related_name='storage_config',
    )
    backend = models.CharField(max_length=20, choices=BACKEND_CHOICES, default=BACKEND_LOCAL)

    google_drive_client_id_encrypted = models.TextField(blank=True)
    google_drive_client_secret_encrypted = models.TextField(blank=True)
    google_drive_refresh_token_encrypted = models.TextField(blank=True)
    google_drive_access_token = models.TextField(blank=True)
    google_drive_token_expiry = models.DateTimeField(null=True, blank=True)
    google_drive_folder_id = models.CharField(max_length=128, blank=True)
    google_drive_folder_name = models.CharField(max_length=255, blank=True)
    google_drive_connected_email = models.EmailField(blank=True)

    google_sheets_client_id_encrypted = models.TextField(blank=True)
    google_sheets_client_secret_encrypted = models.TextField(blank=True)
    google_sheets_refresh_token_encrypted = models.TextField(blank=True)
    google_sheets_access_token = models.TextField(blank=True)
    google_sheets_token_expiry = models.DateTimeField(null=True, blank=True)
    google_sheets_spreadsheet_id = models.CharField(max_length=128, blank=True)
    google_sheets_spreadsheet_name = models.CharField(max_length=255, blank=True, default='Content Generator')
    google_sheets_connected_email = models.EmailField(blank=True)

    s3_endpoint_url = models.URLField(blank=True)
    s3_region = models.CharField(max_length=64, blank=True, default='us-east-1')
    s3_bucket = models.CharField(max_length=128, blank=True)
    s3_access_key_encrypted = models.TextField(blank=True)
    s3_secret_key_encrypted = models.TextField(blank=True)
    s3_path_prefix = models.CharField(max_length=255, blank=True, default='')
    s3_public_base_url = models.URLField(blank=True, help_text='Optional CDN/public base URL prepended to keys.')
    s3_use_path_style = models.BooleanField(default=True)
    s3_provider_label = models.CharField(max_length=64, blank=True, default='S3-Compatible')

    storage_used_mb = models.IntegerField(default=0, help_text='Latest calculated storage usage in MB')
    storage_last_checked_at = models.DateTimeField(null=True, blank=True)

    is_verified = models.BooleanField(default=False)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Workspace storage config'
        verbose_name_plural = 'Workspace storage configs'

    def __str__(self):
        return f"{self.workspace.name} → {self.get_backend_display()}"

    def set_google_drive_client_id(self, client_id):
        self.google_drive_client_id_encrypted = encrypt_secret(client_id or '')

    def get_google_drive_client_id(self):
        return decrypt_secret(self.google_drive_client_id_encrypted)

    def set_google_drive_client_secret(self, client_secret):
        self.google_drive_client_secret_encrypted = encrypt_secret(client_secret or '')

    def get_google_drive_client_secret(self):
        return decrypt_secret(self.google_drive_client_secret_encrypted)

    def set_google_drive_refresh_token(self, token):
        self.google_drive_refresh_token_encrypted = encrypt_secret(token or '')

    def get_google_drive_refresh_token(self):
        return decrypt_secret(self.google_drive_refresh_token_encrypted)

    def set_s3_access_key(self, key):
        self.s3_access_key_encrypted = encrypt_secret(key or '')

    def get_s3_access_key(self):
        return decrypt_secret(self.s3_access_key_encrypted)

    def set_s3_secret_key(self, key):
        self.s3_secret_key_encrypted = encrypt_secret(key or '')

    def get_s3_secret_key(self):
        return decrypt_secret(self.s3_secret_key_encrypted)

    def is_google_drive_connected(self):
        return (
            self.backend == self.BACKEND_GOOGLE_DRIVE
            and bool(self.get_google_drive_refresh_token())
        )

    def is_google_drive_credentials_configured(self):
        return bool(
            self.get_google_drive_client_id()
            and self.get_google_drive_client_secret()
        )

    def set_google_sheets_client_id(self, client_id):
        self.google_sheets_client_id_encrypted = encrypt_secret(client_id or '')

    def get_google_sheets_client_id(self):
        return decrypt_secret(self.google_sheets_client_id_encrypted)

    def set_google_sheets_client_secret(self, client_secret):
        self.google_sheets_client_secret_encrypted = encrypt_secret(client_secret or '')

    def get_google_sheets_client_secret(self):
        return decrypt_secret(self.google_sheets_client_secret_encrypted)

    def set_google_sheets_refresh_token(self, token):
        self.google_sheets_refresh_token_encrypted = encrypt_secret(token or '')

    def get_google_sheets_refresh_token(self):
        return decrypt_secret(self.google_sheets_refresh_token_encrypted)

    def is_google_sheets_connected(self):
        return bool(self.get_google_sheets_refresh_token())

    def is_google_sheets_credentials_configured(self):
        return bool(
            self.get_google_sheets_client_id()
            and self.get_google_sheets_client_secret()
        )

    def is_s3_configured(self):
        return (
            self.backend == self.BACKEND_S3
            and bool(self.s3_bucket)
            and bool(self.get_s3_access_key())
            and bool(self.get_s3_secret_key())
        )

    def mask_secret(self, ciphertext):
        if not ciphertext:
            return ''
        return '••••••••' + (ciphertext[-4:] if len(ciphertext) >= 4 else '')


class WorkspaceQuota(models.Model):
    workspace = models.OneToOneField(Workspace, on_delete=models.CASCADE, related_name='_quota')
    emails_sent_this_month = models.PositiveIntegerField(default=0)
    ai_credits_used = models.PositiveIntegerField(default=0)
    storage_bytes_used = models.BigIntegerField(default=0)
    month_reset_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Workspace quotas'

    def __str__(self):
        return f"Quota for {self.workspace.name}"

    def check_emails_available(self, count=1):
        limit = self.workspace.get_plan_limits().get('emails_per_month')
        if limit is None:
            return True
        return (self.emails_sent_this_month + count) <= limit

    def check_ai_credits_available(self, count=1):
        limit = self.workspace.get_plan_limits().get('ai_credits')
        if limit is None:
            return True
        return (self.ai_credits_used + count) <= limit

    def check_storage_available(self, bytes_needed):
        limit_gb = self.workspace.get_plan_limits().get('storage_gb')
        if limit_gb is None:
            return True
        limit_bytes = limit_gb * 1024 * 1024 * 1024
        return (self.storage_bytes_used + bytes_needed) <= limit_bytes

    def check_team_seats_available(self, current_members=None):
        limit = self.workspace.get_plan_limits().get('team_seats')
        if limit is None:
            return True
        if current_members is None:
            current_members = WorkspaceMembership.objects.filter(workspace=self.workspace).count()
        return current_members < limit

    def increment_emails_sent(self, count=1):
        WorkspaceQuota.objects.filter(pk=self.pk).update(
            emails_sent_this_month=models.F('emails_sent_this_month') + count
        )

    def increment_ai_credits(self, count=1):
        WorkspaceQuota.objects.filter(pk=self.pk).update(
            ai_credits_used=models.F('ai_credits_used') + count
        )

    def reset_monthly_if_needed(self):
        from django.utils import timezone
        now = timezone.now()
        if self.month_reset_at and self.month_reset_at.month == now.month and self.month_reset_at.year == now.year:
            return
        self.emails_sent_this_month = 0
        self.ai_credits_used = 0
        self.month_reset_at = now
        self.save(update_fields=['emails_sent_this_month', 'ai_credits_used', 'month_reset_at'])


def get_or_create_personal_workspace(user, workspace_name=None):
    membership = (
        WorkspaceMembership.objects
        .filter(user=user)
        .select_related('workspace')
        .order_by('workspace__created_at')
        .first()
    )
    if membership:
        return membership.workspace

    name = workspace_name or f"{user.get_full_name() or user.email}'s Workspace"
    workspace = Workspace.objects.create(name=name, created_by=user)
    WorkspaceMembership.objects.create(workspace=workspace, user=user, role='owner')
    return workspace
