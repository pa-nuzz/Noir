from django.urls import path
from . import views

app_name = 'contacts'

urlpatterns = [
    path('', views.contacts_home, name='list'),
    path('tags/', views.tags_manager, name='tags_manager'),
    path('tags/bulk-update/', views.bulk_update_contact_tags, name='bulk_update_contact_tags'),
    path('bulk-delete/', views.bulk_delete_contacts, name='bulk_delete_contacts'),
    path('bulk-delete-lists/', views.bulk_delete_lists, name='bulk_delete_lists'),
    path('import-csv/', views.import_csv, name='import_csv'),
    path('add/', views.add_contact, name='add_contact'),
    path('delete/<int:contact_id>/', views.delete_contact, name='delete_contact'),
    path('delete-list/<int:list_id>/', views.delete_list, name='delete_list'),
    path('create-list/', views.create_list, name='create_list'),

    # Custom fields
    path('custom-fields/', views.custom_fields_list, name='custom_fields'),
    path('custom-fields/create/', views.custom_field_create, name='custom_field_create'),
    path('custom-fields/<int:pk>/delete/', views.custom_field_delete, name='custom_field_delete'),

    # Segments
    path('segments/', views.segment_list, name='segment_list'),
    path('segments/create/', views.segment_create, name='segment_create'),
    path('segments/count-preview/', views.segment_count_preview, name='segment_count_preview'),
    path('segments/<int:pk>/', views.segment_detail, name='segment_detail'),
    path('segments/<int:pk>/delete/', views.segment_delete, name='segment_delete'),

    # Export CSV
    path('export-csv/', views.export_csv, name='export_csv'),

    # Unsubscribe management
    path('unsubscribes/', views.unsubscribe_list, name='unsubscribe_list'),

    # GDPR
    path('gdpr/', views.gdpr_tools, name='gdpr'),
    path('gdpr/export-data/', views.gdpr_export_data, name='gdpr_export'),
    path('gdpr/anonymize/<int:contact_id>/', views.gdpr_anonymize_contact, name='gdpr_anonymize'),

    # Contact detail with custom fields
    path('<int:contact_id>/', views.contact_detail, name='contact_detail'),
    path('<int:contact_id>/edit/', views.contact_edit, name='contact_edit'),
]
