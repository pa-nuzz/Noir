from django.urls import path

from . import storage_views, views

app_name = 'workspaces'

urlpatterns = [
    path('', views.workspace_list, name='list'),
    path('create/', views.workspace_create, name='create'),
    path('<int:workspace_id>/', views.workspace_detail, name='detail'),
    path('<int:workspace_id>/edit/', views.workspace_edit, name='edit'),
    path('<int:workspace_id>/delete/', views.workspace_delete, name='delete'),
    path('<int:workspace_id>/members/', views.member_list, name='member_list'),
    path('<int:workspace_id>/members/<int:membership_id>/remove/', views.remove_member, name='remove_member'),
    path('<int:workspace_id>/members/leave/', views.leave_workspace, name='leave'),
    path('<int:workspace_id>/invite/', views.invite_member, name='invite'),
    path('invitations/', views.my_invitations, name='my_invitations'),
    path('invitations/<int:invitation_id>/accept/', views.accept_invitation, name='accept_invitation'),
    path('invitations/<int:invitation_id>/decline/', views.decline_invitation, name='decline_invitation'),
    path('invitations/<int:invitation_id>/cancel/', views.cancel_invitation, name='cancel_invitation'),
    path('<int:workspace_id>/audit-log/', views.audit_log_view, name='audit_log'),
    path('deactivate/', views.deactivate_workspace, name='deactivate'),
    path('<int:workspace_id>/activate/', views.set_active_workspace, name='activate'),
    path('<int:workspace_id>/overview/', views.workspace_overview, name='overview'),
    path('<int:workspace_id>/social/', views.workspace_social_hub, name='social_hub'),
    path('<int:workspace_id>/permissions/', views.workspace_permissions, name='permissions'),
    path('<int:workspace_id>/permissions/update/', views.workspace_permissions, name='permissions_update'),
    path('<int:workspace_id>/members/<int:membership_id>/role/', views.update_member_role, name='update_member_role'),
    path('<int:workspace_id>/onboarding/', views.workspace_onboarding, name='onboarding'),

    path('<int:workspace_id>/onboarding/', views.workspace_onboarding, name='onboarding'),
    path('<int:workspace_id>/onboarding/dismiss/', views.onboarding_dismiss, name='dismiss_onboarding'),

    path('storage/', storage_views.storage_settings, name='storage_settings'),
    path('storage/select/', storage_views.storage_select_backend, name='storage_select'),
    path('storage/google-drive/credentials/', storage_views.storage_google_drive_save_credentials, name='storage_google_drive_save_credentials'),
    path('storage/google-drive/start/', storage_views.storage_google_drive_start, name='storage_google_drive_start'),
    path('storage/google-drive/callback/', storage_views.storage_google_drive_callback, name='storage_google_drive_callback'),
    path('storage/google-drive/disconnect/', storage_views.storage_google_drive_disconnect, name='storage_google_drive_disconnect'),
    path('storage/dia-s3/test/', storage_views.storage_dia_s3_test, name='storage_dia_s3_test'),
    path('storage/s3/save/', storage_views.storage_s3_save, name='storage_s3_save'),
    path('storage/s3/test/', storage_views.storage_s3_test, name='storage_s3_test'),
    path('storage/s3/disconnect/', storage_views.storage_s3_disconnect, name='storage_s3_disconnect'),
    path('storage/test/', storage_views.storage_test, name='storage_test'),
    path('storage/health/', storage_views.storage_health, name='storage_health'),
]
