from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
import smtplib, ssl, json
import logging

from apps.workspaces.decorators import require_workspace_permission

logger = logging.getLogger(__name__)


@login_required
@require_POST
@require_workspace_permission('workspace', 'edit')
def verify_sender(request):
    try:
        data = json.loads(request.body)
        host = str(data.get('host', '')).strip()
        port = int(data.get('port', 0))
        username = str(data.get('username', '')).strip()
        from_email = str(data.get('from_email', '')).strip()
        password = str(data.get('password', '')).strip()
        use_tls = bool(data.get('use_tls', True))
        sender_id = data.get('sender_id')

        if not host or not password or not port:
            return JsonResponse({'success': False, 'error': 'Missing host, port, username, or password.'})

        # Try multiple auth identities because many providers (especially Gmail)
        # require the account that generated the app password, which may be from_email.
        auth_candidates = []
        if username:
            auth_candidates.append(username)
        if from_email and from_email not in auth_candidates:
            auth_candidates.append(from_email)

        if not auth_candidates:
            return JsonResponse({'success': False, 'error': 'Missing SMTP username/email for authentication.'})

        context = ssl.create_default_context()
        auth_error = None

        def try_login(server):
            # Attempt each candidate in order and keep the last auth error for user feedback.
            nonlocal auth_error
            for candidate in auth_candidates:
                try:
                    server.login(candidate, password)
                    return candidate
                except smtplib.SMTPAuthenticationError as exc:
                    auth_error = exc
                    continue
            raise auth_error or smtplib.SMTPAuthenticationError(535, b'Authentication failed')

        # Port 465 is implicit SSL; non-465 routes can optionally use STARTTLS.
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15, context=context) as server:
                server.ehlo()
                authenticated_as = try_login(server)
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.ehlo()
                if use_tls:
                    server.starttls(context=context)
                    server.ehlo()
                authenticated_as = try_login(server)

        from django.utils import timezone
        if sender_id:
            from apps.senders.models import Sender
            try:
                sender = Sender.objects.get(id=sender_id, user=request.user)
                sender.is_active = True
                sender.is_verified = True
                sender.last_verified_at = timezone.now()
                sender.save(update_fields=['is_active', 'is_verified', 'last_verified_at'])
            except Sender.DoesNotExist:
                pass

        return JsonResponse({'success': True, 'message': f'Connection verified as {authenticated_as}!'})
    except smtplib.SMTPAuthenticationError:
        if 'gmail' in host.lower():
            return JsonResponse({'success': False, 'error': 'Gmail auth failed. Use app password from the same Gmail as SMTP Username (or sender email).'})
        return JsonResponse({'success': False, 'error': 'Authentication failed. Check SMTP username/email and app password.'})
    except smtplib.SMTPConnectError:
        return JsonResponse({'success': False, 'error': 'Unable to connect to SMTP host/port.'})
    except (TimeoutError, smtplib.SMTPServerDisconnected):
        return JsonResponse({'success': False, 'error': 'SMTP connection timed out.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
@require_workspace_permission('workspace', 'edit')
def audit_sender_dns_view(request):
    """
    Run a live DNS reputation audit for a sender's domain.
    Accepts JSON with 'domain' and optional 'smtp_host'.
    Returns structured check results and an overall health score.
    """
    try:
        data = json.loads(request.body)
        domain = str(data.get('domain', '')).strip().lower()
        smtp_host = str(data.get('smtp_host', '')).strip() or None

        if not domain:
            return JsonResponse({'success': False, 'error': 'Domain is required.'}, status=400)

        # Remove protocol/path if accidentally included
        domain = domain.replace('https://', '').replace('http://', '').split('/')[0]

        from .services.dns_audit import audit_sender_dns
        result = audit_sender_dns(domain=domain, smtp_host=smtp_host)

        return JsonResponse({'success': True, **result})

    except Exception as exc:
        logger.error(f"DNS audit error: {exc}")
        return JsonResponse({'success': False, 'error': 'DNS audit failed. Please try again.'}, status=500)



