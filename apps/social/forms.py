from django import forms

from .models import SocialAccount, SocialPost


class SocialAccountForm(forms.ModelForm):
    class Meta:
        model = SocialAccount
        fields = ['platform', 'account_name', 'account_id']
        widgets = {
            'platform': forms.Select(attrs={'class': 'input-field'}),
            'account_name': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'e.g. My Business Page'}),
            'account_id': forms.TextInput(attrs={'class': 'input-field', 'placeholder': 'Platform account/user ID (optional)'}),
        }


class SocialPostForm(forms.ModelForm):
    scheduled_at = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'input-field'}),
        help_text='Leave blank to save as draft',
    )

    class Meta:
        model = SocialPost
        fields = ['account', 'content', 'media_urls', 'link_url', 'scheduled_at']
        widgets = {
            'account': forms.Select(attrs={'class': 'input-field'}),
            'content': forms.Textarea(attrs={'class': 'input-field', 'rows': 5, 'placeholder': 'Write your post content here...'}),
            'media_urls': forms.Textarea(attrs={'class': 'input-field', 'rows': 2, 'placeholder': 'One URL per line'}),
            'link_url': forms.URLInput(attrs={'class': 'input-field', 'placeholder': 'https://...'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields['account'].queryset = SocialAccount.objects.filter(user=user, is_active=True)
        self.fields['account'].empty_label = '— Select Account —'

    def clean_media_urls(self):
        data = self.cleaned_data['media_urls']
        if isinstance(data, str):
            lines = [line.strip() for line in data.split('\n') if line.strip()]
            return lines
        return data or []

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('scheduled_at') and cleaned['scheduled_at'] < __import__('django').utils.timezone.now():
            raise forms.ValidationError('Scheduled time must be in the future.')
        return cleaned
