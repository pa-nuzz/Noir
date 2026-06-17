import csv
import io
import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .models import Contact, ContactCustomField, ContactCustomFieldValue, ContactList, ContactSegment, ContactTag
from apps.workspaces.query_helpers import filter_by_context
from apps.workspaces.decorators import require_workspace_permission
from core.tenant import get_current_tenant

logger = logging.getLogger(__name__)


def _get_active_workspace(request):
    tenant = get_current_tenant()
    if tenant is not None:
        return tenant
    ws_id = request.session.get('active_workspace_id')
    if ws_id:
        from apps.workspaces.models import Workspace
        try:
            return Workspace.objects.get(id=ws_id)
        except Workspace.DoesNotExist:
            return None
    return None


def _get_or_create_tag(request, tag_name):
    ws = _get_active_workspace(request)
    if ws:
        tag_obj, _ = ContactTag.objects.get_or_create(
            workspace=ws, name=tag_name,
            defaults={'user': request.user},
        )
    else:
        tag_obj, _ = ContactTag.objects.get_or_create(
            user=request.user, name=tag_name,
        )
    return tag_obj


@login_required
def contacts_home(request):
    contact_lists = filter_by_context(request, ContactList.objects.all()).annotate(contact_count=Count('contacts'))
    available_tags = filter_by_context(request, ContactTag.objects.all()).annotate(contact_count=Count('contacts'))

    contacts_qs = Contact.objects.filter(
        contact_list__in=filter_by_context(request, ContactList.objects.all())
    ).select_related('contact_list').prefetch_related('tags').order_by('-created_at')

    selected_list_id = request.GET.get('list_id', '').strip()
    selected_list = None
    if selected_list_id and selected_list_id.isdigit():
        selected_list = get_object_or_404(filter_by_context(request, ContactList.objects.all()), id=selected_list_id)
        contacts_qs = contacts_qs.filter(contact_list=selected_list)

    selected_tag_id = request.GET.get('tag_id', '').strip()
    selected_tag = None
    if selected_tag_id and selected_tag_id.isdigit():
        selected_tag = get_object_or_404(filter_by_context(request, ContactTag.objects.all()), id=selected_tag_id)
        contacts_qs = contacts_qs.filter(tags=selected_tag)

    search = request.GET.get('q', '').strip()
    if search:
        contacts_qs = contacts_qs.filter(
            Q(email__icontains=search) | Q(first_name__icontains=search) | Q(last_name__icontains=search)
        )

    total = contacts_qs.count()
    paginator = Paginator(contacts_qs, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    gdpr_consent_count = Contact.objects.filter(
        contact_list__in=filter_by_context(request, ContactList.objects.all()),
        gdpr_consent=True,
    ).count()

    return render(request, 'contacts/contacts_home.html', {
        'contact_lists': contact_lists,
        'available_tags': available_tags,
        'all_contacts': page_obj.object_list,
        'page_obj': page_obj,
        'total': total,
        'search': search,
        'selected_list': selected_list,
        'selected_tag': selected_tag,
        'gdpr_consent_count': gdpr_consent_count,
    })


@login_required
def tags_manager(request):
    next_url = (request.POST.get('next') or request.GET.get('next') or '').strip()
    if not next_url:
        next_url = reverse('contacts:tags_manager')

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()

        if action == 'create':
            name = (request.POST.get('name') or '').strip()
            if not name:
                messages.error(request, 'Tag name is required.')
                return redirect(next_url)
            ws = _get_active_workspace(request)
            if ws:
                tag_obj, created = ContactTag.objects.get_or_create(
                    workspace=ws, name=name,
                    defaults={'user': request.user},
                )
            else:
                tag_obj, created = ContactTag.objects.get_or_create(
                    user=request.user, name=name,
                )
            messages.success(request, f'Tag "{tag_obj.name}" {"created" if created else "already exists"}.' if created else f'Tag "{tag_obj.name}" already exists.')
            return redirect(next_url)

        if action == 'rename':
            tag_id = request.POST.get('tag_id')
            new_name = (request.POST.get('new_name') or '').strip()
            if not tag_id or not new_name:
                messages.error(request, 'Tag and new name are required.')
                return redirect(next_url)
            tag_obj = get_object_or_404(filter_by_context(request, ContactTag.objects.all()), id=tag_id)
            ws = _get_active_workspace(request)
            dup_filter = ContactTag.objects.filter(name=new_name).exclude(id=tag_obj.id)
            if ws:
                dup_filter = dup_filter.filter(workspace=ws)
            else:
                dup_filter = dup_filter.filter(user=request.user)
            if dup_filter.exists():
                messages.error(request, f'Tag "{new_name}" already exists.')
                return redirect(next_url)
            old_name = tag_obj.name
            tag_obj.name = new_name
            tag_obj.save(update_fields=['name'])
            messages.success(request, f'Tag "{old_name}" renamed to "{new_name}".')
            return redirect(next_url)

        if action == 'delete':
            tag_id = request.POST.get('tag_id')
            if not tag_id:
                messages.error(request, 'Tag is required.')
                return redirect(next_url)
            tag_obj = get_object_or_404(filter_by_context(request, ContactTag.objects.all()), id=tag_id)
            name = tag_obj.name
            tag_obj.delete()
            messages.success(request, f'Tag "{name}" deleted.')
            return redirect(next_url)

        messages.error(request, 'Invalid action.')
        return redirect(next_url)

    tags = filter_by_context(request, ContactTag.objects.all()).annotate(contact_count=Count('contacts')).order_by('name')
    return render(request, 'contacts/tags_manager.html', {'tags': tags})


@login_required
def bulk_update_contact_tags(request):
    if request.method != 'POST':
        return redirect('contacts:list')

    operation = (request.POST.get('operation') or '').strip()
    raw_ids = (request.POST.get('selected_contact_ids') or '').strip()
    tag_ids = request.POST.getlist('tag_ids')

    if not raw_ids:
        messages.error(request, 'Select at least one contact.')
        return redirect('contacts:list')

    selected_ids = []
    for token in raw_ids.split(','):
        token = token.strip()
        if token and token.isdigit():
            selected_ids.append(int(token))

    if not selected_ids:
        messages.error(request, 'Select at least one valid contact.')
        return redirect('contacts:list')

    contacts = Contact.objects.filter(id__in=selected_ids, contact_list__in=filter_by_context(request, ContactList.objects.all())).distinct()
    selected_count = contacts.count()
    if selected_count == 0:
        messages.error(request, 'No valid contacts found.')
        return redirect('contacts:list')

    selected_tags = filter_by_context(request, ContactTag.objects.all()).filter(id__in=tag_ids)
    selected_tag_count = selected_tags.count()

    if operation in ('add', 'replace', 'remove') and selected_tag_count == 0:
        messages.error(request, 'Select at least one tag for this action.')
        return redirect('contacts:list')

    if operation == 'add':
        for contact in contacts:
            contact.tags.add(*selected_tags)
        messages.success(request, f'Added {selected_tag_count} tag(s) to {selected_count} contact(s).')
    elif operation == 'replace':
        for contact in contacts:
            contact.tags.set(selected_tags)
        messages.success(request, f'Replaced tags for {selected_count} contact(s).')
    elif operation == 'remove':
        for contact in contacts:
            contact.tags.remove(*selected_tags)
        messages.success(request, f'Removed selected tag(s) from {selected_count} contact(s).')
    elif operation == 'clear':
        for contact in contacts:
            contact.tags.clear()
        messages.success(request, f'Cleared all tags from {selected_count} contact(s).')
    else:
        messages.error(request, 'Invalid tag action selected.')

    return redirect('contacts:list')


@login_required
@require_workspace_permission('contacts', 'create')
def import_csv(request):
    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')
        list_id = request.POST.get('list_id', '').strip()
        list_name = request.POST.get('list_name', '').strip()
        next_url = request.POST.get('next', '').strip()
        default_gdpr_consent = request.POST.get('default_gdpr_consent') == 'on'

        if not csv_file:
            messages.error(request, 'Please provide a CSV file.')
            return redirect(next_url or 'contacts:list')

        if not csv_file.name.endswith('.csv'):
            messages.error(request, 'File must be a .csv')
            return redirect(next_url or 'contacts:list')

        try:
            decoded = csv_file.read().decode('utf-8')
            reader = csv.DictReader(io.StringIO(decoded))
            headers = [h.strip().lower() for h in (reader.fieldnames or [])]

            if 'email' not in headers:
                messages.error(request, 'CSV must have an "email" column.')
                return redirect(next_url or 'contacts:list')

            ws = _get_active_workspace(request)

            if list_id:
                contact_list_obj = get_object_or_404(
                    filter_by_context(request, ContactList.objects.all()),
                    id=list_id,
                )
            elif list_name:
                contact_list_obj = ContactList.objects.create(
                    user=request.user,
                    workspace=ws,
                    name=list_name,
                    description=f'Imported from {csv_file.name}',
                )
            else:
                base_qs = filter_by_context(request, ContactList.objects.all()).filter(name='Default List')
                contact_list_obj = base_qs.first()
                if not contact_list_obj:
                    contact_list_obj = ContactList.objects.create(
                        name='Default List',
                        description='Auto-created default list',
                        user=request.user,
                        workspace=ws,
                    )

            has_consent_col = 'gdpr_consent' in headers
            created = 0
            skipped = 0
            for row in reader:
                row = {k.strip().lower(): v.strip() for k, v in row.items()}
                email = row.get('email', '').strip().lower()
                if not email or '@' not in email:
                    skipped += 1
                    continue
                contact_obj, was_created = Contact.objects.get_or_create(
                    contact_list=contact_list_obj,
                    email=email,
                    defaults={
                        'first_name': row.get('first_name', ''),
                        'last_name': row.get('last_name', ''),
                    }
                )

                if not was_created:
                    if row.get('first_name'):
                        contact_obj.first_name = row['first_name']
                    if row.get('last_name'):
                        contact_obj.last_name = row['last_name']
                    contact_obj.save()

                consent_granted = False
                if has_consent_col:
                    consent_val = row.get('gdpr_consent', '').strip().lower()
                    consent_granted = consent_val in ('yes', 'true', '1', 'y', 't', '✓', 'checked', 'on')
                elif default_gdpr_consent:
                    consent_granted = True

                if consent_granted:
                    contact_obj.gdpr_consent = True
                    contact_obj.gdpr_consent_at = timezone.now()
                    contact_obj.gdpr_notes = (contact_obj.gdpr_notes or '') + '\n[Imported via CSV with consent]'
                    contact_obj.save(update_fields=['gdpr_consent', 'gdpr_consent_at', 'gdpr_notes', 'updated_at'])

                tag_values = Contact.parse_tags(row.get('tags', ''))
                if tag_values:
                    tag_objects = []
                    for tag_name in tag_values:
                        tag_obj = _get_or_create_tag(request, tag_name)
                        tag_objects.append(tag_obj)
                    contact_obj.tags.add(*tag_objects)

                if was_created:
                    created += 1
                else:
                    skipped += 1

            list_label = contact_list_obj.name
            messages.success(request, f'List "{list_label}" updated with {created} new contacts ({skipped} skipped).')
            return redirect(next_url or 'contacts:list')

        except Exception as e:
            logger.exception('CSV import failed')
            messages.error(request, f'Failed to import CSV: {e}')
            return redirect(next_url or 'contacts:list')

    return render(request, 'contacts/import_csv.html')


@login_required
@require_workspace_permission('contacts', 'create')
def add_contact(request):
    if request.method != 'POST':
        return redirect('contacts:list')

    email = request.POST.get('email', '').strip().lower()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    list_id = request.POST.get('list_id', '').strip()
    tags_raw = request.POST.get('tags', '').strip()
    gdpr_consent = request.POST.get('gdpr_consent') == 'on'

    if not email or '@' not in email:
        messages.error(request, 'Please enter a valid email address.')
        return redirect('contacts:list')

    if list_id:
        contact_list = get_object_or_404(filter_by_context(request, ContactList.objects.all()), id=list_id)
    else:
        ws = _get_active_workspace(request)
        base_qs = filter_by_context(request, ContactList.objects.all()).filter(name='Default List')
        contact_list = base_qs.first()
        if not contact_list:
            contact_list = ContactList.objects.create(
                name='Default List',
                description='Auto-created default list',
                user=request.user,
                workspace=ws,
            )

    contact_obj, created = Contact.objects.get_or_create(
        contact_list=contact_list,
        email=email,
        defaults={
            'first_name': first_name,
            'last_name': last_name,
            'gdpr_consent': gdpr_consent,
            'gdpr_consent_at': timezone.now() if gdpr_consent else None,
        }
    )

    if not created:
        if gdpr_consent and not contact_obj.gdpr_consent:
            contact_obj.gdpr_consent = True
            contact_obj.gdpr_consent_at = timezone.now()
            contact_obj.save(update_fields=['gdpr_consent', 'gdpr_consent_at', 'updated_at'])

    tag_values = Contact.parse_tags(tags_raw)
    if tag_values:
        tag_objects = []
        for tag_name in tag_values:
            tag_obj = _get_or_create_tag(request, tag_name)
            tag_objects.append(tag_obj)
        contact_obj.tags.add(*tag_objects)

    if created:
        messages.success(request, f'{email} added to "{contact_list.name}".')
    else:
        messages.warning(request, f'{email} already exists in "{contact_list.name}".')

    return redirect('contacts:list')


@login_required
@require_workspace_permission('contacts', 'delete')
def bulk_delete_contacts(request):
    if request.method != 'POST':
        return redirect('contacts:list')

    raw_ids = (request.POST.get('contact_ids') or '').strip()
    if not raw_ids:
        messages.error(request, 'Select at least one contact.')
        return redirect('contacts:list')

    selected_ids = []
    for token in raw_ids.split(','):
        token = token.strip()
        if token and token.isdigit():
            selected_ids.append(int(token))

    if not selected_ids:
        messages.error(request, 'Select at least one valid contact.')
        return redirect('contacts:list')

    contacts = Contact.objects.filter(
        id__in=selected_ids,
        contact_list__in=filter_by_context(request, ContactList.objects.all())
    ).distinct()

    deleted_count = contacts.count()
    contacts.delete()
    messages.success(request, f'Deleted {deleted_count} contact(s).')
    return redirect('contacts:list')


@login_required
@require_workspace_permission('contacts', 'delete')
def delete_contact(request, contact_id):
    contact = get_object_or_404(Contact.objects.filter(contact_list__in=filter_by_context(request, ContactList.objects.all())), id=contact_id)
    if request.method == 'POST':
        contact.delete()
        messages.success(request, f'{contact.email} deleted.')
    return redirect('contacts:list')


@login_required
@require_workspace_permission('contacts', 'delete')
def delete_list(request, list_id):
    contact_list = get_object_or_404(filter_by_context(request, ContactList.objects.all()), id=list_id)
    if request.method == 'POST':
        name = contact_list.name
        contact_list.delete()
        messages.success(request, f'List "{name}" and all its contacts deleted.')
    return redirect('contacts:list')


@login_required
@require_workspace_permission('contacts', 'create')
def create_list(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()

        if not name:
            messages.error(request, 'List name is required.')
            return render(request, 'contacts/create_list.html')

        if filter_by_context(request, ContactList.objects.all()).filter(name=name).exists():
            messages.error(request, f'A list named "{name}" already exists.')
            return render(request, 'contacts/create_list.html')

        contact_list = ContactList.objects.create(
            user=request.user,
            workspace=_get_active_workspace(request),
            name=name,
            description=description,
        )
        messages.success(request, f'List "{name}" created successfully. Add contacts now!')
        return redirect(f"{reverse('contacts:list')}?open_add_contact=1")

    return render(request, 'contacts/create_list.html')


# --- Custom Fields ---

@login_required
def custom_fields_list(request):
    fields = filter_by_context(request, ContactCustomField.objects.all())
    return render(request, 'contacts/custom_fields.html', {'fields': fields})


@login_required
@require_workspace_permission('contacts', 'edit')
def custom_field_create(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        field_type = request.POST.get('field_type', 'text')
        options_raw = request.POST.get('options', '').strip()
        is_required = request.POST.get('is_required') == 'on'

        if not name:
            messages.error(request, 'Field name is required.')
            return redirect('contacts:custom_fields')

        if filter_by_context(request, ContactCustomField.objects.all()).filter(name=name).exists():
            messages.error(request, f'A field named "{name}" already exists.')
            return redirect('contacts:custom_fields')

        options = [o.strip() for o in options_raw.split(',') if o.strip()] if options_raw else []

        ContactCustomField.objects.create(
            user=request.user,
            workspace=_get_active_workspace(request),
            name=name,
            field_type=field_type,
            options=options,
            is_required=is_required,
        )
        messages.success(request, f'Custom field "{name}" created.')
        return redirect('contacts:custom_fields')

    return redirect('contacts:custom_fields')


@login_required
@require_workspace_permission('contacts', 'delete')
def custom_field_delete(request, pk):
    field = get_object_or_404(filter_by_context(request, ContactCustomField.objects.all()), pk=pk)
    field.delete()
    messages.success(request, f'Custom field "{field.name}" deleted.')
    return redirect('contacts:custom_fields')


# --- Segments ---

@login_required
def segment_list(request):
    segments_qs = filter_by_context(request, ContactSegment.objects.all())

    filter_type = request.GET.get('filter', 'all')
    if filter_type == 'dynamic':
        segments_qs = segments_qs.filter(match_type='any')
    elif filter_type == 'static':
        segments_qs = segments_qs.filter(match_type='all')

    segment_type = request.GET.get('filter', 'all')

    total_contacts = Contact.objects.filter(contact_list__in=filter_by_context(request, ContactList.objects.all())).count()

    segments = []
    total_matched = 0
    for seg in segments_qs:
        seg.matched_count = seg.get_matched_contacts().count()
        total_matched += seg.matched_count
        segments.append(seg)

    total_segments = filter_by_context(request, ContactSegment.objects.all()).count()
    dynamic_count = filter_by_context(request, ContactSegment.objects.filter(match_type='any')).count()
    static_count = total_segments - dynamic_count
    avg_size = round(total_matched / total_segments) if total_segments > 0 else 0

    custom_fields = filter_by_context(request, ContactCustomField.objects.all())

    return render(request, 'contacts/segment_list.html', {
        'segments': segments,
        'total_segments': total_segments,
        'dynamic_count': dynamic_count,
        'static_count': static_count,
        'avg_size': avg_size,
        'segment_type': segment_type,
        'custom_fields': custom_fields,
    })


@login_required
def segment_count_preview(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        rules = data.get('rules', [])
        match_type = data.get('match_type', 'all')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    from django.db.models import Q
    qs = Contact.objects.filter(contact_list__in=filter_by_context(request, ContactList.objects.all()))
    queries = []

    for rule in rules:
        field = rule.get('field', '')
        operator = rule.get('operator', '')
        value = rule.get('value', '')

        if field == 'email':
            if operator == 'contains':
                queries.append(Q(email__icontains=value))
            elif operator == 'equals':
                queries.append(Q(email__iexact=value))
            elif operator == 'starts_with':
                queries.append(Q(email__istartswith=value))
            elif operator == 'ends_with':
                queries.append(Q(email__iendswith=value))
        elif field == 'first_name':
            if operator == 'contains':
                queries.append(Q(first_name__icontains=value))
            elif operator == 'equals':
                queries.append(Q(first_name__iexact=value))
        elif field == 'last_name':
            if operator == 'contains':
                queries.append(Q(last_name__icontains=value))
            elif operator == 'equals':
                queries.append(Q(last_name__iexact=value))
        elif field == 'is_active':
            queries.append(Q(is_active=(value.lower() == 'true')))
        elif field == 'unsubscribed':
            queries.append(Q(unsubscribed=(value.lower() == 'true')))
        elif field == 'bounce_count':
            try:
                val = int(value)
                if operator == 'gt':
                    queries.append(Q(bounce_count__gt=val))
                elif operator == 'gte':
                    queries.append(Q(bounce_count__gte=val))
                elif operator == 'lt':
                    queries.append(Q(bounce_count__lt=val))
                elif operator == 'lte':
                    queries.append(Q(bounce_count__lte=val))
                elif operator == 'equals':
                    queries.append(Q(bounce_count=val))
            except (ValueError, TypeError):
                pass
        elif field == 'created_at':
            if operator == 'before':
                queries.append(Q(created_at__date__lt=value))
            elif operator == 'after':
                queries.append(Q(created_at__date__gt=value))
        elif field == 'tag':
            if operator == 'has':
                queries.append(Q(tags__name__iexact=value))
            elif operator == 'not_has':
                queries.append(~Q(tags__name__iexact=value))
        elif field == 'contact_list':
            if operator == 'is':
                queries.append(Q(contact_list__name__iexact=value))
            elif operator == 'is_not':
                queries.append(~Q(contact_list__name__iexact=value))

    if queries:
        if match_type == 'all':
            combined = queries[0]
            for q in queries[1:]:
                combined &= q
        else:
            combined = queries[0]
            for q in queries[1:]:
                combined |= q
        count = qs.filter(combined).distinct().count()
    else:
        count = 0

    return JsonResponse({'count': count})


@login_required
@require_workspace_permission('contacts', 'create')
def segment_create(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        match_type = request.POST.get('match_type', 'all')
        rules_raw = request.POST.get('rules', '[]')

        if not name:
            messages.error(request, 'Segment name is required.')
            return redirect('contacts:segment_list')

        try:
            rules = json.loads(rules_raw)
        except json.JSONDecodeError:
            rules = []

        ContactSegment.objects.create(
            user=request.user,
            workspace=_get_active_workspace(request),
            name=name,
            description=description,
            match_type=match_type,
            rules=rules,
        )
        messages.success(request, f'Segment "{name}" created.')
        return redirect('contacts:segment_list')

    custom_fields = filter_by_context(request, ContactCustomField.objects.all())
    return render(request, 'contacts/segment_form.html', {
        'custom_fields': custom_fields,
    })


@login_required
def segment_detail(request, pk):
    segment = get_object_or_404(filter_by_context(request, ContactSegment.objects.all()), pk=pk)
    contacts = segment.get_matched_contacts().select_related('contact_list')
    return render(request, 'contacts/segment_detail.html', {
        'segment': segment,
        'contacts': contacts,
    })


@login_required
@require_workspace_permission('contacts', 'delete')
def segment_delete(request, pk):
    segment = get_object_or_404(filter_by_context(request, ContactSegment.objects.all()), pk=pk)
    segment.delete()
    messages.success(request, f'Segment "{segment.name}" deleted.')
    return redirect('contacts:segment_list')


# --- Export ---

@login_required
def export_csv(request):
    list_id = request.GET.get('list_id', '')
    contacts_qs = Contact.objects.filter(contact_list__in=filter_by_context(request, ContactList.objects.all())).select_related('contact_list')

    if list_id and list_id.isdigit():
        contacts_qs = contacts_qs.filter(contact_list_id=list_id)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="contacts_export.csv"'

    writer = csv.writer(response)
    writer.writerow(['Email', 'First Name', 'Last Name', 'List', 'Tags', 'Active', 'Unsubscribed', 'Bounce Count', 'Created At'])

    for c in contacts_qs:
        writer.writerow([
            c.email,
            c.first_name,
            c.last_name,
            c.contact_list.name,
            ', '.join(t.name for t in c.tags.all()),
            'Yes' if c.is_active else 'No',
            'Yes' if c.unsubscribed else 'No',
            c.bounce_count,
            c.created_at.strftime('%Y-%m-%d'),
        ])

    return response


# --- Unsubscribe Management ---

@login_required
def unsubscribe_list(request):
    unsubscribed = Contact.objects.filter(
        contact_list__in=filter_by_context(request, ContactList.objects.all()),
        unsubscribed=True,
    ).select_related('contact_list').order_by('-unsubscribed_at')

    return render(request, 'contacts/unsubscribes.html', {
        'unsubscribed': unsubscribed,
    })


# --- GDPR ---

@login_required
def gdpr_tools(request):
    from django.db.models import Sum

    total_contacts = Contact.objects.filter(contact_list__in=filter_by_context(request, ContactList.objects.all())).count()
    consent_given = Contact.objects.filter(contact_list__in=filter_by_context(request, ContactList.objects.all()), gdpr_consent=True).count()
    consent_missing = total_contacts - consent_given

    return render(request, 'contacts/gdpr.html', {
        'total_contacts': total_contacts,
        'consent_given': consent_given,
        'consent_missing': consent_missing,
    })


@login_required
def gdpr_export_data(request):
    contacts = Contact.objects.filter(contact_list__in=filter_by_context(request, ContactList.objects.all())).select_related('contact_list')

    data = []
    for c in contacts:
        data.append({
            'email': c.email,
            'first_name': c.first_name,
            'last_name': c.last_name,
            'list': c.contact_list.name,
            'is_active': c.is_active,
            'unsubscribed': c.unsubscribed,
            'bounce_count': c.bounce_count,
            'gdpr_consent': c.gdpr_consent,
            'gdpr_consent_at': c.gdpr_consent_at.isoformat() if c.gdpr_consent_at else None,
            'tags': list(c.tags.values_list('name', flat=True)),
            'created_at': c.created_at.isoformat(),
        })

    response = HttpResponse(
        json.dumps(data, indent=2, default=str),
        content_type='application/json',
    )
    response['Content-Disposition'] = 'attachment; filename="gdpr_data_export.json"'
    return response


@login_required
@require_workspace_permission('contacts', 'edit')
def gdpr_anonymize_contact(request, contact_id):
    contact = get_object_or_404(Contact.objects.filter(contact_list__in=filter_by_context(request, ContactList.objects.all())), id=contact_id)
    if request.method == 'POST':
        contact.first_name = '[GDPR Anonymized]'
        contact.last_name = ''
        contact.email = f'redacted-{contact.id}@anonymized.local'
        contact.is_active = False
        contact.gdpr_consent = False
        contact.gdpr_data_exported_at = timezone.now()
        contact.notes = (contact.notes or '') + '\n[GDPR Anonymized on ' + timezone.now().strftime('%Y-%m-%d %H:%M') + ']'
        contact.save()
        contact.tags.clear()
        contact.custom_field_values.all().delete()
        messages.success(request, f'Contact {contact.id} has been anonymized per GDPR request.')
        return redirect('contacts:list')

    return render(request, 'contacts/gdpr_confirm.html', {'contact': contact})


# --- Contact Detail & Edit ---

@login_required
def contact_detail(request, contact_id):
    contact = get_object_or_404(Contact.objects.filter(contact_list__in=filter_by_context(request, ContactList.objects.all())), id=contact_id)
    custom_fields = filter_by_context(request, ContactCustomField.objects.all())
    field_values = {v.field_id: v.value for v in contact.custom_field_values.all()}
    return render(request, 'contacts/contact_detail.html', {
        'contact': contact,
        'custom_fields': custom_fields,
        'field_values': field_values,
    })


@login_required
def contact_edit(request, contact_id):
    contact = get_object_or_404(Contact.objects.filter(contact_list__in=filter_by_context(request, ContactList.objects.all())), id=contact_id)
    if request.method == 'POST':
        contact.first_name = request.POST.get('first_name', '').strip()
        contact.last_name = request.POST.get('last_name', '').strip()
        contact.notes = request.POST.get('notes', '').strip()
        contact.is_active = request.POST.get('is_active') == 'on'
        contact.gdpr_consent = request.POST.get('gdpr_consent') == 'on'
        contact.save()

        # Update custom field values
        custom_fields = filter_by_context(request, ContactCustomField.objects.all())
        for field in custom_fields:
            value = request.POST.get(f'cf_{field.id}', '').strip()
            ContactCustomFieldValue.objects.update_or_create(
                contact=contact,
                field=field,
                defaults={'value': value},
            )

        messages.success(request, 'Contact updated.')
        return redirect('contacts:contact_detail', contact_id=contact.id)

    custom_fields = filter_by_context(request, ContactCustomField.objects.all())
    field_values = {v.field_id: v.value for v in contact.custom_field_values.all()}
    return render(request, 'contacts/contact_form.html', {
        'contact': contact,
        'custom_fields': custom_fields,
        'field_values': field_values,
    })
