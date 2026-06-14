from django.contrib import admin

from .models import ContentGeneration, ContentVersion


@admin.register(ContentGeneration)
class ContentGenerationAdmin(admin.ModelAdmin):
    list_display = ['generation_type', 'platform', 'user', 'status', 'is_favorite', 'created_at']
    list_filter = ['generation_type', 'platform', 'status']
    search_fields = ['input_context', 'generated_content']


@admin.register(ContentVersion)
class ContentVersionAdmin(admin.ModelAdmin):
    list_display = ['generation', 'created_at']
