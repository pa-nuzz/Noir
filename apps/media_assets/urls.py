from django.urls import path

from . import views_api

app_name = 'media_assets'

urlpatterns = [
    path('', views_api.library, name='library'),
    path('upload/', views_api.upload, name='upload'),
    path('<int:asset_id>/', views_api.detail, name='detail'),
    path('<int:asset_id>/delete/', views_api.delete_asset, name='delete_asset'),
    path('folders/', views_api.folders, name='folders'),
    path('folders/<int:folder_id>/', views_api.folder_detail, name='folder_detail'),
    path('folders/<int:folder_id>/delete/', views_api.delete_folder, name='delete_folder'),
    path('api/assets/', views_api.api_assets, name='api_assets'),
    path('serve/<int:asset_id>/<str:file_type>/', views_api.serve_asset, name='serve_asset'),
]
