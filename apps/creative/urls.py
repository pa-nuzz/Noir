from django.urls import path

from . import views

app_name = 'creative'

urlpatterns = [
    path('media/', views.media_library, name='media_library'),
    path('strategy/', views.strategy_studio, name='strategy_studio'),
    path('strategy/<int:strategy_id>/', views.strategy_detail, name='strategy_detail'),
    path('context/', views.company_context, name='company_context'),
    path('api/assets/', views.api_assets_json, name='api_assets'),
    path('api/folder-tree/', views.api_folder_tree, name='api_folder_tree'),
    path('api/update-asset-status/', views.api_update_asset_status, name='api_update_asset_status'),
    path('api/strategy-status/', views.api_strategy_status, name='api_strategy_status'),
    path('api/chat-generate/', views.api_chat_generate, name='api_chat_generate'),
    path('api/strategy-update/', views.api_strategy_update, name='api_strategy_update'),
    path('api/strategy-inputs/', views.api_strategy_inputs, name='api_strategy_inputs'),
    path('api/strategy-inputs/<str:strategy_type>/', views.api_strategy_inputs, name='api_strategy_inputs_detail'),
    # Media asset serve and upload (workspace-isolated)
    path('serve-asset/<int:asset_id>/<str:file_type>/', views.serve_creative_asset, name='serve_asset'),
    path('upload-media/', views.upload_media, name='upload_media'),
]
