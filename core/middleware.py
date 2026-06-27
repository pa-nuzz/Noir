import os
import sys

from django.contrib import messages
from django.shortcuts import redirect

from .tenant import set_current_tenant, clear_current_tenant


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            ws_id = request.session.get('active_workspace_id')
            if ws_id:
                from apps.workspaces.models import Workspace, WorkspaceMembership
                membership = WorkspaceMembership.objects.filter(
                    workspace_id=ws_id, user=request.user
                ).select_related('workspace').first()
                if membership:
                    request.tenant = membership.workspace
                    set_current_tenant(membership.workspace)
                else:
                    request.tenant = None
                    del request.session['active_workspace_id']
            else:
                request.tenant = None
                set_current_tenant(None)
        else:
            request.tenant = None
            set_current_tenant(None)

        response = self.get_response(request)
        clear_current_tenant()
        return response


class DevHTTPMiddleware:
    """
    Middleware to disable HTTPS/HSTS in development to prevent browser caching issues.
    Removes HSTS headers to prevent SSL redirect on localhost/127.0.0.1.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.debug = os.getenv('DEBUG', 'False') == 'True'

    def __call__(self, request):
        response = self.get_response(request)
        
        if self.debug or 'runserver' in sys.argv:
            # Remove HSTS headers to prevent browser from caching HTTPS-only policy
            # Do NOT clear cookies - that breaks CSRF protection
            if 'Strict-Transport-Security' in response:
                del response['Strict-Transport-Security']
        
        return response


class CSPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.tailwindcss.com https://fonts.googleapis.com https://cdnjs.cloudflare.com https://unpkg.com https://cdn.jsdelivr.net 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com https://cdn.jsdelivr.net 'unsafe-inline'; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: blob: https:; "
            "connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:* https://unpkg.com https://cdn.jsdelivr.net https://api.openai.com https://cdnjs.cloudflare.com; "
            "frame-src 'self' https://www.youtube.com https://youtube.com; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )
        return response