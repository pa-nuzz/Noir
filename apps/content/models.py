from django.db import models
from django.conf import settings

from core.models import AuditMixin


class ContentGeneration(AuditMixin):
    GENERATION_TYPES = [
        ('caption', 'Caption'),
        ('hashtags', 'Hashtags'),
        ('carousel', 'Carousel Content'),
        ('video_script', 'Video Script'),
        ('image_prompt', 'Image Prompt'),
        ('cta', 'CTA'),
    ]

    PLATFORM_CHOICES = [
        ('instagram', 'Instagram'),
        ('facebook', 'Facebook'),
        ('twitter', 'X (Twitter)'),
        ('linkedin', 'LinkedIn'),
        ('tiktok', 'TikTok'),
        ('youtube', 'YouTube'),
        ('generic', 'Generic'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('review', 'Needs Review'),
        ('approved', 'Approved'),
        ('published', 'Published'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='content_generations')
    generation_type = models.CharField(max_length=20, choices=GENERATION_TYPES)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default='generic')

    input_context = models.TextField(blank=True, help_text='Topic, keywords, or context for generation')
    generated_content = models.TextField(blank=True, help_text='AI-generated output text')
    raw_prompt = models.TextField(blank=True, help_text='The full prompt sent to AI')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    is_favorite = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_generation_type_display()} — {self.input_context[:50]}"


class ContentVersion(AuditMixin):
    generation = models.ForeignKey(ContentGeneration, on_delete=models.CASCADE, related_name='versions')
    content = models.TextField()
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Version {self.id} of {self.generation}"
