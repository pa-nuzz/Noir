from django.urls import path
from . import views

app_name = 'social'

urlpatterns = [
    path('', views.social_dashboard, name='dashboard'),
    path('accounts/', views.account_list, name='account_list'),
    path('accounts/connect/', views.account_connect, name='account_connect'),
    path('accounts/<int:account_id>/disconnect/', views.account_disconnect, name='account_disconnect'),
    path('posts/', views.post_list, name='post_list'),
    path('posts/create/', views.post_create, name='post_create'),
    path('posts/<int:post_id>/', views.post_detail, name='post_detail'),
    path('posts/<int:post_id>/edit/', views.post_edit, name='post_edit'),
    path('posts/<int:post_id>/delete/', views.post_delete, name='post_delete'),
    path('analytics/', views.analytics_overview, name='analytics'),
]
