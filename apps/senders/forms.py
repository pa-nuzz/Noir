from django import forms
from .models import Sender


class SenderForm(forms.ModelForm):
    smtp_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'SMTP Password / App Password'}),
        label='SMTP Password'
    )
    daily_limit = forms.IntegerField(
        required=False,
        initial=100,
        widget=forms.NumberInput(attrs={'placeholder': '100'})
    )
    send_delay_seconds = forms.FloatField(
        required=False,
        initial=3.0,
        min_value=1.0,
        max_value=120.0,
        label='Delay Between Sends',
        help_text='Small delay between bulk campaign emails to protect the sender account.',
        widget=forms.NumberInput(attrs={'placeholder': '3', 'step': '0.5', 'min': '1', 'max': '120'})
    )

    class Meta:
        model = Sender
        fields = ['display_name', 'from_email', 'reply_to', 'provider', 'smtp_host', 'smtp_port',
                  'username', 'smtp_password', 'use_tls', 'daily_limit', 'send_delay_seconds']

    def clean_smtp_port(self):
        port = self.cleaned_data['smtp_port']
        if port not in [25, 465, 587, 2525]:
            raise forms.ValidationError("Port must be 25, 465, 587, or 2525.")
        return port

    def clean_daily_limit(self):
        daily_limit = self.cleaned_data.get('daily_limit')
        if daily_limit is None:
            return 100
        return daily_limit

    def clean_send_delay_seconds(self):
        delay = self.cleaned_data.get('send_delay_seconds')
        if delay is None:
            return 3.0
        return delay
