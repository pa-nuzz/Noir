from django.urls import path

from . import views_api

app_name = 'social_accounts'

urlpatterns = [
    path('tiktok/setup/', views_api.tiktok_setup, name='tiktok_setup'),
    path('', views_api.social_hub, name='social_hub'),
    path('connect/<str:platform>/', views_api.connect_platform, name='connect_platform'),
    path('oauth/<str:platform>/callback/', views_api.oauth_callback, name='oauth_callback'),
    path('select-page/', views_api.select_page, name='select_page'),
    path('accounts/<int:account_id>/disconnect/', views_api.disconnect_account, name='disconnect_account'),
    path('posts/', views_api.post_list, name='post_list'),
    path('posts/create/', views_api.post_create, name='post_create'),
    path('posts/<int:post_id>/', views_api.post_detail, name='post_detail'),
    path('posts/<int:post_id>/delete/', views_api.post_delete, name='post_delete'),
    path('posts/<int:post_id>/publish/', views_api.publish_post, name='publish_post'),
    path('analytics/', views_api.analytics_view, name='analytics_overview'),
    path('analytics/<int:post_id>/', views_api.analytics_view, name='analytics_detail'),
    path('calendar/', views_api.calendar_view, name='calendar'),
    path('calendar/<int:year>/<int:month>/', views_api.calendar_view, name='calendar_month'),
]
