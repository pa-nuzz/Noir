from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


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

    def test_login_redirects_to_dashboard(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.user.email, "password": self.user_password},
        )
        self.assertRedirects(response, reverse("dashboard:dashboard"))

    def test_dashboard_requires_authentication(self):
        response = self.client.get(reverse("dashboard:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.get("Location", ""))