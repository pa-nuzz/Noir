from django.urls import path

from . import views

app_name = 'trending'

urlpatterns = [
    path('api/feed/', views.feed_data, name='feed_data'),
    path('api/topics/', views.topic_list, name='topic_list'),
    path('api/topics/subscribe/', views.toggle_subscription, name='toggle_subscription'),
    path('api/feed/<int:item_id>/save-draft/', views.save_as_draft, name='save_as_draft'),
    path('api/feed/<int:item_id>/bookmark/', views.toggle_bookmark, name='toggle_bookmark'),
    path('api/feed/<int:item_id>/dismiss/', views.dismiss_item, name='dismiss_item'),
    path('api/profile/refresh/', views.refresh_profile, name='refresh_profile'),
]
