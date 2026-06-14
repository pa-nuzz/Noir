from django.contrib import admin

from .models import CreativeContext, CreativeStrategy, CreativeStrategyAsset


@admin.register(CreativeContext)
class CreativeContextAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'user', 'workspace', 'updated_at')
    list_filter = ('workspace',)
    search_fields = ('company_name', 'mission_statement', 'goals')


@admin.register(CreativeStrategy)
class CreativeStrategyAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'status', 'tone_of_voice', 'created_at')
    list_filter = ('status', 'tone_of_voice', 'workspace')
    search_fields = ('title', 'campaign_goal', 'generated_output')


@admin.register(CreativeStrategyAsset)
class CreativeStrategyAssetAdmin(admin.ModelAdmin):
    list_display = ('strategy', 'asset', 'created_at')
    list_filter = ('strategy__workspace',)
