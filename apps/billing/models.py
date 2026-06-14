from django.conf import settings
from django.db import models


class StoragePlan(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    price_per_gb_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=10.00)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['price_per_gb_monthly']

    def __str__(self):
        return f"{self.name} — Rs {self.price_per_gb_monthly}/GB/month"


class WorkspaceBilling(models.Model):
    workspace = models.OneToOneField(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='billing',
    )
    storage_plan = models.ForeignKey(
        StoragePlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workspaces',
    )
    storage_used_mb = models.IntegerField(default=0)
    storage_limit_mb = models.IntegerField(default=0)
    billing_email = models.EmailField(blank=True)
    monthly_cost_estimate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Workspace billing'

    def __str__(self):
        return f"Billing for {self.workspace.name}"

    def calculate_monthly_cost(self):
        if self.storage_plan:
            gb = self.storage_used_mb / 1024
            cost = gb * float(self.storage_plan.price_per_gb_monthly)
            self.monthly_cost_estimate = round(cost, 2)
        else:
            self.monthly_cost_estimate = 0
        return self.monthly_cost_estimate


class Plan(models.Model):
    PLAN_CHOICES = [
        ('free', 'Free'),
        ('pro', 'Pro'),
        ('enterprise', 'Enterprise'),
    ]
    INTERVAL_CHOICES = [
        ('month', 'Monthly'),
        ('year', 'Yearly'),
    ]

    plan_id = models.CharField(max_length=20, unique=True, choices=PLAN_CHOICES)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_yearly = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stripe_price_id_monthly = models.CharField(max_length=255, blank=True)
    stripe_price_id_yearly = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    features = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order']

    def __str__(self):
        return self.name

    def get_price(self, interval='month'):
        return self.price_monthly if interval == 'month' else self.price_yearly

    def get_stripe_price_id(self, interval='month'):
        return self.stripe_price_id_monthly if interval == 'month' else self.stripe_price_id_yearly


class Subscription(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('past_due', 'Past Due'),
        ('canceled', 'Canceled'),
        ('incomplete', 'Incomplete'),
        ('trialing', 'Trialing'),
        ('unpaid', 'Unpaid'),
    ]

    workspace = models.OneToOneField(
        'workspaces.Workspace',
        on_delete=models.CASCADE,
        related_name='subscription',
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='subscriptions')
    interval = models.CharField(max_length=10, choices=Plan.INTERVAL_CHOICES, default='month')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    stripe_subscription_id = models.CharField(max_length=255, unique=True, blank=True, null=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Subscriptions'

    def __str__(self):
        return f"{self.workspace.name} — {self.plan.name} ({self.status})"

    def is_active(self):
        return self.status in ('active', 'trialing')

    def cancel(self):
        self.status = 'canceled'
        self.canceled_at = None
        from django.utils import timezone
        self.canceled_at = timezone.now()
        self.save(update_fields=['status', 'canceled_at'])
