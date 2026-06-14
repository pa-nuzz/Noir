from django.contrib import admin

from .models import StoragePlan, WorkspaceBilling, Plan, Subscription


@admin.register(StoragePlan)
class StoragePlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'price_per_gb_monthly', 'is_active']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(WorkspaceBilling)
class WorkspaceBillingAdmin(admin.ModelAdmin):
    list_display = ['workspace', 'storage_plan', 'storage_used_mb', 'monthly_cost_estimate']


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'plan_id', 'price_monthly', 'price_yearly', 'is_active']
    list_editable = ['is_active']


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['workspace', 'plan', 'status', 'interval', 'current_period_end']
    list_filter = ['status', 'plan']
