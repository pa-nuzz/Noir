from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django_ratelimit.decorators import ratelimit
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.conf import settings
from django.contrib.auth.forms import SetPasswordForm
from django.http import JsonResponse
from .forms import RegisterForm, LoginForm
from django.contrib import messages
from .models import User, PasswordResetCode


def _send_verification_email(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    verify_path = reverse('accounts:verify_email', kwargs={'uidb64': uid, 'token': token})
    verify_url = request.build_absolute_uri(verify_path)

    subject = 'Verify your Intelligent Digital Automation (IDA) email'
    message = (
        f"Hi {user.get_full_name() or user.email},\n\n"
        "Please verify your email by clicking the link below:\n"
        f"{verify_url}\n\n"
        "If you did not create this account, you can ignore this email.\n\n"
        "— Intelligent Digital Automation (IDA)"
    )

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )

@ratelimit(key='ip', rate='10/m', method='POST', block=True)
def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard:dashboard")
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            try:
                _send_verification_email(request, user)
                messages.success(request, "Account created. Verification email sent — please verify your email.")
            except Exception as exc:
                messages.warning(request, f"Account created, but verification email could not be sent: {exc}")
            return redirect("dashboard:dashboard")
    else:
        form = RegisterForm()
    return render(request, "auth/register.html", {"form": form})

@ratelimit(key='ip', rate='10/m', method='POST', block=True)
def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard:dashboard")
    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            next_url = request.POST.get('next') or request.GET.get('next') or '/dashboard/'
            from django.utils.http import url_has_allowed_host_and_scheme
            if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
            return redirect('/dashboard/')
    else:
        form = LoginForm()
    return render(request, "auth/login.html", {"form": form, "next": request.GET.get('next', '')})

@require_POST
@login_required
def logout_view(request):
    logout(request)
    return redirect("home")


def verify_email_view(request, uidb64, token):
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
        from .models import User
        user = User.objects.filter(pk=user_id).first()
    except Exception:
        user = None

    if user and default_token_generator.check_token(user, token):
        if not user.email_verified:
            user.email_verified = True
            user.save(update_fields=['email_verified'])
        messages.success(request, "Your email is verified.")
    else:
        messages.error(request, "Invalid or expired verification link.")

    if request.user.is_authenticated:
        return redirect('dashboard:profile')
    return redirect('accounts:login')


@login_required
def resend_verification_view(request):
    if request.user.email_verified:
        messages.info(request, "Email is already verified.")
        return redirect('dashboard:profile')

    try:
        _send_verification_email(request, request.user)
        messages.success(request, "Verification email sent. Please check your inbox.")
    except Exception as exc:
        messages.error(request, f"Could not send verification email: {exc}")

    return redirect('dashboard:profile')


# ============================
# Password Reset Views (Link + Code Options)
# ============================

@ratelimit(key='ip', rate='5/m', method='POST', block=True)
def password_reset_choice_view(request):
    """
    First step: User enters email and chooses reset method.
    Options: 'link' (email link) or 'code' (6-digit verification code).
    """
    if request.user.is_authenticated:
        return redirect('dashboard:dashboard')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        method = request.POST.get('method', '').strip()

        if not email or '@' not in email:
            messages.error(request, 'Please enter a valid email address.')
            return redirect('accounts:password_reset_choice')

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Don't reveal if user exists (security best practice)
            messages.success(request, 'If an account exists with this email, you will receive password reset instructions.')
            return redirect('accounts:login')

        if method == 'code':
            # Generate and send code
            code = PasswordResetCode.generate_code()
            PasswordResetCode.objects.create(user=user, code=code)

            # Send code via email
            try:
                send_mail(
                    subject='Password Reset Code - Intelligent Digital Automation (IDA)',
                    message=(
                        f"Hi {user.get_full_name() or user.email},\n\n"
                        f"Your password reset code is: {code}\n\n"
                        f"This code will expire in {PasswordResetCode.EXPIRY_MINUTES} minutes.\n\n"
                        f"If you didn't request this, you can ignore this email.\n\n"
                        f"— Intelligent Digital Automation (IDA)"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
                # Store email in session for code verification page
                request.session['password_reset_email'] = email
                messages.success(request, 'A 6-digit code has been sent to your email. Enter it below.')
                return redirect('accounts:password_reset_code')
            except Exception as exc:
                messages.error(request, f'Could not send email: {exc}')
                return redirect('accounts:password_reset_choice')

        elif method == 'link':
            # Use Django's built-in password reset
            from django.contrib.auth.views import PasswordResetView
            # Create a POST request to the built-in view
            reset_view = PasswordResetView.as_view(
                template_name='auth/reset_password.html',
                email_template_name='auth/password_reset_email.txt',
                subject_template_name='auth/password_reset_subject.txt',
                success_url=reverse_lazy('accounts:password_reset_done')
            )
            # Fake a POST request to the built-in view
            from django.test import RequestFactory
            factory = RequestFactory()
            post_request = factory.post('/password-reset/', {'email': email})
            post_request.session = request.session
            return reset_view(post_request)

        else:
            messages.error(request, 'Please select a valid reset method.')
            return redirect('accounts:password_reset_choice')

    return render(request, 'auth/password_reset_choice.html')


@ratelimit(key='ip', rate='10/m', method='POST', block=True)
def password_reset_code_view(request):
    """
    Second step (code method): User enters the 6-digit code received via email.
    """
    if request.user.is_authenticated:
        return redirect('dashboard:dashboard')

    email = request.session.get('password_reset_email')
    if not email:
        messages.error(request, 'Please start the password reset process again.')
        return redirect('accounts:password_reset_choice')

    if request.method == 'POST':
        code = request.POST.get('code', '').strip()

        if not code or not code.isdigit() or len(code) != 6:
            messages.error(request, 'Please enter a valid 6-digit code.')
            return redirect('accounts:password_reset_code')

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            messages.error(request, 'Invalid request. Please start over.')
            return redirect('accounts:password_reset_choice')

        # Validate the code
        reset_code = PasswordResetCode.get_valid_code(user, code)

        if not reset_code:
            messages.error(request, 'Invalid or expired code. Please try again or request a new code.')
            return redirect('accounts:password_reset_code')

        # Code is valid - mark as used and redirect to password change
        reset_code.used = True
        reset_code.save(update_fields=['used'])

        # Generate token for password reset (same as Django's built-in)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        # Redirect to password change page
        return redirect('accounts:password_reset_confirm', uidb64=uid, token=token)

    return render(request, 'auth/password_reset_code.html', {'email': email})


@ratelimit(key='ip', rate='5/m', method='POST', block=True)
def password_reset_resend_code(request):
    """Resend a new code to the user's email."""
    if request.user.is_authenticated:
        return redirect('dashboard:dashboard')

    email = request.session.get('password_reset_email')
    if not email:
        messages.error(request, 'Please start the password reset process again.')
        return redirect('accounts:password_reset_choice')

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        messages.error(request, 'Invalid request. Please start over.')
        return redirect('accounts:password_reset_choice')

    # Generate new code
    code = PasswordResetCode.generate_code()
    PasswordResetCode.objects.create(user=user, code=code)

    try:
        send_mail(
            subject='Password Reset Code - Intelligent Digital Automation (IDA)',
            message=(
                f"Hi {user.get_full_name() or user.email},\n\n"
                f"Your new password reset code is: {code}\n\n"
                f"This code will expire in {PasswordResetCode.EXPIRY_MINUTES} minutes.\n\n"
                f"If you didn't request this, you can ignore this email.\n\n"
                f"— Intelligent Digital Automation (IDA)"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        messages.success(request, 'A new code has been sent to your email.')
    except Exception as exc:
        messages.error(request, f'Could not send email: {exc}')

    return redirect('accounts:password_reset_code')


@ratelimit(key='ip', rate='20/m', method='GET', block=True)
@require_GET
def check_availability(request):
    """Check if email or username is available for registration. Accepts a single field that can be either email or username."""
    field_value = request.GET.get('field', '').strip().lower()
    
    if not field_value:
        return JsonResponse({
            'available': False,
            'message': 'Enter a valid email or username',
            'field': 'field'
        })

    # Check if field_value looks like an email (contains @)
    is_email = '@' in field_value
    
    if is_email:
        # Check email availability
        exists = User.objects.filter(email__iexact=field_value).exists()
        if exists:
            return JsonResponse({
                'available': False,
                'message': 'This email is already registered',
                'field': 'email'
            })
        return JsonResponse({
            'available': True,
            'message': 'Email is available',
            'field': 'email'
        })
    else:
        # Check username availability
        exists = User.objects.filter(username__iexact=field_value).exists()
        if exists:
            return JsonResponse({
                'available': False,
                'message': 'This username is already taken',
                'field': 'username'
            })
        return JsonResponse({
            'available': True,
            'message': 'Username is available',
            'field': 'username'
        })


