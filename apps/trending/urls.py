from django.urls import path

from . import views

app_name = 'trending'

urlpatterns = [
    path('api/feed/', views.feed_data, name='feed_data'),
    path('api/topics/', views.topic_list, name='topic_list'),
    path('api/topics/subscribe/', views.toggle_subscription, name='toggle_subscription'),
    path('api/topics/bulk-subscribe/', views.bulk_subscribe, name='bulk_subscribe'),
    path('api/feed/<int:item_id>/save-draft/', views.save_as_draft, name='save_as_draft'),
    path('api/feed/<int:item_id>/bookmark/', views.toggle_bookmark, name='toggle_bookmark'),
    path('api/feed/<int:item_id>/dismiss/', views.dismiss_item, name='dismiss_item'),
    path('api/feed/<int:item_id>/queue/', views.queue_for_publish, name='queue_for_publish'),
    path('api/feed/<int:item_id>/dequeue/', views.dequeue_currents, name='dequeue_currents'),
    path('api/feed/<int:item_id>/publish-draft/', views.publish_currents, name='publish_currents'),
    path('api/currents/', views.currents_data, name='currents_data'),
    path('api/automation/rules/save/', views.save_automation_rules, name='save_automation_rules'),
    path('api/automation/rules/', views.automation_rules_data, name='automation_rules_data'),
    path('api/automation/generate/', views.generate_automation_content, name='generate_automation_content'),
    path('api/automation/generated/', views.list_generated_items, name='list_generated_items'),
    path('api/automation/publish/<int:content_item_id>/', views.publish_automation_item, name='publish_automation_item'),
    path('api/automation/schedule/<int:content_item_id>/', views.schedule_automation_item, name='schedule_automation_item'),
    path('categories/', views.manage_categories, name='manage_categories'),
    path('api/profile/refresh/', views.refresh_profile, name='refresh_profile'),
]
