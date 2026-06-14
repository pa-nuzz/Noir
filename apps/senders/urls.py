from django.urls import path

from .views import verify_sender, audit_sender_dns_view

app_name = 'senders'

urlpatterns = [
    path('verify/', verify_sender, name='verify_sender'),
    path('audit-dns/', audit_sender_dns_view, name='audit_dns'),
]
