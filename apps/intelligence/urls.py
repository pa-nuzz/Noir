from django.urls import path
from .views import analyze_spam, generate_copilot_content

app_name = "intelligence"

urlpatterns = [
    path('api/analyze/', analyze_spam, name='analyze_spam'),
    path('api/copilot/', generate_copilot_content, name='copilot'),
]

