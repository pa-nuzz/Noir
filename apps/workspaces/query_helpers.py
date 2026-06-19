from .models import WorkspaceMembership
from core.tenant import get_current_tenant


def filter_by_context(request, queryset, user_field='user', workspace_field='workspace'):
    """Apply workspace or personal scoping to any queryset.

    Usage:
        posts = filter_by_context(request, SocialPost.objects.all())
        campaigns = filter_by_context(request, Campaign.objects.all())

    When an active workspace is set, filters by workspace_id.
    When in personal mode (no active workspace), filters by user.
    Superusers bypass all scoping.

    Note: The TenantMiddleware + TenantManager combo already auto-scopes
    querysets at the model level when a tenant is active. This function
    remains as an explicit safety net, especially for personal mode.
    """
    user = request.user
    if user.is_superuser or user.is_staff:
        return queryset

    tenant = get_current_tenant()
    if tenant is not None:
        if hasattr(queryset.model, workspace_field):
            return queryset.filter(**{workspace_field: tenant})
        return queryset.filter(**{user_field: user})

    active_ws_id = request.session.get('active_workspace_id')
    if active_ws_id:
        if not WorkspaceMembership.objects.filter(
            workspace_id=active_ws_id, user=user
        ).exists():
            return queryset.none()
        if hasattr(queryset.model, workspace_field):
            return queryset.filter(**{workspace_field: active_ws_id})
        return queryset.filter(**{user_field: user})

    if hasattr(queryset.model, workspace_field):
        return queryset.filter(**{user_field: user}, **{workspace_field + '__isnull': True})
    return queryset.filter(**{user_field: user})