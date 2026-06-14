import json

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from .models import WebhookEndpoint, WebhookDelivery, WEBHOOK_EVENTS


@login_required
def webhook_list(request):
    tenant = getattr(request, 'tenant', None)
    if tenant is None:
        return redirect('dashboard:main')
    endpoints = WebhookEndpoint.objects.filter(workspace=tenant).order_by('-created_at')
    return render(request, 'webhooks/list.html', {
        'endpoints': endpoints,
        'events': WEBHOOK_EVENTS,
    })


@login_required
def webhook_create(request):
    tenant = getattr(request, 'tenant', None)
    if tenant is None:
        return redirect('dashboard:main')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        url = request.POST.get('url', '').strip()
        events = request.POST.getlist('events')

        if not name or not url:
            messages.error(request, 'Name and URL are required.')
            return render(request, 'webhooks/form.html', {'events': WEBHOOK_EVENTS})

        endpoint = WebhookEndpoint.objects.create(
            workspace=tenant,
            name=name,
            url=url,
            events=events,
        )
        messages.success(request, f'Webhook "{endpoint.name}" created.')
        return redirect('webhooks:list')

    return render(request, 'webhooks/form.html', {'events': WEBHOOK_EVENTS})


@login_required
def webhook_toggle(request, pk):
    tenant = getattr(request, 'tenant', None)
    endpoint = get_object_or_404(WebhookEndpoint, id=pk, workspace=tenant)
    endpoint.is_active = not endpoint.is_active
    endpoint.save(update_fields=['is_active'])
    status = 'activated' if endpoint.is_active else 'deactivated'
    messages.success(request, f'Webhook "{endpoint.name}" {status}.')
    return redirect('webhooks:list')


@login_required
def webhook_test(request, pk):
    tenant = getattr(request, 'tenant', None)
    endpoint = get_object_or_404(WebhookEndpoint, id=pk, workspace=tenant)

    test_payload = {
        'event': 'test.ping',
        'workspace_id': tenant.id,
        'data': {'message': 'This is a test webhook from Intelligent Digital Automation.'},
    }

    try:
        import requests
        headers = {'Content-Type': 'application/json', 'User-Agent': 'MailFlow-Webhook/1.0'}
        if endpoint.secret:
            headers['X-Webhook-Signature'] = endpoint.sign_payload(test_payload)
        resp = requests.post(endpoint.url, json=test_payload, headers=headers, timeout=15)
        messages.success(request, f'Test sent. Response: {resp.status_code}')
    except Exception as e:
        messages.error(request, f'Test failed: {e}')

    return redirect('webhooks:list')
