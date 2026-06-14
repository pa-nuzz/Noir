from django import forms
from apps.accounts.models import User
from django.contrib.auth.forms import PasswordChangeForm

class ProfileForm(forms.ModelForm):
    avatar = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'hidden', 'id': 'id_avatar', 'accept': 'image/*'}),
        help_text='',
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'company', 'bio', 'avatar']

class ChangePasswordForm(PasswordChangeForm):
    pass
