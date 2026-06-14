import logging
import re
import smtplib
import base64
import mimetypes
from email.mime.text import MIMEText
from urllib.parse import urlparse

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import F
from django.views.decorators.http import require_POST, require_GET
from django.urls import reverse
from django.utils import timezone
from django.http import HttpResponse, JsonResponse, Http404

from .forms import EmailInboxConnectForm
from .models import EmailDraft, EmailInbox, EmailMessage
from apps.intelligence.services.inbox_ai import summarize_thread, generate_draft_reply
from apps.senders.models import Sender
from apps.workspaces.decorators import require_workspace_permission
from apps.workspaces.query_helpers import filter_by_context

logger = logging.getLogger(__name__)


@login_required
@require_workspace_permission('inbox', 'read')
def inbox_dashboard(request):
    inboxes = filter_by_context(request, EmailInbox.objects.all())
    selected_id = request.GET.get('inbox_id')
    folder = request.GET.get('folder', 'inbox')
    page = request.GET.get('page', 1)

    selected_inbox = None
    if selected_id:
        selected_inbox = get_object_or_404(inboxes, id=selected_id)
    elif inboxes.exists():
        selected_inbox = inboxes.first()

    messages_list = []
    drafts_list = []
    page_obj = None

    if selected_inbox:
        if folder == 'drafts':
            drafts_qs = EmailDraft.objects.filter(
                user=request.user,
                thread__inbox=selected_inbox,
            ).select_related('thread', 'original_message').order_by('-created_at')
            paginator = Paginator(drafts_qs, 20)
            page_obj = paginator.get_page(page)
            drafts_list = page_obj.object_list
        else:
            is_incoming = (folder == 'inbox')
            messages_qs = EmailMessage.objects.filter(
                thread__inbox=selected_inbox,
                is_incoming=is_incoming,
                is_deleted=False,
            ).select_related('thread').order_by('-received_at')
            paginator = Paginator(messages_qs, 20)
            page_obj = paginator.get_page(page)
            messages_list = page_obj.object_list

    trash_count = EmailMessage.objects.filter(
        thread__inbox__in=filter_by_context(request, EmailInbox.objects.all()),
        is_deleted=True,
    ).count()

    return render(request, 'inbox/dashboard.html', {
        'inboxes': inboxes,
        'selected_inbox': selected_inbox,
        'folder': folder,
        'email_messages': messages_list,
        'drafts': drafts_list,
        'page_obj': page_obj,
        'trash_count': trash_count,
    })


@login_required
@require_workspace_permission('inbox', 'create')
def inbox_connect(request):
    reconnect_id = request.GET.get('reconnect')
    reconnect_inbox = None
    if reconnect_id:
        try:
            reconnect_inbox = get_object_or_404(filter_by_context(request, EmailInbox.objects.all()), id=reconnect_id)
        except EmailInbox.DoesNotExist:
            pass

    if request.method == 'POST':
        form = EmailInboxConnectForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email_address']
            existing = filter_by_context(request, EmailInbox.objects.filter(email_address=email))

            if reconnect_inbox and reconnect_inbox.email_address == email:
                inbox = reconnect_inbox
                inbox.provider = form.cleaned_data['provider']
            elif existing.exists():
                messages.error(request, f'Inbox "{email}" is already connected.')
                return render(request, 'inbox/connect.html', {
                    'form': form,
                    'existing_inboxes': filter_by_context(request, EmailInbox.objects.all()),
                })
            else:
                inbox = form.save(commit=False)
                inbox.user = request.user
                ws_id = request.session.get('active_workspace_id')
                if ws_id:
                    inbox.workspace_id = ws_id

            imap_password = form.cleaned_data.get('imap_password', '')
            if imap_password:
                inbox.set_token(imap_password)
            inbox.last_sync_status = 'pending'
            inbox.last_sync_error = ''
            inbox.save()

            from .tasks import sync_inbox_task
            try:
                sync_inbox_task.delay(inbox.id)
                if reconnect_inbox:
                    messages.success(request, f'{inbox.get_provider_display()} inbox reconnected. Sync started.')
                else:
                    messages.success(request, f'{inbox.get_provider_display()} inbox connected. Initial sync started.')
            except Exception:
                logger.warning("Celery unavailable, running sync synchronously")
                try:
                    count = sync_inbox_task(inbox.id)
                    messages.success(request, f'{inbox.get_provider_display()} inbox {"re" if reconnect_inbox else ""}connected. Synced {count} messages.')
                except Exception as e2:
                    logger.error(f"Sync failed: {e2}")
                    messages.warning(request, f'{inbox.get_provider_display()} inbox {"re" if reconnect_inbox else ""}connected, but sync failed. You can retry from the dashboard.')
            return redirect('inbox:dashboard')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = EmailInboxConnectForm()
        if reconnect_inbox:
            form = EmailInboxConnectForm(initial={
                'email_address': reconnect_inbox.email_address,
                'provider': reconnect_inbox.provider,
            })

    existing_inboxes = filter_by_context(request, EmailInbox.objects.all())
    return render(request, 'inbox/connect.html', {
        'form': form,
        'existing_inboxes': existing_inboxes,
        'reconnect_inbox': reconnect_inbox,
    })


@login_required
@require_workspace_permission('inbox', 'read')
def inbox_sync(request, inbox_id):
    inbox = get_object_or_404(filter_by_context(request, EmailInbox.objects.all()), id=inbox_id)
    password = inbox.get_token()

    if not password:
        inbox.last_sync_status = 'error'
        inbox.last_sync_error = 'No password stored. Please reconnect the inbox.'
        inbox.save(update_fields=['last_sync_status', 'last_sync_error'])
        messages.warning(
            request,
            f'No password stored for {inbox.email_address}. '
            f'<a href="{reverse("inbox:connect")}?reconnect={inbox.id}" class="underline font-semibold">Reconnect</a> to restore sync.',
        )
        return redirect('inbox:dashboard')

    from .tasks import sync_inbox_task
    try:
        count = sync_inbox_task(inbox.id)
        messages.success(request, f'Synced {inbox.email_address}: {count} new message(s).')
        return redirect(f'{reverse("inbox:dashboard")}?refresh={int(timezone.now().timestamp())}')
    except Exception as e2:
        logger.error(f"Sync failed for {inbox.email_address}: {e2}")
        inbox.last_sync_status = 'error'
        inbox.last_sync_error = str(e2)
        inbox.save(update_fields=['last_sync_status', 'last_sync_error'])
        messages.error(request, f'Sync failed for {inbox.email_address}. Try again.')
        return redirect('inbox:dashboard')


@login_required
@require_workspace_permission('inbox', 'delete')
def inbox_disconnect(request, inbox_id):
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('inbox:dashboard')
    inbox = get_object_or_404(filter_by_context(request, EmailInbox.objects.all()), id=inbox_id)
    inbox.delete()
    messages.success(request, 'Inbox disconnected.')
    return redirect('inbox:dashboard')



def _render_email_for_display(body_html, body_text=None, inline_cids=None, request=None):
    """
    Render email HTML for display in iframe sandbox.
    Preserves images, styles, and structure while sanitizing dangerous content.
    """
    if not body_html and not body_text:
        return _get_empty_email_html()
    
    if body_html:
        # Sanitize HTML - remove only dangerous content, preserve structure
        html = body_html
        
        # Remove dangerous elements
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<object[^>]*>.*?</object>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<embed[^>]*>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'<iframe[^>]*>.*?</iframe>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<form[^>]*>.*?</form>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<base[^>]*>', '', html, flags=re.IGNORECASE)
        
        # Remove dangerous attributes
        html = re.sub(r'\bon\w+\s*=\s*["\'][^"\']*["\']', '', html, flags=re.IGNORECASE)
        html = re.sub(r'\bon\w+\s*=\s*\S+', '', html, flags=re.IGNORECASE)
        html = re.sub(r'href\s*=\s*["\']\s*javascript\s*:', '', html, flags=re.IGNORECASE)
        html = re.sub(r'src\s*=\s*["\']\s*javascript\s*:', '', html, flags=re.IGNORECASE)
        html = re.sub(r'action\s*=\s*["\']\s*javascript\s*:', '', html, flags=re.IGNORECASE)
        
        # Handle inline CID images - replace with proxy URLs
        if inline_cids:
            for cid, uri in inline_cids.items():
                if uri.startswith('data:'):
                    # Already a data URI, keep as is
                    html = html.replace(f'cid:{cid}', uri)
                else:
                    # Proxy the image through our endpoint
                    proxy_url = f"/inbox/proxy-image/?cid={cid}"
                    html = html.replace(f'cid:{cid}', proxy_url)
        
        # Handle remaining CID references - try to proxy them
        html = re.sub(r'cid:([\w\.\-\+]+)', lambda m: f"/inbox/proxy-image/?cid={m.group(1)}", html)
        
        # Handle external images - proxy them for privacy
        def proxy_external_images(match):
            full_tag = match.group(0)
            src_match = re.search(r'src\s*=\s*["\']([^"\']+)["\']', full_tag, flags=re.IGNORECASE)
            if src_match:
                src = src_match.group(1)
                if src.startswith(('http://', 'https://')) and not src.startswith('data:'):
                    proxy_url = f"/inbox/proxy-image/?url={urlparse(src).path if urlparse(src).path else src}"
                    full_tag = full_tag.replace(src, f"/inbox/proxy-image/?url={src}")
            return full_tag
        
        html = re.sub(r'<img\s+[^>]*>', proxy_external_images, html, flags=re.IGNORECASE)
        
        # Fix image styles
        html = re.sub(
            r'<img\s(?![^>]*style=)',
            '<img style="display:block;outline:none;border:0;max-width:100%;height:auto" ',
            html,
            flags=re.IGNORECASE,
        )
        
        # Add target="_blank" to external links
        html = re.sub(
            r'<a\s+([^>]*href\s*=\s*["\'](https?://[^"\']+)["\'][^>]*)>',
            r'<a \1 target="_blank" rel="noopener noreferrer">',
            html,
            flags=re.IGNORECASE
        )
        
        # Preserve structure - keep html, head, body but sanitize
        # Extract body content if full HTML
        body_content = html
        body_match = re.search(r'<body[^>]*>(.*?)</body>', html, flags=re.DOTALL | re.IGNORECASE)
        if body_match:
            body_content = body_match.group(1)
        else:
            # If no body tag, use the whole HTML
            body_content = html
        
        # Extract styles from head if present
        styles = ''
        head_match = re.search(r'<head[^>]*>(.*?)</head>', html, flags=re.DOTALL | re.IGNORECASE)
        if head_match:
            head_content = head_match.group(1)
            # Extract only style tags
            style_matches = re.findall(r'<style[^>]*>(.*?)</style>', head_content, flags=re.DOTALL | re.IGNORECASE)
            styles = ''.join(style_matches)
        
        # Build the final email HTML for iframe
        email_html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'self' data: https:; img-src 'self' data: https: blob:; style-src 'self' 'unsafe-inline';">
    <style>
        {styles}
        * {{
            box-sizing: border-box;
        }}
        body {{
            margin: 0;
            padding: 0;
            background-color: #f4f4f5;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #1e293b;
        }}
        .email-container {{
            max-width: 600px;
            margin: 0 auto;
            background: #ffffff;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }}
        .email-body {{
            padding: 24px;
        }}
        img {{
            max-width: 100% !important;
            height: auto !important;
            display: block;
        }}
        a {{
            color: #6D28D9;
            text-decoration: underline;
        }}
        a[href^="tel"] {{
            color: inherit;
            text-decoration: none;
        }}
        table {{
            max-width: 100%;
            width: 100%;
            border-collapse: collapse;
        }}
        @media (max-width: 600px) {{
            .email-container {{
                border-radius: 0;
            }}
            .email-body {{
                padding: 16px;
            }}
        }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="email-body">
            {body_content}
        </div>
    </div>
</body>
</html>'''
        return email_html
    
    elif body_text:
        # Fallback: convert plain text to HTML with proper formatting
        escaped = body_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        paragraphs = escaped.split('\n\n')
        html_parts = []
        for p in paragraphs:
            lines = p.split('\n')
            if len(lines) > 1:
                html_parts.append('<p style="margin:0 0 1em 0;line-height:1.6">' + '<br>'.join(lines) + '</p>')
            else:
                html_parts.append('<p style="margin:0 0 1em 0;line-height:1.6">' + p + '</p>')
        body_text_html = ''.join(html_parts)
        
        return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'self' data: https:; img-src 'self' data: https: blob:; style-src 'self' 'unsafe-inline';">
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0; padding: 0; background-color: #f4f4f5;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6; color: #1e293b;
        }}
        .email-container {{
            max-width: 600px; margin: 0 auto; background: #ffffff;
            border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }}
        .email-body {{ padding: 24px; }}
        p {{ margin: 0 0 1em 0; line-height: 1.6; }}
    </style>
</head>
<body>
    <div class="email-container">
        <div class="email-body">
            {body_text_html}
        </div>
    </div>
</body>
</html>'''
    
    return _get_empty_email_html()


def _get_empty_email_html():
    return '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { margin: 0; padding: 40px 20px; background: #f4f4f5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
        .empty { max-width: 400px; margin: 0 auto; text-align: center; padding: 40px 20px; background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
        .empty svg { color: #cbd5e1; margin-bottom: 16px; }
        .empty h3 { color: #1e293b; font-size: 18px; margin-bottom: 8px; }
        .empty p { color: #64748b; font-size: 14px; }
    </style>
</head>
<body>
    <div class="empty">
        <svg width="64" height="64" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
        <h3>No content available</h3>
        <p>This message has no readable content.</p>
    </div>
</body>
</html>'''


@login_required
@require_workspace_permission('inbox', 'read')
def message_detail(request, message_id):
    msg = get_object_or_404(EmailMessage, id=message_id, thread__inbox__user=request.user)
    
    # Build inline CIDs dict from message or thread
    inline_cids = {}
    if msg.body_html and 'cid:' in msg.body_html:
        # Extract CIDs from the message
        import re
        cids = set(re.findall(r'cid:([\w\.\-\+]+)', msg.body_html))
        # In a real implementation, you'd fetch the actual image data from the message
        # For now, we'll let the proxy handle it
    
    email_html = _render_email_for_display(
        body_html=msg.body_html,
        body_text=msg.body_text,
        inline_cids={},
        request=request
    )
    
    drafts = EmailDraft.objects.filter(
        original_message=msg, 
        thread__inbox__in=filter_by_context(request, EmailInbox.objects.all())
    ).order_by('-created_at')
    
    return render(request, 'inbox/message_detail.html', {
        'msg': msg,
        'email_html': email_html,
        'drafts': drafts,
        'summarized': request.GET.get('summarized'),
    })


@login_required
@require_workspace_permission('inbox', 'read')
def message_summarize(request, message_id):
    msg = get_object_or_404(EmailMessage, id=message_id, thread__inbox__user=request.user)
    body = f"From: {msg.from_name or msg.from_email}\nSubject: {msg.subject}\n{msg.body_text}"
    try:
        summary = summarize_thread(body, msg.subject)
    except Exception as e:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            from django.http import JsonResponse
            return JsonResponse({'success': False, 'error': str(e)})
        messages.error(request, f'AI summarization failed: {e}')
        return redirect('inbox:message_detail', message_id=msg.id)
    msg.ai_summary = summary
    msg.save(update_fields=['ai_summary'])
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        from django.http import JsonResponse
        return JsonResponse({'success': True, 'summary': summary})
    
    messages.success(request, 'Message summarized.')
    return redirect(reverse('inbox:message_detail', kwargs={'message_id': msg.id}) + '?summarized=1')


@login_required
@require_workspace_permission('inbox', 'create')
def generate_draft(request, message_id):
    """Generate an AI draft reply. Supports both AJAX (JSON) and normal request."""
    msg = get_object_or_404(EmailMessage, id=message_id, thread__inbox__user=request.user)
    thread = msg.thread
    
    # Get tone preference from AJAX header or default to professional
    tone = request.META.get('HTTP_X_TONE', 'professional')
    
    try:
        draft_body = generate_draft_reply(
            msg.subject or thread.subject,
            thread.ai_summary or '',
            msg.body_text or '',
            tone=tone,
        )
    except Exception as e:
        error_msg = f'AI draft generation failed: {e}'
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            from django.http import JsonResponse
            return JsonResponse({'success': False, 'error': error_msg})
        messages.error(request, error_msg)
        return redirect('inbox:message_detail', message_id=msg.id)
    
    draft = EmailDraft.objects.create(
        thread=thread,
        user=request.user,
        original_message=msg,
        ai_generated_body=draft_body,
        status='pending_review',
    )
    
    # AJAX response
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        from django.http import JsonResponse
        return JsonResponse({
            'success': True,
            'draft_id': draft.id,
            'draft_body': draft_body,
        })
    
    messages.success(request, 'AI draft generated. Review and approve below.')
    return redirect('inbox:draft_detail', draft_id=draft.id)


@require_POST
@login_required
@require_workspace_permission('inbox', 'delete')
def message_delete(request, message_id):
    msg = get_object_or_404(EmailMessage, id=message_id, thread__inbox__user=request.user)
    msg.is_deleted = True
    msg.deleted_at = timezone.now()
    msg.save(update_fields=['is_deleted', 'deleted_at'])
    messages.success(request, 'Message moved to trash.')
    inbox_id = request.GET.get('inbox_id') or request.POST.get('inbox_id')
    folder = request.GET.get('folder') or request.POST.get('folder') or 'inbox'
    url = reverse('inbox:dashboard')
    if inbox_id:
        url += f'?inbox_id={inbox_id}&folder={folder}'
    return redirect(url)


@require_POST
@login_required
@require_workspace_permission('inbox', 'edit')
def message_restore(request, message_id):
    msg = get_object_or_404(EmailMessage, id=message_id, thread__inbox__user=request.user)
    msg.is_deleted = False
    msg.save(update_fields=['is_deleted'])
    messages.success(request, 'Message restored from trash.')
    return redirect('inbox:dashboard')


@login_required
@require_workspace_permission('inbox', 'read')
def inbox_trash(request):
    inboxes = filter_by_context(request, EmailInbox.objects.all())
    selected_id = request.GET.get('inbox_id')
    selected_inbox = None
    if selected_id:
        selected_inbox = get_object_or_404(inboxes, id=selected_id)
    elif inboxes.exists():
        selected_inbox = inboxes.first()

    deleted_messages = EmailMessage.objects.filter(
        thread__inbox__in=filter_by_context(request, EmailInbox.objects.all()),
        is_deleted=True,
    ).select_related('thread__inbox').order_by('-received_at')

    if selected_inbox:
        deleted_messages = deleted_messages.filter(thread__inbox=selected_inbox)

    paginator = Paginator(deleted_messages, 20)
    page = request.GET.get('page', 1)
    page_obj = paginator.get_page(page)

    return render(request, 'inbox/trash.html', {
        'inboxes': inboxes,
        'selected_inbox': selected_inbox,
        'page_obj': page_obj,
        'deleted_messages': page_obj.object_list,
    })


@login_required
@require_workspace_permission('inbox', 'read')
def draft_detail(request, draft_id):
    draft = get_object_or_404(EmailDraft, id=draft_id, user=request.user)
    return render(request, 'inbox/draft_detail.html', {'draft': draft})


@login_required
@require_workspace_permission('inbox', 'edit')
def draft_review(request, draft_id):
    draft = get_object_or_404(EmailDraft, id=draft_id, user=request.user)
    if request.method == 'POST':
        form = EmailDraftReviewForm(request.POST, instance=draft)
        if form.is_valid():
            edited = form.save(commit=False)
            if not edited.edited_body:
                edited.edited_body = edited.ai_generated_body
            if edited.status == 'approved':
                edited.final_body = edited.edited_body or edited.ai_generated_body
            edited.save()
            messages.success(request, 'Draft updated.')
            return redirect('inbox:draft_detail', draft_id=draft.id)
        else:
            messages.error(request, 'Please correct the errors.')
    else:
        form = EmailDraftReviewForm(instance=draft)

    return render(request, 'inbox/draft_review.html', {
        'form': form,
        'draft': draft,
    })


@require_POST
@login_required
@require_workspace_permission('inbox', 'edit')
def draft_approve(request, draft_id):
    draft = get_object_or_404(EmailDraft, id=draft_id, user=request.user)
    draft.status = 'approved'
    draft.final_body = draft.edited_body or draft.ai_generated_body
    draft.save(update_fields=['status', 'final_body', 'updated_at'])
    messages.success(request, 'Draft approved.')
    return redirect('inbox:draft_detail', draft_id=draft.id)


@require_POST
@login_required
@require_workspace_permission('inbox', 'edit')
def draft_send(request, draft_id):
    logger.info(f"[DRAFT_SEND] Starting send for draft {draft_id}")
    draft = get_object_or_404(EmailDraft, id=draft_id, user=request.user)
    logger.info(f"[DRAFT_SEND] Draft status: {draft.status}")
    
    # Auto-approve if not already approved
    if draft.status != 'approved':
        draft.status = 'approved'
        draft.final_body = draft.edited_body or draft.ai_generated_body
        draft.save(update_fields=['status', 'final_body', 'updated_at'])
        logger.info(f"[DRAFT_SEND] Auto-approved draft {draft_id}")
    
    body = draft.final_body or draft.edited_body or draft.ai_generated_body
    logger.info(f"[DRAFT_SEND] Body length: {len(body) if body else 0}")
    
    if not body:
        logger.error(f"[DRAFT_SEND] No body content")
        messages.error(request, 'Draft has no content to send.')
        return redirect('inbox:draft_detail', draft_id=draft.id)

    original_msg = draft.original_message
    if not original_msg:
        logger.error(f"[DRAFT_SEND] No original message")
        messages.error(request, 'Original message not found.')
        return redirect('inbox:draft_detail', draft_id=draft.id)

    sender = Sender.objects.filter(user=request.user, is_active=True).first()
    if not sender:
        logger.error(f"[DRAFT_SEND] No active sender")
        messages.error(request, 'No active SMTP sender found. Configure a sender first.')
        return redirect('inbox:draft_detail', draft_id=draft.id)
    
    sender.reset_daily_quota_if_needed()
    if sender.is_limit_reached:
        logger.error(f"[DRAFT_SEND] Limit reached")
        messages.error(request, f'Daily sending limit ({sender.daily_limit}) reached for {sender.from_email}.')
        return redirect('inbox:draft_detail', draft_id=draft.id)
    
    smtp_password = sender.get_password()
    logger.info(f"[DRAFT_SEND] Password retrieved: {smtp_password is not None}")
    
    if not smtp_password:
        logger.error(f"[DRAFT_SEND] Password decryption failed")
        messages.error(request, 'Could not decrypt sender password. Re-save sender credentials.')
        return redirect('inbox:draft_detail', draft_id=draft.id)

    to_address = original_msg.from_email
    if not to_address:
        logger.error(f"[DRAFT_SEND] No recipient")
        messages.error(request, 'No recipient found.')
        return redirect('inbox:draft_detail', draft_id=draft.id)

    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.utils import formatdate, make_msgid
    import smtplib
    import ssl
    
    try:
        domain = sender.from_email.split('@')[-1] if '@' in sender.from_email else 'mailflow.ai'
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"Re: {draft.thread.subject}" if draft.thread.subject else 'Re:'
        msg['From'] = f"{sender.display_name} <{sender.from_email}>"
        msg['To'] = to_address
        msg['Message-ID'] = make_msgid(domain=domain)
        msg['Date'] = formatdate(localtime=True)
        msg['MIME-Version'] = '1.0'
        msg['X-Priority'] = '3'
        msg['X-Mailer'] = 'MailFlow AI'
        
        if sender.reply_to:
            msg['Reply-To'] = sender.reply_to
        
        part = MIMEText(body, 'html' if '<' in body else 'plain')
        msg.attach(part)

        max_retries = 3
        last_error = None
        
        logger.info(f"[DRAFT_SEND] Attempting to send via SMTP: {sender.smtp_host}:{sender.smtp_port}")
        
        for attempt in range(max_retries):
            try:
                if sender.smtp_port == 465:
                    with smtplib.SMTP_SSL(sender.smtp_host, sender.smtp_port, timeout=30) as server:
                        logger.info(f"[DRAFT_SEND] Connected via SSL, logging in...")
                        server.login(sender.username, smtp_password)
                        logger.info(f"[DRAFT_SEND] Login successful, sending...")
                        server.sendmail(msg['From'], [to_address], msg.as_string())
                        logger.info(f"[DRAFT_SEND] Send successful")
                else:
                    with smtplib.SMTP(sender.smtp_host, sender.smtp_port, timeout=30) as server:
                        server.ehlo()
                        if sender.use_tls:
                            server.starttls(context=ssl.create_default_context())
                            server.ehlo()
                        logger.info(f"[DRAFT_SEND] Connected via STARTTLS, logging in...")
                        server.login(sender.username, smtp_password)
                        logger.info(f"[DRAFT_SEND] Login successful, sending...")
                        server.sendmail(msg['From'], [to_address], msg.as_string())
                        logger.info(f"[DRAFT_SEND] Send successful")
                
                break
            except smtplib.SMTPAuthenticationError as auth_err:
                logger.error(f"[DRAFT_SEND] SMTP authentication failed: {auth_err}")
                error_str = str(auth_err)
                if '535' in error_str:
                    messages.error(request, 'SMTP authentication failed: Invalid username or password. Please re-save your sender credentials in Settings.')
                elif '534' in error_str:
                    messages.error(request, 'SMTP authentication failed: App Password required. For Gmail, create an App Password at myaccount.google.com/apppasswords and use that instead of your regular password.')
                else:
                    messages.error(request, f'SMTP authentication failed: {error_str}')
                return redirect('inbox:draft_detail', draft_id=draft.id)
            except smtplib.SMTPRecipientsRefused as recip_err:
                logger.error(f"[DRAFT_SEND] Recipient refused: {recip_err}")
                recipient_email = list(recip_err.recipients.keys())[0] if recip_err.recipients else 'recipient'
                messages.error(request, f'Recipient address rejected: {recipient_email}. Please verify the email address is correct.')
                return redirect('inbox:draft_detail', draft_id=draft.id)
            except smtplib.SMTPServerDisconnected as disc_err:
                logger.error(f"[DRAFT_SEND] SMTP server disconnected: {disc_err}")
                messages.error(request, 'SMTP server disconnected unexpectedly. Please check your connection settings and try again.')
                return redirect('inbox:draft_detail', draft_id=draft.id)
            except (smtplib.SMTPException, ConnectionError) as send_err:
                last_error = str(send_err)
                logger.warning(f"[DRAFT_SEND] Send attempt {attempt + 1} failed: {send_err}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2 ** attempt)
                else:
                    raise
        
        Sender.objects.filter(pk=sender.pk).update(emails_sent_today=F('emails_sent_today') + 1)
        draft.status = 'sent'
        draft.save(update_fields=['status', 'updated_at'])
        logger.info(f"[DRAFT_SEND] Draft {draft_id} marked as sent")
        messages.success(request, 'Draft sent successfully.')
        
    except Exception as e:
        logger.exception(f"[DRAFT_SEND] Failed to send draft {draft.id} after retries: {e}")
        error_msg = str(e)
        if 'authentication' in error_msg.lower() or 'auth' in error_msg.lower():
            messages.error(request, 'SMTP authentication failed. Please verify your credentials in Settings.')
        elif 'connection' in error_msg.lower() or 'timeout' in error_msg.lower():
            messages.error(request, 'SMTP connection timed out. Check your internet connection and SMTP server settings.')
        elif 'tls' in error_msg.lower() or 'ssl' in error_msg.lower():
            messages.error(request, 'TLS/SSL handshake failed. Try enabling or disabling TLS in your sender settings.')
        elif 'recipient' in error_msg.lower():
            messages.error(request, 'Recipient address was rejected. Please verify the email address is correct.')
        else:
            messages.error(request, f'Failed to send draft: {error_msg}')
    return redirect('inbox:draft_detail', draft_id=draft.id)


@login_required
@require_POST
def draft_send_test(request, draft_id):
    """Send a test copy of the draft to the user's own email."""
    logger.info(f"[DRAFT_SEND_TEST] Starting test send for draft {draft_id}")
    draft = get_object_or_404(EmailDraft, id=draft_id, user=request.user)
    
    # Auto-approve if not already approved
    if draft.status != 'approved':
        draft.status = 'approved'
        draft.final_body = draft.edited_body or draft.ai_generated_body
        draft.save(update_fields=['status', 'final_body', 'updated_at'])
        logger.info(f"[DRAFT_SEND_TEST] Auto-approved draft {draft_id}")
    
    body = draft.final_body or draft.edited_body or draft.ai_generated_body
    
    if not body:
        messages.error(request, 'Draft has no content to send.')
        return redirect('inbox:draft_detail', draft_id=draft.id)
    
    original_msg = draft.original_message
    if not original_msg:
        messages.error(request, 'Original message not found.')
        return redirect('inbox:draft_detail', draft_id=draft.id)
    
    sender = Sender.objects.filter(user=request.user, is_active=True).first()
    if not sender:
        messages.error(request, 'No active SMTP sender found. Configure a sender first.')
        return redirect('inbox:draft_detail', draft_id=draft.id)
    
    sender.reset_daily_quota_if_needed()
    if sender.is_limit_reached:
        messages.error(request, f'Daily sending limit ({sender.daily_limit}) reached for {sender.from_email}.')
        return redirect('inbox:draft_detail', draft_id=draft.id)
    
    smtp_password = sender.get_password()
    if not smtp_password:
        messages.error(request, 'Could not decrypt sender password. Re-save sender credentials.')
        return redirect('inbox:draft_detail', draft_id=draft.id)
    
    # Send to user's own email instead of original recipient
    to_address = request.user.email
    if not to_address:
        messages.error(request, 'Your user account does not have an email address set.')
        return redirect('inbox:draft_detail', draft_id=draft.id)
    
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.utils import formatdate, make_msgid
    import smtplib
    import ssl
    
    try:
        domain = sender.from_email.split('@')[-1] if '@' in sender.from_email else 'mailflow.ai'
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"[TEST] Re: {draft.thread.subject}" if draft.thread.subject else '[TEST]'
        msg['From'] = f"{sender.display_name} <{sender.from_email}>"
        msg['To'] = to_address
        msg['Message-ID'] = make_msgid(domain=domain)
        msg['Date'] = formatdate(localtime=True)
        msg['MIME-Version'] = '1.0'
        msg['X-Priority'] = '3'
        msg['X-Mailer'] = 'MailFlow AI (Test)'
        
        if sender.reply_to:
            msg['Reply-To'] = sender.reply_to
        
        # Add test header
        test_header = (
            "<div style='background:#fef3c7;border-left:4px solid #f59e0b;padding:12px;margin-bottom:20px;'>"
            "<strong>🧪 TEST EMAIL</strong> - This is a test copy. The original recipient will not receive this.</div>"
        )
        full_body = test_header + body
        part = MIMEText(full_body, 'html' if '<' in body else 'plain')
        msg.attach(part)
        
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                if sender.smtp_port == 465:
                    with smtplib.SMTP_SSL(sender.smtp_host, sender.smtp_port, timeout=30) as server:
                        server.login(sender.username, smtp_password)
                        server.sendmail(msg['From'], [to_address], msg.as_string())
                else:
                    with smtplib.SMTP(sender.smtp_host, sender.smtp_port, timeout=30) as server:
                        server.ehlo()
                        if sender.use_tls:
                            server.starttls(context=ssl.create_default_context())
                            server.ehlo()
                        server.login(sender.username, smtp_password)
                        server.sendmail(msg['From'], [to_address], msg.as_string())
                break
            except smtplib.SMTPAuthenticationError as auth_err:
                logger.error(f"[DRAFT_SEND_TEST] SMTP authentication failed: {auth_err}")
                messages.error(request, 'SMTP authentication failed. Please verify your credentials.')
                return redirect('inbox:draft_detail', draft_id=draft.id)
            except (smtplib.SMTPException, ConnectionError) as send_err:
                last_error = str(send_err)
                logger.warning(f"[DRAFT_SEND_TEST] Send attempt {attempt + 1} failed: {send_err}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2 ** attempt)
                else:
                    raise
        
        Sender.objects.filter(pk=sender.pk).update(emails_sent_today=F('emails_sent_today') + 1)
        logger.info(f"[DRAFT_SEND_TEST] Test email sent successfully to {to_address}")
        messages.success(request, f'Test email sent to {to_address}. Check your inbox!')
        
    except Exception as e:
        logger.exception(f"[DRAFT_SEND_TEST] Failed to send test draft: {e}")
        messages.error(request, f'Failed to send test email: {str(e)}')
    
    return redirect('inbox:draft_detail', draft_id=draft.id)


@login_required
@require_GET
def proxy_email_image(request):
    """
    Proxy email images to protect user privacy and avoid CSP issues.
    Supports both CID references and external URLs.
    """
    cid = request.GET.get('cid')
    url = request.GET.get('url')
    
    if not cid and not url:
        return HttpResponse(status=400)
    
    try:
        if cid:
            # For CID references, we'd need to look up the actual image data
            # For now, return a placeholder
            # In a full implementation, you'd look up the CID in the message's inline images
            placeholder_svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">
                <rect width="100" height="100" fill="#f1f5f9"/>
                <text x="50" y="55" font-family="system-ui" font-size="12" fill="#94a3b8" text-anchor="middle">Image</text>
            </svg>'''
            return HttpResponse(placeholder_svg, content_type='image/svg+xml')
        
        elif url:
            # Proxy external image
            import httpx
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return HttpResponse(status=400)
            
            # Fetch the image with timeout
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                response = client.get(url, headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; MailFlow Image Proxy)',
                    'Accept': 'image/*,*/*;q=0.8',
                })
                response.raise_for_status()
                
                content_type = response.headers.get('content-type', 'image/png')
                # Only allow image content types
                if not content_type.startswith('image/'):
                    return HttpResponse(status=400)
                
                # Return with caching headers
                response_http = HttpResponse(response.content, content_type=content_type)
                response_http['Cache-Control'] = 'public, max-age=86400, immutable'
                response_http['X-Content-Type-Options'] = 'nosniff'
                return response_http
                
    except httpx.TimeoutException:
        return HttpResponse(status=504)
    except httpx.HTTPStatusError as e:
        return HttpResponse(status=e.response.status_code)
    except Exception as e:
        logger.warning(f"Image proxy error: {e}")
        return HttpResponse(status=500)

