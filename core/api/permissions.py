from rest_framework.permissions import BasePermission, SAFE_METHODS

from apps.api_keys.models import WorkspaceAPIKey


class TenantPermission(BasePermission):
    """Ensures the requested workspace matches the authenticated user's tenant.

    For session-auth: uses request.tenant (set by TenantMiddleware).
    For API-key auth: uses the workspace associated with the API key.
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        tenant = getattr(request, 'tenant', None)
        if tenant is None:
            return False
        return True

    def has_object_permission(self, request, view, obj):
        tenant = getattr(request, 'tenant', None)
        if tenant is None:
            return False
        ws_field = getattr(view, 'workspace_field', 'workspace')
        ownee = getattr(obj, ws_field, None)
        if ownee is None:
            return False
        if hasattr(ownee, 'pk'):
            return ownee.pk == tenant.pk
        return ownee == tenant.pk


class TenantModelPermission(BasePermission):
    """Combines TenantPermission with Django's standard model permissions."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        tenant = getattr(request, 'tenant', None)
        if tenant is None:
            return False
        if request.user.is_superuser:
            return True
        return True

    def has_object_permission(self, request, view, obj):
        tenant = getattr(request, 'tenant', None)
        if tenant is None:
            return False
        ws_field = getattr(view, 'workspace_field', 'workspace')
        ownee = getattr(obj, ws_field, None)
        if ownee is None:
            return False
        if hasattr(ownee, 'pk'):
            return ownee.pk == tenant.pk
        return ownee == tenant.pk


class IsWorkspaceAdminOrReadOnly(BasePermission):
    """Admin/member can write;"""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        membership = getattr(request, 'active_membership', None)
        if membership and membership.role in ('owner', 'admin'):
            return True
        return False
