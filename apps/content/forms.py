from django import forms

from .models import ContentGeneration


class ContentGenerateForm(forms.Form):
    GENERATION_TYPES = [
        ('caption', 'Caption — Platform-optimized post caption'),
        ('hashtags', 'Hashtags — Relevant and trending hashtags'),
        ('carousel', 'Carousel — Slide-by-slide structure with CTAs'),
        ('video_script', 'Video Script — 15s, 30s, or 60s format'),
        ('image_prompt', 'Image Prompt — DALL-E / Midjourney ready'),
        ('cta', 'CTA — Click-through, engagement, or conversion'),
    ]

    generation_type = forms.ChoiceField(
        choices=GENERATION_TYPES,
        widget=forms.Select(attrs={'class': 'auth-input'}),
    )
    platform = forms.ChoiceField(
        choices=ContentGeneration.PLATFORM_CHOICES,
        widget=forms.Select(attrs={'class': 'auth-input'}),
    )
    topic = forms.CharField(
        max_length=500,
        widget=forms.TextInput(attrs={'class': 'auth-input', 'placeholder': 'e.g. New product launch, motivational quote, industry insight...'}),
        help_text='What is this content about?',
    )
    keywords = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'auth-input', 'placeholder': 'keyword1, keyword2, keyword3'}),
        help_text='Optional keywords to include',
    )
    tone = forms.ChoiceField(
        choices=[
            ('professional', 'Professional'),
            ('casual', 'Casual / Conversational'),
            ('humorous', 'Humorous'),
            ('inspirational', 'Inspirational'),
            ('urgent', 'Urgent'),
        ],
        widget=forms.Select(attrs={'class': 'auth-input'}),
        initial='professional',
    )
    length = forms.ChoiceField(
        choices=[
            ('short', 'Short'),
            ('medium', 'Medium'),
            ('long', 'Long'),
        ],
        widget=forms.Select(attrs={'class': 'auth-input'}),
        initial='medium',
        help_text='Desired length of output',
    )
    include_hashtags = forms.BooleanField(
        required=False,
        initial=True,
        label='Include hashtags',
        widget=forms.CheckboxInput(attrs={'class': 'rounded border-slate-300'}),
    )


class ContentReviewForm(forms.ModelForm):
    class Meta:
        model = ContentGeneration
        fields = ['generated_content', 'status']
        widgets = {
            'generated_content': forms.Textarea(attrs={'class': 'auth-input', 'rows': 8}),
            'status': forms.Select(attrs={'class': 'auth-input'}),
        }
