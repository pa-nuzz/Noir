from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect

from .models import WorkspaceMembership, WorkspacePermission


def _get_ws_and_membership(workspace_id, user):
    from django.shortcuts import get_object_or_404
    from .models import Workspace
    workspace = get_object_or_404(Workspace, id=workspace_id)
    membership = WorkspaceMembership.objects.filter(workspace=workspace, user=user).first()
    return workspace, membership


def workspace_role_required(*roles):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, workspace_id, *args, **kwargs):
            workspace, membership = _get_ws_and_membership(workspace_id, request.user)
            if not membership:
                messages.error(request, 'You do not have access to this workspace.')
                return redirect('workspaces:list')
            if membership.role not in roles:
                messages.error(request, 'You do not have permission for this action.')
                return redirect('workspaces:detail', workspace_id=workspace.id)
            return view_func(request, workspace, membership, *args, **kwargs)
        return _wrapped
    return decorator


def require_workspace_permission(module, action):
    """Decorator: require a specific module+action permission in the active workspace.

    Usage:
        @require_workspace_permission('campaigns', 'create')
        def campaign_create(request):
            ...

    The check is performed against the active workspace in the session.
    Falls back to allowing all if no active workspace (personal mode).
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            ws_id = request.session.get('active_workspace_id')
            if not ws_id:
                return view_func(request, *args, **kwargs)
            membership = WorkspaceMembership.objects.filter(
                workspace_id=ws_id, user=request.user
            ).first()
            if not membership:
                messages.error(request, 'You do not have access to this workspace.')
                return redirect('workspaces:list')
            # Owner bypass
            if membership.role == 'owner':
                return view_func(request, *args, **kwargs)
            perm = WorkspacePermission.objects.filter(
                workspace_id=ws_id,
                role=membership.role,
                module=module,
            ).first()
            action_map = {
                'read': getattr(perm, 'can_read', False) if perm else False,
                'create': getattr(perm, 'can_create', False) if perm else False,
                'edit': getattr(perm, 'can_edit', False) if perm else False,
                'delete': getattr(perm, 'can_delete', False) if perm else False,
            }
            if not action_map.get(action, False):
                messages.error(
                    request,
                    f'You do not have "{action}" permission for {module} in this workspace.'
                )
                return redirect('workspaces:overview', workspace_id=ws_id)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator
