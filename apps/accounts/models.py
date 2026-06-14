import random
import string
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    email = models.EmailField(unique=True)
    company = models.CharField(max_length=255, blank=True)
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    email_verified = models.BooleanField(default=False)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() #or self.email

    class Meta:
        verbose_name = 'User'


class PasswordResetCode(models.Model):
    """Stores verification codes for code-based password reset."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reset_codes')
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    # Code expires after 15 minutes
    EXPIRY_MINUTES = 15

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'code']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Reset code for {self.user.email}"

    @property
    def is_expired(self):
        """Check if the code has expired."""
        expiry_time = self.created_at + timedelta(minutes=self.EXPIRY_MINUTES)
        return timezone.now() > expiry_time

    @property
    def is_valid(self):
        """Check if code is valid (not used and not expired)."""
        return not self.used and not self.is_expired

    @classmethod
    def generate_code(cls):
        """Generate a random 6-digit code."""
        return ''.join(random.choices(string.digits, k=6))

    @classmethod
    def get_valid_code(cls, user, code):
        """Get a valid (non-expired, unused) code for a user."""
        try:
            reset_code = cls.objects.get(user=user, code=code, used=False)
            if reset_code.is_expired:
                return None
            return reset_code
        except cls.DoesNotExist:
            return None