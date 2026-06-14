from django.urls import path
from . import views

app_name = 'media'

urlpatterns = [
    path('', views.media_library, name='library'),
    path('upload/', views.media_upload, name='upload'),
    path('<int:pk>/', views.media_detail, name='detail'),
    path('<int:pk>/delete/', views.media_delete, name='delete'),
    path('<int:pk>/optimize/', views.media_optimize, name='optimize'),
    path('<int:pk>/tag/', views.media_auto_tag, name='auto_tag'),
    path('folders/', views.folder_list, name='folder_list'),
    path('folders/create/', views.folder_create, name='folder_create'),
    path('folders/<int:pk>/', views.folder_detail, name='folder_detail'),
    path('folders/<int:pk>/delete/', views.folder_delete, name='folder_delete'),
    path('search/', views.media_search, name='search'),
]
