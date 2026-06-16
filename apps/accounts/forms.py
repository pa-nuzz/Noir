import re

from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import get_user_model
from .models import User

UserModel = get_user_model()

class RegisterForm(UserCreationForm):
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(required=True)
    username = forms.CharField(
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            'autocomplete': 'username',
            'inputmode': 'text',
            'pattern': r'[A-Za-z0-9_@.+-]+',
        })
    )
    company = forms.CharField(max_length=255, required=False)

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "company")

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not email:
            raise forms.ValidationError("Email is required.")
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email.lower()

    def clean_username(self):
        username = (self.cleaned_data.get('username') or '').strip().lower()
        if not username:
            raise forms.ValidationError("Username is required.")
        if re.search(r'\s', username):
            raise forms.ValidationError("Username must be one word with no spaces.")
        if not re.fullmatch(r'[\w.@+-]+', username):
            raise forms.ValidationError("Username can only use letters, numbers, and @/./+/-/_.")
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            if hasattr(self, 'save_m2m'):
                self.save_m2m()
        return user


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Email or Username", 
        widget=forms.TextInput(attrs={'placeholder': 'Email or Username', 'autocomplete': 'username'})
    )
    password = forms.CharField(widget=forms.PasswordInput(attrs={'placeholder': 'Password', 'autocomplete': 'current-password'}))

    def clean(self):
        raw_username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if raw_username and password:
            from django.contrib.auth import authenticate
            self.user_cache = authenticate(self.request, username=raw_username, password=password)
            if self.user_cache is None:
                try:
                    user_obj = User.objects.get(username__iexact=raw_username)
                    self.user_cache = authenticate(self.request, username=user_obj.email, password=password)
                except User.DoesNotExist:
                    pass
            if self.user_cache is None:
                raise forms.ValidationError(
                    "Invalid email/username or password.",
                    code='invalid_login',
                )
            self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data
