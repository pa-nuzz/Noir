import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Workflow, WorkflowNode, WorkflowEdge, WorkflowEnrollment
from apps.workspaces.query_helpers import filter_by_context
from apps.workspaces.decorators import require_workspace_permission

logger = logging.getLogger(__name__)


@login_required
def workflow_list(request):
    workflows = filter_by_context(request, Workflow.objects.all()).annotate(
        enrollment_count=Count('enrollments', filter=Q(enrollments__status='active')),
    )
    return render(request, 'automations/workflow_list.html', {
        'workflows': workflows,
    })


@login_required
@require_workspace_permission('workflows', 'create')
def workflow_create(request):
    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        if not name:
            messages.error(request, 'Workflow name is required.')
            return render(request, 'automations/workflow_form.html')
        workflow = Workflow.objects.create(user=request.user, name=name)
        messages.success(request, f'Workflow "{name}" created.')
        return redirect('automations:workflow_edit', workflow_id=workflow.id)

    return render(request, 'automations/workflow_form.html')


@login_required
@require_workspace_permission('workflows', 'edit')
def workflow_edit(request, workflow_id):
    workflow = get_object_or_404(filter_by_context(request, Workflow.objects.all()), id=workflow_id)
    nodes = list(workflow.nodes.all().order_by('created_at'))
    edges = list(workflow.edges.all())

    # Available email templates for action nodes
    from apps.campaigns.models import EmailTemplate
    from apps.contacts.models import ContactList

    templates = filter_by_context(request, EmailTemplate.objects.all()).filter(is_active=True)
    contact_lists = filter_by_context(request, ContactList.objects.all())

    templates_json = json.dumps([
        {'id': t.id, 'name': t.name, 'subject': t.subject}
        for t in templates
    ])

    return render(request, 'automations/workflow_form.html', {
        'workflow': workflow,
        'nodes_json': json.dumps([
            {'node_id': n.node_id, 'type': n.type, 'config': n.config}
            for n in nodes
        ]),
        'edges_json': json.dumps([
            {'from_node_id': e.from_node_id, 'to_node_id': e.to_node_id, 'condition': e.condition}
            for e in edges
        ]),
        'templates': templates,
        'templates_json': templates_json,
        'contact_lists': contact_lists,
    })


@login_required
@require_workspace_permission('workflows', 'delete')
@require_POST
def workflow_delete(request, workflow_id):
    workflow = get_object_or_404(filter_by_context(request, Workflow.objects.all()), id=workflow_id)
    workflow.delete()
    messages.success(request, 'Workflow deleted.')
    return redirect('automations:workflow_list')


@login_required
@require_workspace_permission('workflows', 'edit')
@require_POST
def workflow_toggle(request, workflow_id):
    workflow = get_object_or_404(filter_by_context(request, Workflow.objects.all()), id=workflow_id)
    workflow.is_active = not workflow.is_active
    workflow.save(update_fields=['is_active', 'updated_at'])
    status = 'activated' if workflow.is_active else 'deactivated'
    messages.success(request, f'Workflow "{workflow.name}" {status}.')
    return redirect('automations:workflow_list')


@login_required
def workflow_analytics(request, workflow_id):
    workflow = get_object_or_404(filter_by_context(request, Workflow.objects.all()), id=workflow_id)
    enrollments = workflow.enrollments.all()
    total_count = enrollments.count()
    active_count = enrollments.filter(status='active').count()
    completed_count = enrollments.filter(status='completed').count()
    paused_count = enrollments.filter(status='paused').count()

    pending_count = total_count - active_count - completed_count - paused_count
    completion_rate = round((completed_count / total_count) * 100, 1) if total_count else 0

    nodes = workflow.nodes.all().order_by('created_at')
    node_stats = []
    for node in nodes:
        reached = enrollments.filter(
            current_node_id=node.node_id
        ).count()
        node_stats.append({
            'node_id': node.node_id,
            'type': node.type,
            'reached': reached,
        })

    return render(request, 'automations/workflow_analytics.html', {
        'workflow': workflow,
        'active_count': active_count,
        'completed_count': completed_count,
        'paused_count': paused_count,
        'pending_count': pending_count,
        'total_count': total_count,
        'completion_rate': completion_rate,
        'node_stats': node_stats,
    })


@login_required
@require_POST
def workflow_api_save_nodes(request):
    """Save the workflow node/edge graph from the flow builder."""
    try:
        data = json.loads(request.body)
        workflow_id = int(data.get('workflow_id', 0))
        nodes = data.get('nodes', [])
        edges = data.get('edges', [])

        workflow = get_object_or_404(filter_by_context(request, Workflow.objects.all()), id=workflow_id)

        active_count = workflow.enrollments.filter(status='active').count()
        if active_count > 0:
            return JsonResponse({
                'success': False,
                'error': f'Cannot modify flow — {active_count} contact(s) are actively enrolled. Pause the workflow first.',
            }, status=409)

        # Clear existing nodes and edges
        workflow.nodes.all().delete()
        workflow.edges.all().delete()

        # Recreate nodes
        for n in nodes:
            WorkflowNode.objects.create(
                workflow=workflow,
                node_id=n.get('node_id'),
                type=n.get('type', 'action'),
                config=n.get('config', {}),
            )

        # Recreate edges
        for e in edges:
            WorkflowEdge.objects.create(
                workflow=workflow,
                from_node_id=e.get('from_node_id'),
                to_node_id=e.get('to_node_id'),
                condition=e.get('condition', 'default'),
            )

        return JsonResponse({'success': True})

    except Exception as exc:
        logger.error(f"Error saving workflow nodes: {exc}")
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
