from django.urls import path
from .views import (
    analyze_spam, generate_copilot_content, auto_reply_settings,
    api_auto_reply_rules, api_auto_reply_rule_detail, api_trigger_auto_reply,
    generate_page, api_generate, api_generate_status,
)

app_name = "intelligence"

urlpatterns = [
    path('api/analyze/', analyze_spam, name='analyze_spam'),
    path('api/copilot/', generate_copilot_content, name='copilot'),
    path('settings/', auto_reply_settings, name='auto_reply_settings'),
    path('api/rules/', api_auto_reply_rules, name='api_auto_reply_rules'),
    path('api/rules/<int:rule_id>/', api_auto_reply_rule_detail, name='api_auto_reply_rule_detail'),
    path('api/trigger/<int:message_id>/', api_trigger_auto_reply, name='api_trigger_auto_reply'),
    path('generate/', generate_page, name='generate'),
    path('api/generate/', api_generate, name='api_generate'),
    path('api/generate/status/', api_generate_status, name='api_generate_status'),
]
