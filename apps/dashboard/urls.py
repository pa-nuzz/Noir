from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("settings/", views.settings_view, name="settings"),
    path("profile/", views.profile_view, name="profile"),
    path("analytics/", views.platform_analytics, name="analytics"),
    path("notifications/clear/", views.clear_notifications_view, name="clear_notifications"),
    path("notifications/check/", views.check_notifications_view, name="check_notifications"),
    path("social-content/", views.social_content_hub, name="social_content_hub"),
]