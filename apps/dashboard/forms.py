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

    def save(self, commit=True):
        old_avatar_path = None
        if self.instance.pk and self.instance.avatar:
            old_avatar_path = self.instance.avatar.name

        user = super().save(commit=commit)

        if old_avatar_path and 'avatar' in self.changed_data:
            storage = user.avatar.storage
            try:
                if storage.exists(old_avatar_path):
                    storage.delete(old_avatar_path)
            except Exception:
                pass

        return user


class ChangePasswordForm(PasswordChangeForm):
    pass
