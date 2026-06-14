from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import get_user_model
from .models import User

UserModel = get_user_model()

class RegisterForm(UserCreationForm):
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    email = forms.EmailField(required=True)
    username = forms.CharField(max_length=150, required=True)
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
        username = self.cleaned_data.get('username')
        if not username:
            raise forms.ValidationError("Username is required.")
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username.lower()

    def save(self, commit=True):
        user = super().save(commit=False)
        # username is now provided by user, not auto-set to email
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
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        
        if username and password:
            # Try to find user by email first, then by username
            from django.contrib.auth import get_user_model
            UserModel = get_user_model()
            
            # Try to find user by email first
            user = None
            if '@' in username:
                try:
                    user = UserModel.objects.get(email__iexact=username)
                except UserModel.DoesNotExist:
                    pass
            
            # If not found by email, try username
            if not user:
                try:
                    user = UserModel.objects.get(username__iexact=username)
                except UserModel.DoesNotExist:
                    pass
            
            if user:
                # Check password
                if user.check_password(password):
                    self.user_cache = user
                else:
                    raise forms.ValidationError(
                        "Invalid password. Please try again.",
                        code='invalid_login',
                    )
            else:
                raise forms.ValidationError(
                    "No account found with this email or username.",
                    code='invalid_login',
                )
        return self.cleaned_data