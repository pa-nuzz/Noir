from django.urls import path

from . import views

app_name = 'webhooks'

urlpatterns = [
    path('', views.webhook_list, name='list'),
    path('create/', views.webhook_create, name='create'),
    path('<int:pk>/toggle/', views.webhook_toggle, name='toggle'),
    path('<int:pk>/test/', views.webhook_test, name='test'),
]
