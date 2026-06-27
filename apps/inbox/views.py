import base64
import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.intelligence.services.inbox_ai import (generate_draft_reply,
                                                 summarize_thread)
from apps.senders.models import Sender
from apps.workspaces.decorators import require_workspace_permission
from apps.workspaces.query_helpers import filter_by_context

from .forms import EmailDraftReviewForm, EmailInboxConnectForm
from .models import EmailDraft, EmailInbox, EmailMessage
from .services.rendering import render_email_for_display

logger = logging.getLogger(__name__)


def _is_safe_public_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (
            443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return False
    return True


@login_required
@require_workspace_permission('inbox', 'read')
def inbox_dashboard(request):
    inboxes = filter_by_context(request, EmailInbox.objects.all())
    stale_cutoff = timezone.now() - timezone.timedelta(minutes=10)
    stale_syncing = inboxes.filter(
        last_sync_status='syncing', updated_at__lt=stale_cutoff)
    if stale_syncing.exists():
        stale_syncing.update(
            last_sync_status='error',
            last_sync_error='Sync timed out. Click sync to retry.',
        )
    selected_id = request.GET.get('inbox_id')
    folder = request.GET.get('folder', 'inbox')
    page = request.GET.get('page', 1)
    query = request.GET.get('q', '').strip()

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
            ).select_related('thread__inbox').order_by('-received_at')
            if query:
                messages_qs = messages_qs.filter(
                    Q(subject__icontains=query)
                    | Q(from_email__icontains=query)
                    | Q(from_name__icontains=query)
                    | Q(body_text__icontains=query)
                )
            paginator = Paginator(messages_qs, 20)
            page_obj = paginator.get_page(page)
            messages_list = page_obj.object_list

    trash_count = EmailMessage.objects.filter(
        thread__inbox__in=inboxes,
        is_deleted=True,
    ).count()
    unread_count = EmailMessage.objects.filter(
        thread__inbox=selected_inbox,
        is_incoming=True,
        is_deleted=False,
        is_read=False,
    ).count() if selected_inbox else 0

    template = '_dashboard_content.html' if request.headers.get(
        'HX-Request') else 'dashboard.html'
    return render(request, f'inbox/{template}', {
        'inboxes': inboxes,
        'selected_inbox': selected_inbox,
        'folder': folder,
        'email_messages': messages_list,
        'drafts': drafts_list,
        'page_obj': page_obj,
        'trash_count': trash_count,
        'unread_count': unread_count,
        'query': query,
    })


@login_required
@require_workspace_permission('inbox', 'create')
def inbox_connect(request):
    reconnect_id = request.GET.get('reconnect')
    reconnect_inbox = None
    if reconnect_id:
        try:
            reconnect_inbox = get_object_or_404(filter_by_context(
                request, EmailInbox.objects.all()), id=reconnect_id)
        except EmailInbox.DoesNotExist:
            pass

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'

    if request.method == 'POST':
        form = EmailInboxConnectForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email_address']
            existing = filter_by_context(
                request, EmailInbox.objects.filter(email_address=email))

            if reconnect_inbox and reconnect_inbox.email_address == email:
                inbox = reconnect_inbox
                inbox.provider = form.cleaned_data['provider']
            elif existing.exists():
                if is_ajax:
                    return JsonResponse({'success': False, 'error': f'Inbox "{email}" is already connected.'})
                messages.error(
                    request, f'Inbox "{email}" is already connected.')
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
            try:
                if imap_password:
                    inbox.set_token(imap_password)
            except Exception as token_err:
                logger.error(f"Failed to encrypt token for inbox {email}: {token_err}")
                if is_ajax:
                    return JsonResponse({
                        'success': False,
                        'error': 'Failed to store credentials securely. Please try again.',
                    })
                messages.error(request, 'Failed to store credentials securely. Please try again.')
                return render(request, 'inbox/connect.html', {
                    'form': form,
                    'existing_inboxes': filter_by_context(request, EmailInbox.objects.all()),
                    'reconnect_inbox': reconnect_inbox,
                })
            inbox.last_sync_status = 'pending'
            inbox.last_sync_error = ''
            inbox.save()

            from .tasks import sync_inbox_task
            try:
                transaction.on_commit(lambda: sync_inbox_task.delay(
                    inbox.id, workspace_id=inbox.workspace_id))
                if reconnect_inbox:
                    messages.success(
                        request, f'{inbox.get_provider_display()} inbox reconnected. Sync started.')
                else:
                    messages.success(
                        request, f'{inbox.get_provider_display()} inbox connected. Initial sync started.')
            except Exception:
                logger.warning(
                    "Celery unavailable, running sync synchronously")
                try:
                    count = sync_inbox_task(
                        inbox.id, workspace_id=inbox.workspace_id)
                    messages.success(
                        request, f'{inbox.get_provider_display()} inbox {"re" if reconnect_inbox else ""}connected. Synced {count} messages.')
                except Exception as e2:
                    logger.error(f"Sync failed: {e2}")
                    messages.warning(
                        request, f'{inbox.get_provider_display()} inbox {"re" if reconnect_inbox else ""}connected, but sync failed. You can retry from the dashboard.')

            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'inbox_id': inbox.id,
                    'email': inbox.email_address,
                    'redirect_url': reverse('inbox:dashboard') + f'?inbox_id={inbox.id}',
                })
            return redirect('inbox:dashboard')
        else:
            if is_ajax:
                errors = {}
                for field, err_list in form.errors.items():
                    errors[field] = [str(e) for e in err_list]
                return JsonResponse({'success': False, 'error': 'Please correct the errors below.', 'field_errors': errors})
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
@require_POST
def inbox_sync(request, inbox_id):
    inbox = get_object_or_404(filter_by_context(
        request, EmailInbox.objects.all()), id=inbox_id)
    password = inbox.get_token()

    if not password:
        inbox.last_sync_status = 'error'
        inbox.last_sync_error = 'No password stored. Please reconnect the inbox.'
        inbox.save(update_fields=['last_sync_status', 'last_sync_error'])
        msg = 'No password stored. Please reconnect the inbox.'
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': msg})
        messages.warning(
            request,
            f'No password stored for {inbox.email_address}. '
            f'<a href="{reverse("inbox:connect")}?reconnect={inbox.id}" class="underline font-semibold">Reconnect</a> to restore sync.',
        )
        return redirect('inbox:dashboard')

    if inbox.last_sync_status == 'syncing':
        stale_cutoff = timezone.now() - timezone.timedelta(minutes=10)
        if inbox.updated_at and inbox.updated_at < stale_cutoff:
            inbox.last_sync_status = 'pending'
            inbox.last_sync_error = 'Previous sync timed out. Please retry.'
            inbox.save(update_fields=['last_sync_status', 'last_sync_error'])
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'Sync already in progress.'})
            messages.warning(request, 'Sync already in progress.')
            return redirect('inbox:dashboard')

    from .tasks import sync_inbox_task
    inbox.last_sync_status = 'syncing'
    inbox.last_sync_error = ''
    inbox.last_synced_at = None
    inbox.save(update_fields=['last_sync_status',
               'last_sync_error', 'last_synced_at'])

    try:
        transaction.on_commit(lambda: sync_inbox_task.delay(
            inbox.id, workspace_id=inbox.workspace_id))
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': 'Sync started'})
        messages.success(request, 'Sync started')
    except Exception as exc:
        logger.warning(
            "Celery unavailable, running sync synchronously for inbox %s", inbox.id)
        try:
            count = sync_inbox_task(inbox.id, workspace_id=inbox.workspace_id)
            inbox.last_sync_status = 'success'
            inbox.last_sync_error = ''
            inbox.last_synced_at = timezone.now()
            inbox.save(update_fields=['last_sync_status',
                       'last_sync_error', 'last_synced_at'])
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'status': 'success', 'count': count})
            messages.success(
                request, f'Synced {inbox.email_address}: {count} new message(s).')
            return redirect(f'{reverse("inbox:dashboard")}?inbox_id={inbox.id}')
        except Exception as e2:
            logger.exception("Sync failed for inbox %s", inbox.id)
            inbox.last_sync_status = 'error'
            inbox.last_sync_error = str(e2)
            inbox.save(update_fields=['last_sync_status', 'last_sync_error'])
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': str(e2)})
            messages.error(
                request, f'Sync failed for {inbox.email_address}. Try again.')
            return redirect('inbox:dashboard')

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'status': 'syncing',
            'inbox_id': inbox.id,
        })
    messages.success(request, f'Sync started for {inbox.email_address}.')
    return redirect(f'{reverse("inbox:dashboard")}?inbox_id={inbox.id}')


@login_required
@require_GET
@require_workspace_permission('inbox', 'read')
def inbox_sync_status(request, inbox_id):
    """Lightweight endpoint to check sync status. Returns JSON."""
    inbox = get_object_or_404(filter_by_context(
        request, EmailInbox.objects.all()), id=inbox_id)
    return JsonResponse({
        'inbox_id': inbox.id,
        'status': inbox.last_sync_status,
        'error': inbox.last_sync_error or '',
        'last_synced_at': inbox.last_synced_at.isoformat() if inbox.last_synced_at else None,
    })


@login_required
@require_workspace_permission('inbox', 'create')
def inbox_auto_reply(request, inbox_id):
    """Trigger auto-reply for unread incoming messages in this inbox."""
    inbox = get_object_or_404(filter_by_context(
        request, EmailInbox.objects.all()), id=inbox_id)
    from apps.intelligence.services.auto_reply import (classify_importance,
                                                       is_human_email,
                                                       process_auto_reply)

    from .models import EmailDraft, EmailMessage

    messages_list = EmailMessage.objects.filter(
        thread__inbox=inbox,
        is_incoming=True,
        is_deleted=False,
    ).select_related('thread').order_by('-received_at')[:20]

    processed = 0
    skipped = 0
    for msg in messages_list:
        if not is_human_email(msg.from_email, msg.from_name, msg.subject):
            skipped += 1
            continue
        existing_draft = EmailDraft.objects.filter(
            thread=msg.thread,
            user=request.user,
            status__in=['pending_review', 'edited', 'approved'],
        ).exists()
        if existing_draft:
            skipped += 1
            continue
        importance, intent = classify_importance(
            msg.subject or '',
            msg.body_text or '',
        )
        if importance not in ('medium', 'high', 'urgent'):
            skipped += 1
            continue
        from apps.intelligence.services.auto_reply import generate_auto_reply
        draft_body = generate_auto_reply(
            subject=msg.subject or '',
            body_text=msg.body_text or '',
            thread_summary=msg.thread.ai_summary or '',
            importance=importance,
            intent=intent,
            from_name=msg.from_name or '',
        )
        if draft_body:
            EmailDraft.objects.create(
                thread=msg.thread,
                user=request.user,
                workspace=msg.thread.inbox.workspace,
                original_message=msg,
                ai_generated_body=draft_body,
                edited_body=draft_body,
                status='pending_review',
                final_body='',
            )
            processed += 1
        else:
            skipped += 1

    msg = f'Auto-reply processed. {processed} draft(s) created, {skipped} skipped.'
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'processed': processed, 'skipped': skipped, 'message': msg})
    messages.success(request, msg)
    return redirect('inbox:dashboard')


@login_required
@require_workspace_permission('inbox', 'create')
@require_POST
def bulk_auto_reply(request):
    """Auto-reply to selected messages."""
    import json

    try:
        data = json.loads(request.body)
        message_ids = data.get('message_ids', [])
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid request.'})

    if not message_ids:
        return JsonResponse({'success': False, 'error': 'No messages selected.'})

    from .models import EmailDraft, EmailMessage
    messages_to_process = EmailMessage.objects.filter(
        id__in=message_ids,
        thread__inbox__in=filter_by_context(request, EmailInbox.objects.all()),
        is_incoming=True,
        is_deleted=False,
    ).select_related('thread')

    processed = 0
    skipped = 0
    for msg in messages_to_process:
        existing_draft = EmailDraft.objects.filter(
            thread=msg.thread,
            user=request.user,
            status__in=['pending_review', 'edited', 'approved'],
        ).exists()
        if existing_draft:
            skipped += 1
            continue
        try:
            if process_auto_reply(msg.id):
                processed += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1

    return JsonResponse({
        'success': True,
        'processed': processed,
        'skipped': skipped,
    })


@login_required
@require_workspace_permission('inbox', 'delete')
def inbox_disconnect(request, inbox_id):
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('inbox:dashboard')
    inbox = get_object_or_404(filter_by_context(
        request, EmailInbox.objects.all()), id=inbox_id)
    inbox.delete()
    messages.success(request, 'Inbox disconnected.')
    return redirect('inbox:dashboard')


@login_required
@require_workspace_permission('inbox', 'read')
def message_detail(request, message_id):
    msg = get_object_or_404(EmailMessage.objects.select_related(
        'thread__inbox'), id=message_id,
        thread__inbox__in=filter_by_context(request, EmailInbox.objects.all()))

    # Mark as read
    if not msg.is_read:
        msg.is_read = True
        msg.save(update_fields=['is_read'])

    # Build inline CIDs dict from the raw body_html
    inline_cids = {}
    if msg.body_html and 'cid:' in msg.body_html:
        cids = set(re.findall(r'cid:([\w\.\-\+]+)', msg.body_html))
        for cid in cids:
            inline_cids[cid] = f"/inbox/proxy-image/?cid={cid}"

    email_html = render_email_for_display(
        body_html=msg.body_html,
        body_text=msg.body_text,
        inline_cids=inline_cids or None,
    )

    drafts = EmailDraft.objects.filter(
        original_message=msg,
        thread__inbox__in=filter_by_context(request, EmailInbox.objects.all())
    ).order_by('-created_at')

    now = timezone.now()
    sender = filter_by_context(
        request, Sender.objects.filter(is_active=True)).first()

    import hashlib
    avatar_hue = int(hashlib.md5((msg.from_email or '').encode(
        'utf-8')).hexdigest()[:6], 16) % 360 if msg.from_email else 0

    return render(request, 'inbox/message_detail.html', {
        'msg': msg,
        'email_html': email_html,
        'drafts': drafts,
        'summarized': request.GET.get('summarized'),
        'sender': sender,
        'now': now,
        'avatar_hue': avatar_hue,
    })


@login_required
@require_workspace_permission('inbox', 'read')
def message_summarize(request, message_id):
    msg = get_object_or_404(EmailMessage, id=message_id,
                            thread__inbox__in=filter_by_context(request, EmailInbox.objects.all()))
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
    msg = get_object_or_404(EmailMessage, id=message_id,
                            thread__inbox__in=filter_by_context(request, EmailInbox.objects.all()))
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

    update_draft_id = request.POST.get(
        'draft_id') or request.headers.get('X-Draft-Id')
    draft = None
    if update_draft_id:
        draft = EmailDraft.objects.filter(
            id=update_draft_id,
            user=request.user,
            original_message=msg,
        ).exclude(status='sent').first()

    if draft:
        draft.ai_generated_body = draft_body
        draft.edited_body = draft_body
        draft.final_body = ''
        draft.status = 'pending_review'
        draft.ai_generated = True
        draft.save(update_fields=[
            'ai_generated_body',
            'edited_body',
            'final_body',
            'status',
            'ai_generated',
            'updated_at',
        ])
    else:
        draft = EmailDraft.objects.create(
            thread=thread,
            user=request.user,
            workspace=thread.inbox.workspace,
            original_message=msg,
            ai_generated_body=draft_body,
            edited_body=draft_body,
            status='pending_review',
            ai_generated=True,
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


@login_required
@require_workspace_permission('inbox', 'delete')
@require_POST
def message_delete(request, message_id):
    msg = get_object_or_404(EmailMessage, id=message_id,
                            thread__inbox__in=filter_by_context(request, EmailInbox.objects.all()))
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


@login_required
@require_workspace_permission('inbox', 'delete')
@require_POST
def draft_delete(request, draft_id):
    draft = get_object_or_404(EmailDraft, id=draft_id, user=request.user, thread__inbox__in=filter_by_context(request, EmailInbox.objects.all()))
    draft.delete()
    messages.success(request, 'Draft deleted.')
    return redirect('inbox:dashboard')


@login_required
@require_workspace_permission('inbox', 'edit')
@require_POST
def message_restore(request, message_id):
    msg = get_object_or_404(EmailMessage, id=message_id,
                            thread__inbox__in=filter_by_context(request, EmailInbox.objects.all()))
    msg.is_deleted = False
    msg.save(update_fields=['is_deleted'])
    messages.success(request, 'Message restored from trash.')
    return redirect('inbox:dashboard')


@login_required
@require_workspace_permission('inbox', 'delete')
@require_POST
def bulk_action(request):
    """Perform bulk actions on messages (delete, etc)."""
    import json

    try:
        data = json.loads(request.body)
        action = data.get('action', '')
        message_ids = data.get('message_ids', [])
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid request.'})

    if not message_ids:
        return JsonResponse({'success': False, 'error': 'No messages selected.'})

    messages_to_process = EmailMessage.objects.filter(
        id__in=message_ids,
        thread__inbox__in=filter_by_context(request, EmailInbox.objects.all()),
        is_deleted=False,
    )

    if action == 'delete':
        count = messages_to_process.update(
            is_deleted=True, deleted_at=timezone.now())
        return JsonResponse({'success': True, 'count': count})

    return JsonResponse({'success': False, 'error': f'Unknown action: {action}'})


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
        thread__inbox__in=inboxes,
        is_deleted=True,
    ).select_related('thread__inbox').order_by('-received_at')

    if selected_inbox:
        deleted_messages = deleted_messages.filter(
            thread__inbox=selected_inbox)

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
    draft = get_object_or_404(EmailDraft.objects.select_related(
        'thread__inbox', 'original_message'), id=draft_id, user=request.user,
        thread__inbox__in=filter_by_context(request, EmailInbox.objects.all()))
    sender = filter_by_context(
        request, Sender.objects.filter(is_active=True)).first()
    return render(request, 'inbox/draft_detail.html', {'draft': draft, 'sender': sender})


@login_required
@require_workspace_permission('inbox', 'edit')
def draft_review(request, draft_id):
    draft = get_object_or_404(EmailDraft, id=draft_id, user=request.user,
        thread__inbox__in=filter_by_context(request, EmailInbox.objects.all()))
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
    draft = get_object_or_404(EmailDraft, id=draft_id, user=request.user,
        thread__inbox__in=filter_by_context(request, EmailInbox.objects.all()))
    body = request.POST.get('body', '').strip()
    if body:
        draft.edited_body = body
    draft.status = 'approved'
    draft.final_body = draft.edited_body or draft.ai_generated_body
    draft.save(update_fields=['status', 'final_body',
               'edited_body', 'updated_at'])
    messages.success(request, 'Draft saved and approved.')
    return redirect('inbox:draft_detail', draft_id=draft.id)


@require_POST
@login_required
@require_workspace_permission('inbox', 'edit')
def draft_send(request, draft_id):
    draft = get_object_or_404(EmailDraft, id=draft_id, user=request.user,
        thread__inbox__in=filter_by_context(request, EmailInbox.objects.all()))
    post_body = request.POST.get('body', '').strip()
    if post_body:
        draft.edited_body = post_body

    if draft.status != 'approved':
        draft.status = 'approved'
    draft.final_body = draft.edited_body or draft.ai_generated_body
    draft.save(update_fields=['status', 'final_body',
               'edited_body', 'updated_at'])

    body = draft.final_body or draft.edited_body or draft.ai_generated_body
    try:
        from .services.smtp import EmailSendError, send_draft_reply
        send_draft_reply(
            draft=draft,
            request=request,
            body=body,
            to_address=request.POST.get('to_address', ''),
            cc_addresses=request.POST.get('cc_addresses', ''),
            bcc_addresses=request.POST.get('bcc_addresses', ''),
        )
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': 'Draft sent successfully.',
                'redirect': reverse('inbox:draft_detail', kwargs={'draft_id': draft.id})
            })
        messages.success(request, 'Draft sent successfully.')
    except EmailSendError as exc:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': exc.message
            })
        messages.error(request, exc.message)
    except Exception as exc:
        logger.exception("Failed to send draft %s: %s", draft.id, exc)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': 'Failed to send draft. Please try again.'
            })
        messages.error(request, 'Failed to send draft. Please try again.')
    return redirect('inbox:draft_detail', draft_id=draft.id)


@login_required
@require_POST
@require_workspace_permission('inbox', 'edit')
def draft_send_test(request, draft_id):
    """Send a test copy of the draft to the user's own email."""
    draft = get_object_or_404(EmailDraft, id=draft_id, user=request.user,
        thread__inbox__in=filter_by_context(request, EmailInbox.objects.all()))

    post_body = request.POST.get('body', '').strip()
    if post_body:
        draft.edited_body = post_body

    if draft.status != 'approved':
        draft.status = 'approved'
    draft.final_body = draft.edited_body or draft.ai_generated_body
    draft.save(update_fields=['status', 'final_body',
               'edited_body', 'updated_at'])

    body = draft.final_body or draft.edited_body or draft.ai_generated_body
    try:
        from .services.smtp import EmailSendError, send_test_draft
        result = send_test_draft(draft=draft, request=request, body=body)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': f'Test email sent to {result.recipient}. Check your inbox!'
            })
        messages.success(
            request, f'Test email sent to {result.recipient}. Check your inbox!')
    except EmailSendError as exc:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': exc.message
            })
        messages.error(request, exc.message)
    except Exception as exc:
        logger.exception("Failed to send test draft %s: %s", draft.id, exc)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': 'Failed to send test email. Please try again.'
            })
        messages.error(request, 'Failed to send test email. Please try again.')

    return redirect('inbox:draft_detail', draft_id=draft.id)


@login_required
@require_workspace_permission('inbox', 'read')
@require_GET
def sender_logo_proxy(request):
    """Proxy sender logos to bypass CSP/ad-blocker issues.

    Tries Google Favicons first, then Clearbit as fallback.
    Returns a 1x1 transparent GIF if both fail (triggers onerror in browser).
    """
    domain = request.GET.get('domain', '').strip().lower()
    if not domain or not re.match(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\.[a-z]{2,}$', domain):
        transparent_pixel = base64.b64decode(
            'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
        return HttpResponse(transparent_pixel, content_type='image/gif')

    import httpx

    # Try Google Favicons
    try:
        google_url = f'https://www.google.com/s2/favicons?domain={domain}&sz=64'
        resp = httpx.get(google_url, timeout=10, follow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 200:
            r = HttpResponse(resp.content, content_type=resp.headers.get(
                'content-type', 'image/png'))
            r['Cache-Control'] = 'public, max-age=86400, immutable'
            r['X-Content-Type-Options'] = 'nosniff'
            return r
    except Exception:
        pass

    # Try Clearbit as fallback
    try:
        clearbit_url = f'https://logo.clearbit.com/{domain}'
        resp = httpx.get(clearbit_url, timeout=10, follow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 200:
            r = HttpResponse(resp.content, content_type=resp.headers.get(
                'content-type', 'image/png'))
            r['Cache-Control'] = 'public, max-age=86400, immutable'
            r['X-Content-Type-Options'] = 'nosniff'
            return r
    except Exception:
        pass

    transparent_pixel = base64.b64decode(
        'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
    return HttpResponse(transparent_pixel, content_type='image/gif')


@login_required
@require_workspace_permission('inbox', 'read')
@require_GET
def proxy_email_image(request):
    """
    Proxy email images to protect user privacy and avoid CSP issues.
    Supports both CID references and external URLs.
    """
    cid = request.GET.get('cid')
    url_b64 = request.GET.get('url')

    if not cid and not url_b64:
        return HttpResponse(status=400)

    try:
        if cid:
            try:
                from .models import EmailMessage
                msg = EmailMessage.objects.filter(
                    body_html__contains=f'cid:{cid}',
                    thread__inbox__in=filter_by_context(request, EmailInbox.objects.all()),
                ).order_by('-received_at').first()
                if msg and msg.body_html:
                    # Look for data URI matching this CID in src attribute
                    data_uri_match = re.search(
                        r'cid:' +
                        re.escape(cid) +
                        r'[^>]*src\s*=\s*["\'](data:[^"\']+)["\']',
                        msg.body_html, re.IGNORECASE
                    )
                    if not data_uri_match:
                        data_uri_match = re.search(
                            r'src\s*=\s*["\'](data:[^"\']+)["\'][^>]*cid:' +
                            re.escape(cid),
                            msg.body_html, re.IGNORECASE
                        )
                    if data_uri_match:
                        data_uri = data_uri_match.group(1)
                        if data_uri.startswith('data:'):
                            comma = data_uri.find(',')
                            if comma != -1:
                                header = data_uri[5:comma]
                                b64_data = data_uri[comma + 1:]
                                content_type = header.split(
                                    ';')[0] if ';' in header else 'image/png'
                                try:
                                    img_data = base64.b64decode(b64_data)
                                    resp = HttpResponse(
                                        img_data, content_type=content_type)
                                    resp['Cache-Control'] = 'public, max-age=86400, immutable'
                                    return resp
                                except Exception:
                                    pass
            except Exception:
                pass
            placeholder_svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">
                <rect width="100" height="100" fill="#f1f5f9"/>
                <text x="50" y="55" font-family="system-ui" font-size="12" fill="#94a3b8" text-anchor="middle">Image</text>
            </svg>'''
            return HttpResponse(placeholder_svg, content_type='image/svg+xml')

        elif url_b64:
            import httpx
            url_b64 = request.GET.get('url')
            if not url_b64:
                return HttpResponse(status=400)
            try:
                padded = url_b64 + '=' * (-len(url_b64) % 4)
                url = base64.urlsafe_b64decode(padded).decode()
            except Exception:
                url = url_b64
            if not _is_safe_public_url(url):
                return HttpResponse(status=400)
            headers = {
                'User-Agent': 'Mozilla/5.0 (compatible; MailFlow Image Proxy)',
                'Accept': 'image/*,*/*;q=0.8',
            }
            with httpx.Client(timeout=10.0, follow_redirects=False) as client:
                response = None
                current_url = url
                for _ in range(4):
                    if not _is_safe_public_url(current_url):
                        return HttpResponse(status=400)
                    response = client.get(current_url, headers=headers)
                    if response.status_code not in (301, 302, 303, 307, 308):
                        break
                    next_url = response.headers.get('location')
                    if not next_url:
                        return HttpResponse(status=400)
                    current_url = str(response.url.join(next_url))
                if response is None:
                    return HttpResponse(status=400)
                response.raise_for_status()
                content_type = response.headers.get(
                    'content-type', 'image/png')
                if not content_type.startswith('image/'):
                    return HttpResponse(status=400)
                if len(response.content) > 5 * 1024 * 1024:
                    return HttpResponse(status=413)
                response_http = HttpResponse(
                    response.content, content_type=content_type)
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
