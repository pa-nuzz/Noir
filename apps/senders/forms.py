from django import forms
from .models import Sender


class SenderForm(forms.ModelForm):
    smtp_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'SMTP Password / App Password'}),
        label='SMTP Password'
    )
    daily_limit = forms.IntegerField(
        required=False,  # Make it optional
        initial=100,  # Set a default value
        widget=forms.NumberInput(attrs={'placeholder': '100'})
    )

    class Meta:
        model = Sender
        fields = ['display_name', 'from_email', 'reply_to', 'provider', 'smtp_host', 'smtp_port',
                  'username', 'smtp_password', 'use_tls', 'daily_limit']

    def clean_smtp_port(self):
        port = self.cleaned_data['smtp_port']
        if port not in [25, 465, 587, 2525]:
            raise forms.ValidationError("Port must be 25, 465, 587, or 2525.")
        return port

    def clean_daily_limit(self):
        daily_limit = self.cleaned_data.get('daily_limit')
        if daily_limit is None:
            return 100  # Default value if not provided
        return daily_limit