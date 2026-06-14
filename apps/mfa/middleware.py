from django.shortcuts import redirect
from django.urls import reverse
from django_otp import user_has_device
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.workspaces.models import Workspace, WorkspaceMembership


class MfaEnforcementMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            workspace_id = request.session.get('active_workspace_id')
            if workspace_id:
                try:
                    workspace = Workspace.objects.get(id=workspace_id)
                    membership = WorkspaceMembership.objects.filter(
                        workspace=workspace, user=request.user,
                    ).first()
                    if membership and membership.role in ('owner', 'admin'):
                        if workspace.plan == 'enterprise':
                            has_totp = TOTPDevice.objects.filter(
                                user=request.user, confirmed=True,
                            ).exists()
                            if not has_totp:
                                path = request.path_info
                                mfa_path = reverse('mfa:settings')
                                if path != mfa_path and not path.startswith(reverse('mfa:enable')):
                                    if not path.startswith('/accounts/') and not path.startswith('/admin/'):
                                        return redirect('mfa:required')
                except Workspace.DoesNotExist:
                    pass

        return self.get_response(request)
