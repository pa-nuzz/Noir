import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.forms import RegisterForm


class AuthFlowTests(TestCase):
    def setUp(self):
        self.user_password = "StrongPass123!"
        self.user = get_user_model().objects.create_user(
            username="testuser",
            email="test@example.com",
            password=self.user_password,
            first_name="Test",
            last_name="User",
        )

    def test_login_page_renders(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)

    def test_auth_pages_are_not_cached(self):
        for url_name in ("accounts:login", "accounts:register"):
            response = self.client.get(reverse(url_name))

            self.assertEqual(response.status_code, 200)
            self.assertIn("no-store", response.headers.get("Cache-Control", ""))

    def test_login_redirects_to_dashboard(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.user.email, "password": self.user_password},
        )
        self.assertRedirects(response, reverse("dashboard:dashboard"))

    def test_login_accepts_username(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.user.username, "password": self.user_password},
        )
        self.assertRedirects(response, reverse("dashboard:dashboard"))

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_register_creates_user_and_redirects(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "username": "newuser",
                "email": "new@example.com",
                "first_name": "New",
                "last_name": "User",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertRedirects(response, reverse("dashboard:dashboard"))
        user = get_user_model().objects.get(username="newuser")
        self.assertEqual(user.email, "new@example.com")
        self.assertFalse(user.email_verified)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_register_accepts_the_fields_shown_on_registration_form(self):
        page = self.client.get(reverse("accounts:register"))
        self.assertContains(page, 'name="first_name"')
        self.assertContains(page, 'name="last_name"')

        response = self.client.post(
            reverse("accounts:register"),
            {
                "username": "visiblefields",
                "email": "visible@example.com",
                "first_name": "Visible",
                "last_name": "Fields",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertRedirects(response, reverse("dashboard:dashboard"))
        self.assertTrue(
            get_user_model().objects.filter(username="visiblefields").exists()
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_register_submission_requires_and_accepts_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        page = csrf_client.get(reverse("accounts:register"))
        token = re.search(
            rb'name="csrfmiddlewaretoken" value="([^"]+)"', page.content
        ).group(1).decode()
        data = {
            "username": "csrfuser",
            "email": "csrf@example.com",
            "first_name": "Csrf",
            "last_name": "User",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        }

        missing_token = csrf_client.post(reverse("accounts:register"), data)
        self.assertEqual(missing_token.status_code, 403)

        successful = csrf_client.post(
            reverse("accounts:register"), {**data, "csrfmiddlewaretoken": token}
        )
        self.assertRedirects(successful, reverse("dashboard:dashboard"))

    def test_dashboard_requires_authentication(self):
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.get("Location", ""))

    def test_register_rejects_username_with_spaces(self):
        form = RegisterForm(data={
            "username": "test user",
            "email": "new@example.com",
            "first_name": "New",
            "last_name": "User",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        })

        self.assertFalse(form.is_valid())
        self.assertIn("Username must be one word with no spaces.", form.errors["username"])

    def test_username_availability_rejects_spaces(self):
        response = self.client.get(
            reverse("accounts:check_availability"),
            {"field": "test user", "type": "username"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["available"])
        self.assertEqual(response.json()["message"], "Username must be one word with no spaces")

    def test_email_availability_rejects_incomplete_email(self):
        response = self.client.get(
            reverse("accounts:check_availability"),
            {"field": "anuj.paudel061@", "type": "email"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["available"])
        self.assertEqual(response.json()["message"], "Enter a valid email address")

    def test_register_rejects_invalid_email(self):
        form = RegisterForm(data={
            "username": "newuser",
            "email": "anuj.paudel061@",
            "first_name": "New",
            "last_name": "User",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        })

        self.assertFalse(form.is_valid())
        self.assertIn("Enter a valid email address.", form.errors["email"])
