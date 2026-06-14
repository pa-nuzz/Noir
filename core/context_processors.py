from django.conf import settings
from django.db.models import Count, OuterRef, Subquery
from apps.workspaces.models import Workspace, WorkspaceMembership, WorkspacePermission


def static_version(request):
    return {
        'STATIC_VERSION': getattr(settings, 'STATIC_VERSION', '1'),
    }


def active_workspace(request):
    if not request.user.is_authenticated:
        return {
            'active_workspace': None,
            'active_membership': None,
            'user_workspaces': None,
            'workspace_permissions': None,
        }

    ws_id = request.session.get('active_workspace_id')
    active_workspace = None
    active_membership = None
    workspace_permissions = None

    if ws_id:
        membership = WorkspaceMembership.objects.filter(
            workspace_id=ws_id, user=request.user
        ).select_related('workspace').first()
        if membership:
            active_workspace = membership.workspace
            active_membership = membership
            workspace_permissions = WorkspacePermission.user_permissions_dict(
                membership.workspace, request.user
            )

    membership_counts = WorkspaceMembership.objects.filter(
        workspace=OuterRef('pk')
    ).values('workspace').annotate(
        count=Count('id')
    ).values('count')
    user_workspaces = Workspace.objects.filter(
        memberships__user=request.user
    ).annotate(
        member_count=Subquery(membership_counts)
    ).distinct()

    return {
        'active_workspace': active_workspace,
        'active_membership': active_membership,
        'user_workspaces': user_workspaces,
        'workspace_permissions': workspace_permissions,
    }
