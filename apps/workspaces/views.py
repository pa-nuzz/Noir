import logging

from django.conf import settings
import importlib
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.core.mail import send_mail
from django.db.models import Count, OuterRef, Q, Subquery, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from .models import AuditLog, TeamInvitation, Workspace, WorkspaceMembership, WorkspacePermission, WorkspaceSocialAccount, WorkspaceStorageConfig, seed_default_permissions
from .onboarding import get_or_create_onboarding
from apps.dashboard.models import Notification

logger = logging.getLogger(__name__)


def _get_workspace_and_check_access(workspace_id, user):
    workspace = get_object_or_404(Workspace, id=workspace_id)
    membership = WorkspaceMembership.objects.filter(workspace=workspace, user=user).first()
    return workspace, membership


def _log_action(workspace, user, action, details=None, ip_address=None):
    AuditLog.objects.create(
        workspace=workspace,
        user=user,
        action=action,
        details=details or {},
        ip_address=ip_address,
    )


@login_required
def workspace_list(request):
    membership_counts = WorkspaceMembership.objects.filter(
        workspace=OuterRef('pk')
    ).values('workspace').annotate(
        count=Count('id')
    ).values('count')
    owned = Workspace.objects.filter(created_by=request.user).annotate(
        member_count=Subquery(membership_counts)
    )
    member_of = Workspace.objects.filter(
        memberships__user=request.user
    ).exclude(created_by=request.user).annotate(
        member_count=Subquery(membership_counts)
    )
    pending_invites = TeamInvitation.objects.filter(
        email=request.user.email, status='pending'
    ).select_related('workspace', 'invited_by')
    active_workspace_id = request.session.get('active_workspace_id')
    return render(request, 'workspaces/workspace_list.html', {
        'owned': owned,
        'member_of': member_of,
        'pending_invites': pending_invites,
        'active_workspace_id': active_workspace_id,
    })


@login_required
def workspace_create(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        if not name:
            messages.error(request, 'Workspace name is required.')
            return render(request, 'workspaces/workspace_form.html')
        workspace = Workspace.objects.create(
            name=name,
            description=description,
            created_by=request.user,
        )
        WorkspaceMembership.objects.create(
            workspace=workspace,
            user=request.user,
            role='owner',
        )
        seed_default_permissions(workspace)
        _log_action(workspace, request.user, 'Workspace created',
                    ip_address=request.META.get('REMOTE_ADDR'))
        request.session['active_workspace_id'] = workspace.id
        request.session.modified = True
        messages.success(request, f'Workspace "{name}" created.')
        return redirect('workspaces:onboarding', workspace_id=workspace.id)
    return render(request, 'workspaces/workspace_form.html')


@login_required
def workspace_detail(request, workspace_id):
    workspace, membership = _get_workspace_and_check_access(workspace_id, request.user)
    if not membership:
        messages.error(request, 'You do not have access to this workspace.')
        return redirect('workspaces:list')
    members = WorkspaceMembership.objects.filter(workspace=workspace).select_related('user')
    recent_audit = AuditLog.objects.filter(workspace=workspace)[:10]
    return render(request, 'workspaces/workspace_detail.html', {
        'workspace': workspace,
        'membership': membership,
        'members': members,
        'recent_audit': recent_audit,
    })


@login_required
def workspace_edit(request, workspace_id):
    workspace, membership = _get_workspace_and_check_access(workspace_id, request.user)
    if not membership or membership.role not in ('owner', 'admin'):
        messages.error(request, 'Only workspace owners and admins can edit settings.')
        return redirect('workspaces:detail', workspace_id=workspace.id)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        if not name:
            messages.error(request, 'Workspace name is required.')
            return render(request, 'workspaces/workspace_form.html', {'workspace': workspace, 'editing': True})
        workspace.name = name
        workspace.description = description
        workspace.save(update_fields=['name', 'description'])
        _log_action(workspace, request.user, 'Workspace settings updated',
                    ip_address=request.META.get('REMOTE_ADDR'))
        messages.success(request, 'Workspace updated.')
        return redirect('workspaces:detail', workspace_id=workspace.id)
    return render(request, 'workspaces/workspace_form.html', {
        'workspace': workspace,
        'editing': True,
    })


@login_required
@require_POST
def workspace_delete(request, workspace_id):
    workspace = get_object_or_404(Workspace, id=workspace_id, created_by=request.user)
    name = workspace.name
    for app_label, model_name in [
            ('social_accounts', 'SocialPost'),
            ('content_studio', 'ContentItem'),
            ('webhooks', 'WebhookEndpoint'),
            ('senders', 'Sender'),
            ('media_assets', 'MediaAsset'),
            ('media_assets', 'MediaFolder'),
            ('inbox', 'EmailInbox'),
            ('contacts', 'ContactSegment'),
            ('contacts', 'ContactCustomField'),
            ('contacts', 'ContactTag'),
            ('contacts', 'ContactList'),
            ('campaigns', 'EmailTemplate'),
            ('campaigns', 'Campaign'),
            ('automations', 'Workflow'),
            ('api_keys', 'WorkspaceAPIKey'),
        ]:
            try:
                mod = importlib.import_module(f'apps.{app_label}.models')
                cls = getattr(mod, model_name)
                cls.objects.filter(workspace=workspace).delete()
            except (ImportError, AttributeError):
                pass
    workspace.delete()
    messages.success(request, f'Workspace "{name}" and all associated data deleted.')
    return redirect('workspaces:list')


@login_required
def member_list(request, workspace_id):
    workspace, membership = _get_workspace_and_check_access(workspace_id, request.user)
    if not membership:
        messages.error(request, 'You do not have access to this workspace.')
        return redirect('workspaces:list')
    members = WorkspaceMembership.objects.filter(workspace=workspace).select_related('user')
    pending_invites = TeamInvitation.objects.filter(workspace=workspace, status='pending')
    invite_sent_email = request.session.pop('invite_sent_email', None)
    return render(request, 'workspaces/members.html', {
        'workspace': workspace,
        'membership': membership,
        'members': members,
        'pending_invites': pending_invites,
        'invite_sent_email': invite_sent_email,
        'role_labels': dict(WorkspaceMembership.ROLE_CHOICES),
    })


@login_required
@require_POST
def remove_member(request, workspace_id, membership_id):
    workspace, membership = _get_workspace_and_check_access(workspace_id, request.user)
    if not membership or membership.role not in ('owner', 'admin'):
        messages.error(request, 'Only workspace owners and admins can remove members.')
        return redirect('workspaces:member_list', workspace_id=workspace.id)
    target = get_object_or_404(WorkspaceMembership, id=membership_id, workspace=workspace)
    if target.role == 'owner':
        messages.error(request, 'Cannot remove the workspace owner.')
        return redirect('workspaces:member_list', workspace_id=workspace.id)
    user_email = target.user.email
    removed_user = target.user
    target.delete()
    _log_action(workspace, request.user, f'Removed member {user_email}',
                ip_address=request.META.get('REMOTE_ADDR'))
    Notification.objects.create(
        user=removed_user,
        title='Removed from Workspace',
        message=f'You have been removed from "{workspace.name}" by {request.user.get_full_name() or request.user.email}.',
        tone='warning',
        url=reverse('workspaces:list'),
    )
    messages.success(request, f'{user_email} removed from workspace.')
    return redirect('workspaces:member_list', workspace_id=workspace.id)


@login_required
@require_POST
def leave_workspace(request, workspace_id):
    workspace, membership = _get_workspace_and_check_access(workspace_id, request.user)
    if not membership:
        messages.error(request, 'You are not a member of this workspace.')
        return redirect('workspaces:list')
    if membership.role == 'owner':
        messages.error(request, 'Workspace owners cannot leave. Transfer ownership or delete the workspace first.')
        return redirect('workspaces:detail', workspace_id=workspace.id)
    membership.delete()
    _log_action(workspace, request.user, 'Member left workspace',
                ip_address=request.META.get('REMOTE_ADDR'))
    messages.success(request, f'You have left "{workspace.name}".')
    return redirect('workspaces:list')


@login_required
def invite_member(request, workspace_id):
    workspace, membership = _get_workspace_and_check_access(workspace_id, request.user)
    if not membership or membership.role not in ('owner', 'admin'):
        messages.error(request, 'Only owners and admins can invite members.')
        return redirect('workspaces:detail', workspace_id=workspace.id)
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        role = request.POST.get('role', 'member')
        message = request.POST.get('message', '').strip()
        if not email:
            messages.error(request, 'Email address is required.')
            return redirect('workspaces:member_list', workspace_id=workspace.id)
        if TeamInvitation.objects.filter(workspace=workspace, email=email, status='pending').exists():
            messages.warning(request, f'An invitation has already been sent to {email}.')
            return redirect('workspaces:member_list', workspace_id=workspace.id)
        if WorkspaceMembership.objects.filter(workspace=workspace, user__email=email).exists():
            messages.warning(request, f'{email} is already a member of this workspace.')
            return redirect('workspaces:member_list', workspace_id=workspace.id)
        invitation = TeamInvitation.objects.create(
            workspace=workspace,
            email=email,
            invited_by=request.user,
            role=role,
            message=message,
        )
        _log_action(workspace, request.user, f'Invited {email} as {role}',
                    ip_address=request.META.get('REMOTE_ADDR'))

        accept_url = request.build_absolute_uri(
            reverse('workspaces:accept_invitation', args=[invitation.id])
        )
        decline_url = request.build_absolute_uri(
            reverse('workspaces:decline_invitation', args=[invitation.id])
        )
        try:
            send_mail(
                subject=f"You've been invited to '{workspace.name}'",
                message=(
                    f"Hi,\n\n"
                    f"{request.user.get_full_name() or request.user.email} has invited you to join "
                    f"the workspace '{workspace.name}' as a {invitation.get_role_display()}.\n\n"
                    f"{'Personal message: ' + message + '\n\n' if message else ''}"
                    f"Accept the invitation:\n{accept_url}\n\n"
                    f"Decline the invitation:\n{decline_url}\n\n"
                    f"This invitation expires in 7 days.\n\n"
                    f"— Intelligent Digital Automation (IDA)"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
        except Exception:
            logger.warning(f'Failed to send invitation email to {email}')

        invited_user = User.objects.filter(email__iexact=email).first()
        if invited_user:
            Notification.objects.create(
                user=invited_user,
                title='Workspace Invitation',
                message=f'{request.user.get_full_name() or request.user.email} invited you to join "{workspace.name}" as {invitation.get_role_display()}.',
                tone='info',
                url=reverse('workspaces:my_invitations'),
            )

        request.session['invite_sent_email'] = email
        return redirect('workspaces:member_list', workspace_id=workspace.id)
    return redirect('workspaces:member_list', workspace_id=workspace.id)


@login_required
def update_member_role(request, workspace_id, membership_id):
    """AJAX endpoint: change a member's role."""
    if request.method != 'POST' or not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'error': 'Invalid request'}, status=400)
    workspace, membership = _get_workspace_and_check_access(workspace_id, request.user)
    if not membership or membership.role not in ('owner', 'admin'):
        return JsonResponse({'error': 'Not authorized'}, status=403)
    target = get_object_or_404(WorkspaceMembership, id=membership_id, workspace=workspace)
    if target.role == 'owner':
        return JsonResponse({'error': 'Cannot change owner role'}, status=400)
    new_role = request.POST.get('role', '').strip()
    valid_roles = [r[0] for r in WorkspaceMembership.ROLE_CHOICES if r[0] != 'owner']
    if new_role not in valid_roles:
        return JsonResponse({'error': 'Invalid role'}, status=400)
    old_role = target.role
    target.role = new_role
    target.save(update_fields=['role'])
    _log_action(workspace, request.user, f'Changed {target.user.email} role from {old_role} to {new_role}',
                ip_address=request.META.get('REMOTE_ADDR'))
    return JsonResponse({'status': 'ok', 'role': new_role, 'label': target.get_role_display()})


@login_required
def my_invitations(request):
    return redirect(reverse('workspaces:list') + '?tab=invitations')


@login_required
def accept_invitation(request, invitation_id):
    try:
        invitation = TeamInvitation.objects.get(id=invitation_id)
    except TeamInvitation.DoesNotExist:
        return render(request, 'workspaces/invitation_response.html', {
            'title': 'Invitation Not Found',
            'message': 'This invitation does not exist. It may have been cancelled.',
            'icon': 'error',
        })

    if invitation.email.lower() != request.user.email.lower():
        return render(request, 'workspaces/invitation_response.html', {
            'title': 'Wrong Account',
            'message': f'This invitation was sent to <strong>{invitation.email}</strong>. '
                       f'You are logged in as <strong>{request.user.email}</strong>. '
                       f'Please log out and use the correct account, or ask the inviter to send a new invitation to your current email.',
            'icon': 'warning',
        })

    if invitation.status != 'pending':
        return render(request, 'workspaces/invitation_response.html', {
            'title': 'Invitation Already Used',
            'message': f'This invitation has already been <strong>{invitation.status}</strong>.',
            'icon': 'info',
        })

    if invitation.is_expired():
        invitation.status = 'expired'
        invitation.save(update_fields=['status'])
        return render(request, 'workspaces/invitation_response.html', {
            'title': 'Invitation Expired',
            'message': 'This invitation has expired. Ask the workspace owner to send a new one.',
            'icon': 'error',
        })

    if WorkspaceMembership.objects.filter(workspace=invitation.workspace, user=request.user).exists():
        invitation.status = 'accepted'
        invitation.save(update_fields=['status'])
        return render(request, 'workspaces/invitation_response.html', {
            'title': 'Already a Member',
            'message': f'You are already a member of <strong>"{invitation.workspace.name}"</strong>.',
            'icon': 'info',
            'workspace_id': invitation.workspace.id,
        })

    WorkspaceMembership.objects.create(
        workspace=invitation.workspace,
        user=request.user,
        role=invitation.role,
    )
    seed_default_permissions(invitation.workspace)
    invitation.status = 'accepted'
    invitation.save(update_fields=['status'])
    request.session['active_workspace_id'] = invitation.workspace.id
    request.session.modified = True
    _log_action(invitation.workspace, request.user, f'Accepted invitation (joined as {invitation.role})',
                ip_address=request.META.get('REMOTE_ADDR'))
    try:
        send_mail(
            subject=f"{request.user.get_full_name() or request.user.email} accepted your invitation",
            message=(
                f"{request.user.get_full_name() or request.user.email} has accepted your invitation "
                f"to join '{invitation.workspace.name}' as a {invitation.get_role_display()}.\n\n"
                f"— Intelligent Digital Automation (IDA)"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invitation.invited_by.email],
            fail_silently=False,
        )
    except Exception:
        logger.warning(f'Failed to send acceptance notification to {invitation.invited_by.email}')
    Notification.objects.create(
        user=invitation.invited_by,
        title='Invitation Accepted',
        message=f'{request.user.get_full_name() or request.user.email} accepted their invitation to "{invitation.workspace.name}" as {invitation.get_role_display()}.',
        tone='success',
        url=reverse('workspaces:detail', args=[invitation.workspace.id]),
    )
    return render(request, 'workspaces/invitation_response.html', {
        'title': 'Invitation Accepted!',
        'message': f'You have joined <strong>"{invitation.workspace.name}"</strong> as a <strong>{invitation.get_role_display()}</strong>.',
        'icon': 'success',
        'workspace_id': invitation.workspace.id,
    })


@login_required
def decline_invitation(request, invitation_id):
    try:
        invitation = TeamInvitation.objects.get(id=invitation_id)
    except TeamInvitation.DoesNotExist:
        return render(request, 'workspaces/invitation_response.html', {
            'title': 'Invitation Not Found',
            'message': 'This invitation does not exist. It may have been cancelled.',
            'icon': 'error',
        })

    if invitation.email.lower() != request.user.email.lower():
        return render(request, 'workspaces/invitation_response.html', {
            'title': 'Wrong Account',
            'message': f'This invitation was sent to <strong>{invitation.email}</strong>.',
            'icon': 'warning',
        })

    if invitation.status != 'pending':
        return render(request, 'workspaces/invitation_response.html', {
            'title': 'Already Responded',
            'message': f'This invitation has already been <strong>{invitation.status}</strong>.',
            'icon': 'info',
        })

    invitation.status = 'declined'
    invitation.save(update_fields=['status'])
    _log_action(invitation.workspace, request.user, f'Declined invitation to join as {invitation.role}',
                ip_address=request.META.get('REMOTE_ADDR'))
    try:
        send_mail(
            subject=f"{request.user.get_full_name() or request.user.email} declined your invitation",
            message=(
                f"{request.user.get_full_name() or request.user.email} has declined your invitation "
                f"to join '{invitation.workspace.name}' as a {invitation.get_role_display()}.\n\n"
                f"— Intelligent Digital Automation (IDA)"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invitation.invited_by.email],
            fail_silently=False,
        )
    except Exception:
        logger.warning(f'Failed to send decline notification to {invitation.invited_by.email}')
    Notification.objects.create(
        user=invitation.invited_by,
        title='Invitation Declined',
        message=f'{request.user.get_full_name() or request.user.email} declined the invitation to "{invitation.workspace.name}".',
        tone='info',
        url=reverse('workspaces:detail', args=[invitation.workspace.id]),
    )
    return render(request, 'workspaces/invitation_response.html', {
        'title': 'Invitation Declined',
        'message': f'You have declined the invitation to <strong>"{invitation.workspace.name}"</strong>.',
        'icon': 'info',
    })


@login_required
@require_POST
def cancel_invitation(request, invitation_id):
    invitation = get_object_or_404(TeamInvitation, id=invitation_id)
    workspace = invitation.workspace
    membership = WorkspaceMembership.objects.filter(workspace=workspace, user=request.user).first()
    if not membership or membership.role not in ('owner', 'admin'):
        messages.error(request, 'Only workspace owners and admins can cancel invitations.')
        return redirect('workspaces:member_list', workspace_id=workspace.id)
    invitation.status = 'expired'
    invitation.save(update_fields=['status'])
    _log_action(workspace, request.user, f'Cancelled invitation for {invitation.email}',
                ip_address=request.META.get('REMOTE_ADDR'))
    messages.success(request, f'Invitation to {invitation.email} cancelled.')
    return redirect('workspaces:member_list', workspace_id=workspace.id)


@login_required
def audit_log_view(request, workspace_id):
    workspace, membership = _get_workspace_and_check_access(workspace_id, request.user)
    if not membership or membership.role not in ('owner', 'admin'):
        messages.error(request, 'Only owners and admins can view the audit log.')
        return redirect('workspaces:detail', workspace_id=workspace.id)

    # Permissions matrix
    perm_rows = WorkspacePermission.objects.filter(workspace=workspace).order_by('role', 'module')
    roles_matrix = {}
    for perm in perm_rows:
        roles_matrix.setdefault(perm.module, {})[perm.role] = {
            'read': perm.can_read,
            'create': perm.can_create,
            'edit': perm.can_edit,
            'delete': perm.can_delete,
        }
    module_groups = {
        'pencil-alt': ('Content & Creation', ['campaigns', 'contacts', 'social', 'media', 'workflows', 'content_studio']),
        'mail': ('Communication & Automation', ['inbox']),
        'cog': ('Workspace Management', ['workspace', 'billing', 'members', 'storage', 'export']),
        'clipboard-list': ('System & Compliance', ['audit_log']),
    }

    # Audit log
    log_qs = AuditLog.objects.filter(workspace=workspace).select_related('user')
    keep_ids = list(log_qs.order_by('-created_at').values_list('id', flat=True)[:50])
    AuditLog.objects.filter(workspace=workspace).exclude(id__in=keep_ids).delete()
    log_qs = AuditLog.objects.filter(workspace=workspace).select_related('user').order_by('-created_at')
    total_count = log_qs.count()
    paginator = Paginator(log_qs, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    return render(request, 'workspaces/audit_log.html', {
        'workspace': workspace,
        'membership': membership,
        'page_obj': page_obj,
        'total_count': total_count,
        'roles': ['owner', 'admin', 'member'],
        'roles_matrix': roles_matrix,
        'module_labels': dict(WorkspacePermission.MODULE_CHOICES),
        'role_labels': dict(WorkspaceMembership.ROLE_CHOICES),
        'module_groups': module_groups,
    })


@login_required
def deactivate_workspace(request):
    """Switch back to personal mode — clear active workspace from session."""
    if 'active_workspace_id' in request.session:
        del request.session['active_workspace_id']
        request.session.modified = True
        messages.success(request, 'Switched to Personal Mode.')
    return redirect('dashboard:dashboard')


@login_required
def set_active_workspace(request, workspace_id):
    workspace = get_object_or_404(Workspace, id=workspace_id)
    membership = WorkspaceMembership.objects.filter(workspace=workspace, user=request.user).first()
    if not membership:
        messages.error(request, 'You do not have access to this workspace.')
        return redirect('workspaces:list')
    request.session['active_workspace_id'] = workspace.id
    request.session.modified = True
    messages.success(request, f'Switched to "{workspace.name}".')
    return redirect('workspaces:overview', workspace_id=workspace.id)


@login_required
def workspace_overview(request, workspace_id):
    workspace, membership = _get_workspace_and_check_access(workspace_id, request.user)
    if not membership:
        messages.error(request, 'You do not have access to this workspace.')
        return redirect('workspaces:list')

    members = WorkspaceMembership.objects.filter(workspace=workspace).select_related('user')
    shared_accounts = WorkspaceSocialAccount.objects.filter(workspace=workspace).select_related('account', 'added_by')
    member_count = members.count()
    pending_invites = TeamInvitation.objects.filter(workspace=workspace, status='pending').count()

    SocialPost = Campaign = ContactList = MediaAsset = EmailInbox = Workflow = ContentItem = None
    try:
        from apps.social_accounts.models import SocialPost as SP
        SocialPost = SP
    except ImportError:
        pass
    try:
        from apps.campaigns.models import Campaign as C
        Campaign = C
    except ImportError:
        pass
    try:
        from apps.contacts.models import ContactList as CL
        ContactList = CL
    except ImportError:
        pass
    try:
        from apps.media_assets.models import MediaAsset as MA
        MediaAsset = MA
    except ImportError:
        pass
    try:
        from apps.inbox.models import EmailInbox as EI
        EmailInbox = EI
    except ImportError:
        pass
    try:
        from apps.automations.models import Workflow as W
        Workflow = W
    except ImportError:
        pass
    try:
        from apps.content_studio.models import ContentItem as CI
        ContentItem = CI
    except ImportError:
        pass

    post_count = SocialPost.objects.filter(workspace=workspace).count() if SocialPost else 0
    campaign_count = Campaign.objects.count() if Campaign else 0
    contact_list_count = ContactList.objects.filter(workspace=workspace).count() if ContactList else 0
    media_count = MediaAsset.objects.filter(workspace=workspace).count() if MediaAsset else 0
    inbox_count = EmailInbox.objects.filter(workspace=workspace).count() if EmailInbox else 0
    workflow_count = Workflow.objects.filter(workspace=workspace).count() if Workflow else 0
    content_count = ContentItem.objects.filter(workspace=workspace).count() if ContentItem else 0

    storage_config = WorkspaceStorageConfig.objects.filter(workspace=workspace).first()
    storage_used_mb = storage_config.storage_used_mb if storage_config else 0
    storage_backend = storage_config.get_backend_display() if storage_config and storage_config.backend else 'Local'

    recent_posts = []
    if SocialPost:
        recent_posts = list(SocialPost.objects.filter(workspace=workspace).order_by('-created_at')[:10])

    recent_audit = AuditLog.objects.filter(workspace=workspace)[:10]

    return render(request, 'workspaces/workspace_overview.html', {
        'workspace': workspace,
        'membership': membership,
        'members': members,
        'shared_accounts': shared_accounts,
        'recent_posts': recent_posts,
        'recent_audit': recent_audit,
        'member_count': member_count,
        'pending_invites': pending_invites,
        'post_count': post_count,
        'campaign_count': campaign_count,
        'contact_list_count': contact_list_count,
        'media_count': media_count,
        'inbox_count': inbox_count,
        'workflow_count': workflow_count,
        'content_count': content_count,
        'storage_used_mb': storage_used_mb,
        'storage_backend': storage_backend,
    })


@login_required
def workspace_social_hub(request, workspace_id):
    workspace, membership = _get_workspace_and_check_access(workspace_id, request.user)
    if not membership:
        messages.error(request, 'You do not have access to this workspace.')
        return redirect('workspaces:list')

    shared_accounts = WorkspaceSocialAccount.objects.filter(workspace=workspace).select_related('account', 'added_by')

    SocialPost = None
    try:
        from apps.social_accounts.models import SocialPost as SP
        SocialPost = SP
    except ImportError:
        pass

    posts = []
    if SocialPost:
        posts = list(SocialPost.objects.filter(workspace=workspace).order_by('-created_at')[:50])

    return render(request, 'workspaces/workspace_social_hub.html', {
        'workspace': workspace,
        'membership': membership,
        'shared_accounts': shared_accounts,
        'posts': posts,
    })


@login_required
def workspace_permissions(request, workspace_id):
    """View and edit granular role-based permissions for a workspace."""
    workspace, membership = _get_workspace_and_check_access(workspace_id, request.user)
    if not membership:
        messages.error(request, 'You do not have access to this workspace.')
        return redirect('workspaces:list')
    if membership.role not in ('owner', 'admin'):
        messages.error(request, 'Only workspace owners and admins can manage permissions.')
        return redirect('workspaces:detail', workspace_id=workspace.id)

    # Ensure permission rows exist
    seed_default_permissions(workspace)

    roles = ['owner', 'admin', 'member',]

    if request.method == 'POST':
        role = request.POST.get('role')
        module = request.POST.get('module')
        field = request.POST.get('field')  # can_read, can_create, can_edit, can_delete
        value = request.POST.get('value') == '1'

        if role and module and field:
            perm, _ = WorkspacePermission.objects.get_or_create(
                workspace=workspace,
                role=role,
                module=module,
            )
            setattr(perm, field, value)
            perm.save(update_fields=[field])
            _log_action(workspace, request.user,
                        f'Updated permission: {role} → {module} → {field}={value}',
                        ip_address=request.META.get('REMOTE_ADDR'))
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'ok'})
        messages.success(request, 'Permissions updated.')
        return redirect('workspaces:permissions', workspace_id=workspace.id)

    # Load all permissions grouped by role and module
    perm_rows = WorkspacePermission.objects.filter(workspace=workspace).order_by('role', 'module')

    # Build a matrix: {module: {role: {read, create, edit, delete}}}
    roles_matrix = {}
    for perm in perm_rows:
        roles_matrix.setdefault(perm.module, {})[perm.role] = {
            'read': perm.can_read,
            'create': perm.can_create,
            'edit': perm.can_edit,
            'delete': perm.can_delete,
        }

    modules = [m[0] for m in WorkspacePermission.MODULE_CHOICES]

    module_groups = {
        'pencil-alt': ('Content & Creation', ['campaigns', 'contacts', 'social', 'media', 'workflows', 'content_studio']),
        'mail': ('Communication & Automation', ['inbox']),
        'cog': ('Workspace Management', ['workspace', 'billing', 'members', 'storage', 'export']),
        'clipboard-list': ('System & Compliance', ['audit_log']),
    }

    members = WorkspaceMembership.objects.filter(
        workspace=workspace
    ).select_related('user').order_by('role', 'user__email')

    return render(request, 'workspaces/workspace_permissions.html', {
        'workspace': workspace,
        'membership': membership,
        'roles': roles,
        'modules': modules,
        'roles_matrix': roles_matrix,
        'module_labels': dict(WorkspacePermission.MODULE_CHOICES),
        'role_labels': dict(WorkspaceMembership.ROLE_CHOICES),
        'module_groups': module_groups,
        'members': members,
        'member_count': members.count(),
    })


@login_required
def workspace_onboarding(request, workspace_id):
    """Post-create setup wizard: connect accounts, invite members, configure."""
    workspace, membership = _get_workspace_and_check_access(workspace_id, request.user)
    if not membership or membership.role != 'owner':
        messages.error(request, 'Only the workspace owner can access setup.')
        return redirect('workspaces:detail', workspace_id=workspace.id)

    shared_accounts = WorkspaceSocialAccount.objects.filter(workspace=workspace).select_related('account', 'added_by')
    member_count = WorkspaceMembership.objects.filter(workspace=workspace).count()
    pending_invites = TeamInvitation.objects.filter(workspace=workspace, status='pending').count()
    storage_config = WorkspaceStorageConfig.objects.filter(workspace=workspace).first()

    return render(request, 'workspaces/workspace_onboarding.html', {
        'workspace': workspace,
        'membership': membership,
        'shared_accounts': shared_accounts,
        'member_count': member_count,
        'pending_invites': pending_invites,
        'storage_config': storage_config,
    })


@login_required
@require_POST
def onboarding_dismiss(request, workspace_id):
    workspace, membership = _get_workspace_and_check_access(workspace_id, request.user)
    if not membership:
        return JsonResponse({'error': 'No access'}, status=403)
    onboarding = get_or_create_onboarding(workspace)
    onboarding.dismissed = True
    onboarding.save(update_fields=['dismissed'])
    return JsonResponse({'ok': True})
