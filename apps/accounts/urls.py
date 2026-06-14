from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from .views import (
    login_view, register_view, logout_view, verify_email_view, resend_verification_view,
    password_reset_choice_view, password_reset_code_view, password_reset_resend_code,
)

app_name = "accounts"

urlpatterns = [
    path("login/", login_view, name="login"),
    path("register/", register_view, name="register"),
    path("logout/", logout_view, name="logout"),
    path('verify-email/<uidb64>/<token>/', verify_email_view, name='verify_email'),
    path('resend-verification/', resend_verification_view, name='resend_verification'),

    # Password Reset (Link or Code options)
    path('password-reset/',
         password_reset_choice_view,
         name='password_reset_choice'),
    path('password-reset/code/',
         password_reset_code_view,
         name='password_reset_code'),
    path('password-reset/resend-code/',
         password_reset_resend_code,
         name='password_reset_resend_code'),

    # Legacy link-based flow still accessible for direct access
    path('password-reset/link/',
         auth_views.PasswordResetView.as_view(
             template_name='auth/reset_password.html',
             email_template_name='auth/password_reset_email.txt',
             subject_template_name='auth/password_reset_subject.txt',
             success_url=reverse_lazy('accounts:password_reset_done')
         ),
         name='password_reset_link'),
    path('password-reset/done/',
         auth_views.PasswordResetDoneView.as_view(template_name='auth/password_reset_done.html'),
         name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(
             template_name='auth/password_reset_confirm.html',
             success_url=reverse_lazy('accounts:password_reset_complete')
         ),
         name='password_reset_confirm'),
    path('password-reset-complete/',
         auth_views.PasswordResetCompleteView.as_view(template_name='auth/password_reset_complete.html'),
         name='password_reset_complete'),
]


