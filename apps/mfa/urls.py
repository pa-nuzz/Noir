from django.urls import path

from . import views

app_name = 'mfa'

urlpatterns = [
    path('settings/', views.mfa_settings, name='settings'),
    path('enable/', views.mfa_enable, name='enable'),
    path('disable/', views.mfa_disable, name='disable'),
    path('required/', views.mfa_required, name='required'),
]
