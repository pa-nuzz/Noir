from django import forms

from .models import EmailInbox, EmailDraft


class EmailInboxConnectForm(forms.ModelForm):
    imap_password = forms.CharField(
        label='IMAP Password / App Password',
        required=True,
        widget=forms.PasswordInput(attrs={
            'class': 'auth-input',
            'placeholder': 'Your Gmail app password or Outlook password',
            'autocomplete': 'off',
        }),
        help_text='For Gmail, create an App Password. For Outlook, use your account password.',
    )

    class Meta:
        model = EmailInbox
        fields = ['provider', 'email_address', 'imap_password']
        widgets = {
            'provider': forms.Select(attrs={'class': 'auth-input'}),
            'email_address': forms.EmailInput(attrs={'class': 'auth-input', 'placeholder': 'you@example.com'}),
        }


class EmailDraftReviewForm(forms.ModelForm):
    class Meta:
        model = EmailDraft
        fields = ['edited_body', 'status', 'feedback']
        widgets = {
            'edited_body': forms.Textarea(attrs={'class': 'input-field', 'rows': 8}),
            'status': forms.Select(attrs={'class': 'input-field'}),
            'feedback': forms.Textarea(attrs={'class': 'input-field', 'rows': 2, 'placeholder': 'Optional feedback on the draft quality...'}),
        }


