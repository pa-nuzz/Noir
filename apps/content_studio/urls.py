from django.urls import path

from . import views_api, views_sheets_oauth

app_name = 'content_studio'

urlpatterns = [
    path('', views_api.dashboard, name='dashboard'),
    path('hub/', views_api.content_hub, name='content_hub'),
    path('calendar/', views_api.calendar_view, name='calendar'),
    path('generate/', views_api.generate, name='generate'),
    path('<int:item_id>/', views_api.detail, name='detail'),
    path('<int:item_id>/edit/', views_api.edit, name='edit'),
    path('<int:item_id>/refine/', views_api.refine, name='refine'),
    path('<int:item_id>/approve/', views_api.approve, name='approve'),
    path('<int:item_id>/delete/', views_api.delete, name='delete'),
    path('<int:item_id>/save-draft/', views_api.save_as_draft, name='save_draft'),
    path('history/', views_api.history, name='history'),
    path('excel-sheets/', views_api.excel_sheets, name='excel_sheets'),
    path('excel-sheets/add/', views_api.excel_sheets_add, name='excel_sheets_add'),
    path('excel-sheets/<int:sheet_id>/sync/', views_api.excel_sheets_sync, name='excel_sheets_sync'),
    path('excel-sheets/<int:sheet_id>/delete/', views_api.excel_sheets_delete, name='excel_sheets_delete'),
    
    # Google Sheets OAuth
    path('sheets/oauth/credentials/', views_sheets_oauth.google_sheets_save_credentials, name='sheets_save_credentials'),
    path('sheets/oauth/start/', views_sheets_oauth.google_sheets_auth_start, name='sheets_auth_start'),
    path('sheets/oauth/callback/', views_sheets_oauth.google_sheets_auth_callback, name='sheets_auth_callback'),
    path('sheets/oauth/disconnect/', views_sheets_oauth.google_sheets_auth_disconnect, name='sheets_auth_disconnect'),
    
    # Google Sheets Management
    path('sheets/list/', views_api.google_sheets_list, name='sheets_list'),
    path('sheets/create/', views_api.google_sheets_create, name='sheets_create'),
    path('sheets/select/', views_api.google_sheets_select, name='sheets_select'),
]
