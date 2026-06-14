from django.urls import path

from . import views

app_name = 'billing'

urlpatterns = [
    path('', views.billing_dashboard, name='dashboard'),
    path('subscribe/<int:plan_id>/<str:interval>/', views.create_subscription_checkout, name='subscribe'),
    path('portal/', views.billing_portal, name='portal'),
    path('webhook/stripe/', views.stripe_webhook, name='stripe_webhook'),
]
