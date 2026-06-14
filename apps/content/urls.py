from django.urls import path
from . import views

app_name = 'content'

urlpatterns = [
    path('', views.content_dashboard, name='dashboard'),
    path('generate/', views.content_generate, name='generate'),
    path('history/', views.content_history, name='history'),
    path('<int:pk>/', views.content_detail, name='detail'),
    path('<int:pk>/edit/', views.content_edit, name='edit'),
    path('<int:pk>/approve/', views.content_approve, name='approve'),
    path('<int:pk>/delete/', views.content_delete, name='delete'),
    path('<int:pk>/favorite/', views.content_favorite, name='favorite'),
]
