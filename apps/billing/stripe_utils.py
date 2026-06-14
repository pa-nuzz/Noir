import stripe
from django.conf import settings
from django.db import models
from django.shortcuts import get_object_or_404

from apps.workspaces.models import Workspace, WorkspaceQuota


def get_stripe():
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def create_stripe_customer(workspace, email):
    stripe = get_stripe()
    customer = stripe.Customer.create(
        email=email,
        metadata={'workspace_id': workspace.id, 'workspace_name': workspace.name},
    )
    workspace.stripe_customer_id = customer.id
    workspace.save(update_fields=['stripe_customer_id'])
    return customer


def get_or_create_customer(workspace, email=None):
    if workspace.stripe_customer_id:
        return workspace.stripe_customer_id
    customer = create_stripe_customer(workspace, email or '')
    return customer.id


def create_checkout_session(workspace, price_id, success_url, cancel_url):
    stripe = get_stripe()
    customer_id = get_or_create_customer(workspace)
    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode='subscription',
        line_items=[{'price': price_id, 'quantity': 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={'workspace_id': workspace.id},
    )
    return session


def create_portal_session(workspace, return_url):
    stripe = get_stripe()
    customer_id = get_or_create_customer(workspace)
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return session


def handle_checkout_completed(session):
    workspace_id = session.get('metadata', {}).get('workspace_id')
    if not workspace_id:
        return
    workspace = get_object_or_404(Workspace, id=workspace_id)
    customer_id = session.get('customer')
    if customer_id:
        workspace.stripe_customer_id = customer_id
        workspace.save(update_fields=['stripe_customer_id'])
    subscription_id = session.get('subscription')
    if subscription_id:
        from .models import Subscription, Plan
        stripe = get_stripe()
        sub_data = stripe.Subscription.retrieve(subscription_id)
        price_id = sub_data['items']['data'][0]['price']['id']
        plan = Plan.objects.filter(
            models.Q(stripe_price_id_monthly=price_id) | models.Q(stripe_price_id_yearly=price_id)
        ).first()
        if plan:
            interval = 'year' if price_id == plan.stripe_price_id_yearly else 'month'
            from django.utils import timezone
            Subscription.objects.update_or_create(
                workspace=workspace,
                defaults={
                    'plan': plan,
                    'interval': interval,
                    'status': sub_data['status'],
                    'stripe_subscription_id': subscription_id,
                    'current_period_start': timezone.datetime.fromtimestamp(sub_data['current_period_start'], tz=timezone.utc),
                    'current_period_end': timezone.datetime.fromtimestamp(sub_data['current_period_end'], tz=timezone.utc),
                },
            )
            workspace.plan = plan.plan_id
            workspace.save(update_fields=['plan'])


def handle_subscription_deleted(subscription_obj):
    workspace_id = subscription_obj.get('metadata', {}).get('workspace_id')
    if not workspace_id:
        try:
            workspace = Workspace.objects.get(stripe_customer_id=subscription_obj['customer'])
        except Workspace.DoesNotExist:
            return
    else:
        workspace = get_object_or_404(Workspace, id=workspace_id)
    workspace.plan = 'free'
    workspace.save(update_fields=['plan'])
    from .models import Subscription
    Subscription.objects.filter(workspace=workspace).update(status='canceled')


def handle_invoice_paid(invoice):
    subscription_id = invoice.get('subscription')
    if not subscription_id:
        return
    from .models import Subscription
    Subscription.objects.filter(stripe_subscription_id=subscription_id).update(status='active')


def handle_invoice_payment_failed(invoice):
    subscription_id = invoice.get('subscription')
    if not subscription_id:
        return
    from .models import Subscription
    Subscription.objects.filter(stripe_subscription_id=subscription_id).update(status='past_due')
