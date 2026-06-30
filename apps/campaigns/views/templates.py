"""Email template management views."""

import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, HttpResponse

from django.urls import reverse
from django.contrib import messages

from apps.campaigns.models import EmailTemplate, TemplateImage
from apps.campaigns.default_templates import WELCOME_TEMPLATE, NEWSLETTER_TEMPLATE, PROMO_TEMPLATE, EVENT_TEMPLATE, THANK_YOU_TEMPLATE, FEEDBACK_TEMPLATE, REACTIVATION_TEMPLATE, PRODUCT_UPDATE_TEMPLATE
from apps.workspaces.decorators import require_workspace_permission
from apps.workspaces.query_helpers import filter_by_context
from core.tenant import get_current_tenant, tenant_context

def _get_template_or_404(request, template_id):
    """Fetch a template. Default templates (is_default=True) are accessible to all.
    Custom templates must belong to the current user (workspace=None in personal mode,
    or workspace matches session in workspace mode).
    Personal-mode templates (workspace=None) are accessible even in workspace mode.
    """
    user = request.user

    if not EmailTemplate._base_manager.filter(id=template_id).exists():
        raise Http404("No EmailTemplate matches the given query.")

    if EmailTemplate._base_manager.filter(id=template_id, is_default=True).exists():
        return get_object_or_404(EmailTemplate._base_manager, id=template_id, is_default=True)

    scoped = filter_by_context(request, EmailTemplate.objects.all())
    if scoped.filter(id=template_id).exists():
        return get_object_or_404(scoped, id=template_id)

    if EmailTemplate._base_manager.filter(id=template_id, user=user, workspace__isnull=True).exists():
        return get_object_or_404(EmailTemplate._base_manager, id=template_id, user=user, workspace__isnull=True)

    raise Http404("No EmailTemplate matches the given query.")

logger = logging.getLogger(__name__)



def _process_template_images(request, template):
    """Handle header/footer logo uploads and cid: embedded images."""
    # Header / footer logos
    for field in ('header_logo', 'footer_logo'):
        if request.FILES.get(field):
            setattr(template, field, request.FILES[field])
    # Existing embedded image replacements (image_profile.jpg, image_logo.png, etc.)
    prefix = 'image_'
    for key in request.FILES:
        if key.startswith(prefix):
            cid_name = key[len(prefix):]
            try:
                img_obj = template.images.get(cid_name=cid_name)
                img_obj.image = request.FILES[key]
                img_obj.save()
            except TemplateImage.DoesNotExist:
                logger.warning(f"TemplateImage {cid_name} not found for update")
    # New embedded image uploads (indexed names: cid_name_0, cid_image_0, ...)
    for key in list(request.FILES.keys()):
        if key.startswith('cid_image_'):
            idx = key[len('cid_image_'):]
            cid_name = request.POST.get(f'cid_name_{idx}', '').strip()
            if cid_name:
                cid_label = request.POST.get(f'cid_label_{idx}', '')
                template.images.update_or_create(
                    cid_name=cid_name,
                    defaults={
                        'image': request.FILES[key],
                        'label': cid_label or '',
                    },
                )



# Email Template Views (like Gmail templates)
def _get_template_category(name):
    """Derive a category from template name."""
    n = name.lower()
    if 'welcome' in n: return 'Welcome'
    if 'newsletter' in n: return 'Newsletter'
    if 'promo' in n or 'sale' in n or 'offer' in n: return 'Promotional'
    if 'event' in n or 'invite' in n: return 'Event'
    if 'thank' in n or 'feedback' in n: return 'Feedback'
    if 'reactivat' in n or 'win' in n: return 'Reactivation'
    if 'update' in n or 'product' in n or 'announce' in n: return 'Product Update'
    return 'General'


@login_required
@require_workspace_permission('campaigns', 'read')
def template_list(request):
    """List all email templates for the user, always including default templates."""
    defaults = [WELCOME_TEMPLATE, NEWSLETTER_TEMPLATE, PROMO_TEMPLATE, EVENT_TEMPLATE, THANK_YOU_TEMPLATE, FEEDBACK_TEMPLATE, REACTIVATION_TEMPLATE, PRODUCT_UPDATE_TEMPLATE]
    with tenant_context(None):
        for data in defaults:
            tpl, created = EmailTemplate._base_manager.get_or_create(
                user=request.user,
                name=data['name'],
                defaults={**data, 'is_default': True},
            )
            if not created:
                tpl.is_default = True
                tpl.save(update_fields=['is_default'])
    tenant = get_current_tenant()
    if tenant is not None:
        with tenant_context(None):
            templates = EmailTemplate.objects.filter(is_active=True).filter(
                Q(workspace=tenant) | Q(is_default=True)
            ).distinct()
    else:
        templates = filter_by_context(request, EmailTemplate.objects.filter(is_active=True))
    query = (request.GET.get('q') or '').strip()
    category_filter = request.GET.get('category') or ''
    if query:
        templates = templates.filter(Q(name__icontains=query) | Q(subject__icontains=query))
    if category_filter:
        filtered_ids = [t.id for t in templates if _get_template_category(t.name) == category_filter]
        templates = templates.filter(id__in=filtered_ids)
    if tenant is not None:
        with tenant_context(None):
            all_templates_for_cats = EmailTemplate.objects.filter(is_active=True).filter(
                Q(workspace=tenant) | Q(is_default=True)
            ).distinct()
    else:
        all_templates_for_cats = filter_by_context(request, EmailTemplate.objects.filter(is_active=True))
    categories = sorted(set(_get_template_category(t.name) for t in all_templates_for_cats))
    return render(request, 'campaigns/templates_list.html', {
        'templates': templates,
        'categories': categories,
        'current_category': category_filter,
    })



@login_required
@require_workspace_permission('campaigns', 'create')
def template_create(request):
    """Create a new email template."""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        subject = request.POST.get('subject', '').strip()
        body_html = request.POST.get('body_html', '').strip()
        body_text = request.POST.get('body_text', '').strip()
        header_text = request.POST.get('header_text', '').strip()
        footer_text = request.POST.get('footer_text', '').strip()

        if not name:
            messages.error(request, 'Template name is required.')
            return render(request, 'campaigns/template_form.html')

        # Check for case-insensitive duplicate name
        if filter_by_context(request, EmailTemplate.objects.filter(name__iexact=name)).exists():
            messages.error(request, f'A template named "{name}" already exists (case-insensitive).')
            return render(request, 'campaigns/template_form.html', {
                'name': name,
                'subject': subject,
                'body_html': body_html,
                'body_text': body_text,
                'header_text': header_text,
                'footer_text': footer_text,
            })

        template = EmailTemplate.objects.create(
            user=request.user,
            workspace_id=request.session.get('active_workspace_id'),
            name=name,
            subject=subject,
            body_html=body_html,
            body_text=body_text or '',
            header_text=header_text,
            footer_text=footer_text,
        )
        _process_template_images(request, template)
        template.save()
        messages.success(request, f'Template "{name}" created successfully.')
        return redirect('campaigns:template_list')

    return render(request, 'campaigns/template_form.html')



@login_required
@require_workspace_permission('campaigns', 'edit')
def template_edit(request, template_id):
    """Edit an existing email template."""
    template = _get_template_or_404(request, template_id)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        subject = request.POST.get('subject', '').strip()
        body_html = request.POST.get('body_html', '').strip()
        body_text = request.POST.get('body_text', '').strip()
        header_text = request.POST.get('header_text', '').strip()
        footer_text = request.POST.get('footer_text', '').strip()

        if not name:
            messages.error(request, 'Template name is required.')
            return render(request, 'campaigns/template_form.html', {'template': template})

        # Check for case-insensitive duplicate name (excluding current template)
        if filter_by_context(request, EmailTemplate.objects.filter(name__iexact=name)).exclude(id=template.id).exists():
            messages.error(request, f'A template named "{name}" already exists (case-insensitive).')
            return render(request, 'campaigns/template_form.html', {
                'template': template,
                'name': name,
                'subject': subject,
                'body_html': body_html,
                'body_text': body_text,
                'header_text': header_text,
                'footer_text': footer_text,
            })

        template.name = name
        template.subject = subject
        template.body_html = body_html
        template.body_text = body_text
        template.header_text = header_text
        template.footer_text = footer_text
        _process_template_images(request, template)
        template.save()
        messages.success(request, f'Template "{name}" updated successfully.')
        return redirect('campaigns:template_list')

    return render(request, 'campaigns/template_form.html', {'template': template})



@login_required
@require_workspace_permission('campaigns', 'delete')
def template_delete(request, template_id):
    """Delete (soft-delete) an email template. Default templates cannot be deleted."""
    template = _get_template_or_404(request, template_id)
    if template.is_default:
        messages.error(request, f'"{template.name}" is a default template and cannot be deleted. Duplicate it instead.')
        return redirect('campaigns:template_list')
    if request.method == 'POST':
        name = template.name
        template.is_active = False
        template.save()
        messages.success(request, f'Template "{name}" deleted.')
    else:
        messages.error(request, 'Invalid request method.')
    return redirect('campaigns:template_list')







@login_required
@require_workspace_permission('campaigns', 'read')
def template_preview(request, template_id):
    """Return rendered HTML for template preview in iframe."""
    template = _get_template_or_404(request, template_id)
    html = template.render_complete_html()
    return HttpResponse(html, content_type='text/html; charset=utf-8')


@login_required
@require_workspace_permission('campaigns', 'create')
def template_use(request, template_id):
    """Use a template to start a new campaign."""
    template = _get_template_or_404(request, template_id)
    template.increment_use()
    # Redirect to campaign create with template pre-filled
    return redirect(reverse('campaigns:campaign_create') + f'?template={template.id}')



@login_required
@require_workspace_permission('campaigns', 'create')
def template_duplicate(request, template_id):
    """Create a user-editable copy of a template (default or otherwise)."""
    original = _get_template_or_404(request, template_id)
    if request.method == 'POST':
        base_name = original.name.rstrip(' (Copy)').rstrip(' copy')
        copy_name = base_name + ' (Copy)'
        idx = 2
        while filter_by_context(request, EmailTemplate.objects.filter(name=copy_name)).exists():
            copy_name = f'{base_name} (Copy {idx})'
            idx += 1
        EmailTemplate.objects.create(
            user=request.user,
            workspace_id=request.session.get('active_workspace_id'),
            name=copy_name,
            subject=original.subject,
            body_html=original.body_html,
            body_text=original.body_text,
            header_text=original.header_text,
            footer_text=original.footer_text,
            is_default=False,
        )
        messages.success(request, f'Template duplicated as "{copy_name}".')
    return redirect('campaigns:template_list')

