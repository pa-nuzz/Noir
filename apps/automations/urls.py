from django.urls import path
from . import views

app_name = 'automations'

urlpatterns = [
    path('', views.workflow_list, name='workflow_list'),
    path('create/', views.workflow_create, name='workflow_create'),
    path('<int:workflow_id>/edit/', views.workflow_edit, name='workflow_edit'),
    path('<int:workflow_id>/delete/', views.workflow_delete, name='workflow_delete'),
    path('<int:workflow_id>/toggle/', views.workflow_toggle, name='workflow_toggle'),
    path('<int:workflow_id>/analytics/', views.workflow_analytics, name='workflow_analytics'),
    path('api/nodes/', views.workflow_api_save_nodes, name='api_save_nodes'),
]
