import logging
import os

import stripe
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.workspaces.models import (
    WorkspaceMembership,
    WorkspaceStorageConfig,
    WorkspaceQuota,
    get_or_create_personal_workspace,
)
from apps.workspaces.decorators import require_workspace_permission

from .models import StoragePlan, WorkspaceBilling, Plan, Subscription
from .stripe_utils import (
    create_checkout_session,
    create_portal_session,
    handle_checkout_completed,
    handle_subscription_deleted,
    handle_invoice_paid,
    handle_invoice_payment_failed,
    get_stripe,
)

logger = logging.getLogger(__name__)


def _get_storage_used_mb(workspace):
    """Calculate storage usage for server-managed storage (local or IDA S3)."""
    config = WorkspaceStorageConfig.objects.filter(workspace=workspace).first()
    if not config:
        return 0

    if config.backend == WorkspaceStorageConfig.BACKEND_LOCAL:
        media_root = settings.MEDIA_ROOT
        total_bytes = 0
        try:
            for dirpath, dirnames, filenames in os.walk(media_root):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    try:
                        total_bytes += os.path.getsize(fp)
                    except (OSError, FileNotFoundError):
                        pass
        except Exception:
            logger.exception('Error calculating storage usage')
            return config.storage_used_mb if config else 0
        return round(total_bytes / (1024 * 1024), 2)

    if config.backend == WorkspaceStorageConfig.BACKEND_IDA_S3:
        return config.storage_used_mb or 0

    return 0


@login_required
@require_workspace_permission('billing', 'read')
def billing_dashboard(request):
    workspace = request.tenant or get_or_create_personal_workspace(request.user)
    membership = WorkspaceMembership.objects.filter(workspace=workspace, user=request.user).first()
    config = WorkspaceStorageConfig.objects.filter(workspace=workspace).first()

    storage_plan, _ = StoragePlan.objects.get_or_create(
        slug='server-storage',
        defaults={
            'name': 'Server Storage',
            'slug': 'server-storage',
            'price_per_gb_monthly': 10.00,
            'description': 'Files stored on IDA server disk.',
        },
    )

    billing, _ = WorkspaceBilling.objects.get_or_create(
        workspace=workspace,
        defaults={
            'storage_plan': storage_plan,
            'billing_email': request.user.email,
        },
    )

    storage_used_mb = _get_storage_used_mb(workspace)
    billing.storage_used_mb = storage_used_mb
    billing.calculate_monthly_cost()
    billing.save(update_fields=['storage_used_mb', 'monthly_cost_estimate', 'updated_at'])

    if config:
        config.storage_used_mb = storage_used_mb
        config.save(update_fields=['storage_used_mb', 'updated_at'])

    storage_gb = round(storage_used_mb / 1024, 2)
    monthly_cost = float(billing.monthly_cost_estimate)

    quota = workspace.quota()
    quota.reset_monthly_if_needed()
    plan_limits = workspace.get_plan_limits()
    subscription = getattr(workspace, 'subscription', None)
    plans = Plan.objects.filter(is_active=True).order_by('sort_order')

    quota_percentages = _compute_quota_percentages(quota, plan_limits)

    context = {
        'workspace': workspace,
        'membership': membership,
        'config': config,
        'billing': billing,
        'storage_plan': storage_plan,
        'storage_used_mb': storage_used_mb,
        'storage_gb': storage_gb,
        'monthly_cost': monthly_cost,
        'SERVER_STORAGE_PRICE': float(storage_plan.price_per_gb_monthly),
        'is_using_server_storage': config and config.backend in ('local', 'ida_s3'),
        'quota': quota,
        'quota_percentages': quota_percentages,
        'plan_limits': plan_limits,
        'subscription': subscription,
        'plans': plans,
        'STRIPE_PUBLISHABLE_KEY': settings.STRIPE_PUBLISHABLE_KEY,
        'plan_display': workspace.plan_display,
    }
    return render(request, 'billing/dashboard.html', context)


def _compute_quota_percentages(quota, limits):
    def pct(used, limit):
        if limit is None or limit == 0:
            return 0
        return min(round(used / limit * 100), 100)

    return {
        'emails': pct(quota.emails_sent_this_month, limits.get('emails_per_month', 0)),
        'ai_credits': pct(quota.ai_credits_used, limits.get('ai_credits', 0)),
        'storage': pct(
            quota.storage_bytes_used,
            (limits.get('storage_gb') or 0) * 1024 * 1024 * 1024,
        ),
    }


@login_required
@require_workspace_permission('billing', 'read')
def create_subscription_checkout(request, plan_id, interval='month'):
    workspace = request.tenant or get_or_create_personal_workspace(request.user)
    plan = Plan.objects.get(id=plan_id, is_active=True)
    price_id = plan.get_stripe_price_id(interval)
    if not price_id:
        from django.contrib import messages
        messages.error(request, 'This plan is not configured for online payment yet.')
        return redirect('billing:dashboard')

    success_url = request.build_absolute_uri('/billing/?checkout=success')
    cancel_url = request.build_absolute_uri('/billing/')
    session = create_checkout_session(workspace, price_id, success_url, cancel_url)
    return redirect(session.url)


@login_required
@require_workspace_permission('billing', 'read')
def billing_portal(request):
    workspace = request.tenant or get_or_create_personal_workspace(request.user)
    if not workspace.stripe_customer_id:
        return redirect('billing:dashboard')
    return_url = request.build_absolute_uri('/billing/')
    session = create_portal_session(workspace, return_url)
    return redirect(session.url)


@csrf_exempt
@require_POST
def stripe_webhook(request):
    stripe_obj = get_stripe()
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    if not endpoint_secret:
        logger.warning('STRIPE_WEBHOOK_SECRET not configured, skipping webhook verification')
        return HttpResponse(status=200)

    try:
        event = stripe_obj.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError:
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError:
        return HttpResponse(status=400)

    event_type = event.get('type')
    data = event['data']['object']

    handlers = {
        'checkout.session.completed': lambda: handle_checkout_completed(data),
        'customer.subscription.deleted': lambda: handle_subscription_deleted(data),
        'invoice.paid': lambda: handle_invoice_paid(data),
        'invoice.payment_failed': lambda: handle_invoice_payment_failed(data),
    }

    handler = handlers.get(event_type)
    if handler:
        try:
            handler()
        except Exception as e:
            logger.exception(f'Error handling stripe event {event_type}: {e}')

    return HttpResponse(status=200)

