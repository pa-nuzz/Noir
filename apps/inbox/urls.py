from django.urls import path

from . import views

app_name = 'inbox'

urlpatterns = [
    path('', views.inbox_dashboard, name='dashboard'),
    path('connect/', views.inbox_connect, name='connect'),
    path('<int:inbox_id>/disconnect/', views.inbox_disconnect, name='disconnect'),
    path('<int:inbox_id>/sync/', views.inbox_sync, name='sync'),
    path('<int:inbox_id>/sync-status/',
         views.inbox_sync_status, name='sync_status'),
    path('messages/<int:message_id>/',
         views.message_detail, name='message_detail'),
    path('drafts/<int:draft_id>/', views.draft_detail, name='draft_detail'),
    path('drafts/<int:draft_id>/approve/',
         views.draft_approve, name='draft_approve'),
    path('drafts/<int:draft_id>/send/', views.draft_send, name='draft_send'),
    path('drafts/<int:draft_id>/send-test/',
         views.draft_send_test, name='draft_send_test'),
    path('messages/<int:message_id>/generate-draft/',
         views.generate_draft, name='generate_draft'),
    path('messages/<int:message_id>/summarize/',
         views.message_summarize, name='message_summarize'),
    path('messages/<int:message_id>/delete/',
         views.message_delete, name='message_delete'),
    path('drafts/<int:draft_id>/delete/',
         views.draft_delete, name='draft_delete'),
    path('trash/', views.inbox_trash, name='trash'),
    path('messages/<int:message_id>/restore/',
         views.message_restore, name='message_restore'),
    path('<int:inbox_id>/auto-reply/', views.inbox_auto_reply, name='auto_reply'),
    path('bulk-auto-reply/', views.bulk_auto_reply, name='bulk_auto_reply'),
    path('bulk-action/', views.bulk_action, name='bulk_action'),
    path('proxy-image/', views.proxy_email_image, name='proxy_image'),
    path('sender-logo/', views.sender_logo_proxy, name='sender_logo'),
]
