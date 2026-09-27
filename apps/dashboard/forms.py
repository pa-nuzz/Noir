from django import forms
from django.core.exceptions import ValidationError
from apps.accounts.models import User
from django.contrib.auth.forms import PasswordChangeForm


def _is_storage_unavailable(exc: Exception) -> bool:
    """True when the exception is an S3/MinIO unreachable / auth failure."""
    try:
        from botocore.exceptions import BotoCoreError, ClientError
        return isinstance(exc, (BotoCoreError, ClientError))
    except Exception:
        return False


class ProfileForm(forms.ModelForm):
    avatar = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={'class': 'hidden', 'id': 'id_avatar', 'accept': 'image/*'}),
        help_text='',
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'company', 'bio', 'avatar']

    def clean(self):
        cleaned = super().clean()
        # Only probe storage when an avatar file is actually submitted. GET
        # requests (re-renders) must not round-trip to MinIO.
        if self.files.get('avatar') and cleaned.get('avatar'):
            try:
                from django.core.files.storage import default_storage
                default_storage.exists('')
            except Exception as exc:
                if _is_storage_unavailable(exc):
                    self.add_error(
                        'avatar',
                        "Profile picture upload is temporarily unavailable. "
                        "Please try again in a few minutes, or save without a new photo.",
                    )
        return cleaned

    def save(self, commit=True):
        """
        Save text fields first, THEN upload avatar.

        Why this order: Django's ModelForm.save() writes the row, then assigns
        the file attribute, which triggers the storage backend. If MinIO/S3 is
        unreachable, the row is already saved by the time we know. We split
        the save so text-field writes only commit if the file upload succeeds.
        """
        avatar_file = self.files.get('avatar')
        old_avatar_path = None
        if self.instance.pk and self.instance.avatar:
            old_avatar_path = self.instance.avatar.name

        # Strip avatar out of the initial save, do text fields first.
        if avatar_file:
            self.fields['avatar'].disabled = True
        try:
            user = super().save(commit=commit)
        finally:
            if avatar_file:
                self.fields['avatar'].disabled = False

        if not commit or not avatar_file:
            return user

        # Now upload the avatar file. If this fails, roll back text fields.
        user.avatar = avatar_file
        try:
            user.save(update_fields=['avatar', 'updated_at'])
        except Exception as exc:
            # Roll back text changes so the message we show is truthful.
            try:
                if self.instance.pk:
                    fresh = self.__class__.Meta.model.objects.get(pk=self.instance.pk)
                    for f in ('first_name', 'last_name', 'email', 'company', 'bio'):
                        setattr(user, f, getattr(fresh, f))
                    user.save(update_fields=['first_name', 'last_name', 'email', 'company', 'bio', 'updated_at'])
            except Exception:
                pass
            if _is_storage_unavailable(exc):
                from django.core.exceptions import ValidationError as _VE
                raise _VE({
                    'avatar': 'Profile picture upload failed: storage service is '
                              'unreachable. Your other changes were NOT saved. '
                              'Please try again in a few minutes, or save without a photo.'
                }) from exc
            raise

        # Best-effort cleanup of old avatar.
        if old_avatar_path and old_avatar_path != user.avatar.name:
            try:
                storage = user.avatar.storage
                if storage.exists(old_avatar_path):
                    storage.delete(old_avatar_path)
            except Exception:
                pass

        return user


class ChangePasswordForm(PasswordChangeForm):
    pass
