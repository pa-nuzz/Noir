import base64
import hashlib
import json
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.inbox.models import EmailInbox
from apps.inbox.services.sync import sync_inbox

User = get_user_model()


def _make_test_key():
    raw = base64.urlsafe_b64encode(hashlib.sha256(b'test-secret-key').digest())
    return raw.decode()


def _make_dev_key():
    return base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()).decode()


class EmailInboxTokenTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='pass1234')
        self.inbox = EmailInbox.objects.create(
            user=self.user,
            provider='gmail',
            email_address='test@gmail.com',
        )
        self.raw_password = 'my-secret-imap-password'

    @override_settings(FERNET_KEY=_make_test_key())
    def test_set_token_encrypts_and_stores(self):
        self.inbox.set_token(self.raw_password)
        self.assertNotEqual(self.inbox.access_token, self.raw_password)
        self.assertGreater(len(self.inbox.access_token), 20)

    @override_settings(FERNET_KEY=_make_test_key())
    def test_get_token_decrypts_correctly(self):
        self.inbox.set_token(self.raw_password)
        result = self.inbox.get_token()
        self.assertEqual(result, self.raw_password)

    @override_settings(FERNET_KEY=_make_test_key())
    def test_round_trip_preserves_value(self):
        self.inbox.set_token(self.raw_password)
        first = self.inbox.get_token()
        second = self.inbox.get_token()
        self.assertEqual(first, second)
        self.assertEqual(first, self.raw_password)

    @override_settings(FERNET_KEY=_make_test_key())
    def test_get_token_returns_none_when_empty(self):
        result = self.inbox.get_token()
        self.assertIsNone(result)

    @override_settings(DEBUG=True, FERNET_KEY='')
    def test_dev_fallback_key_works(self):
        self.inbox.set_token(self.raw_password)
        result = self.inbox.get_token()
        self.assertEqual(result, self.raw_password)

    @override_settings(FERNET_KEY=_make_test_key())
    def test_wrong_key_returns_none(self):
        self.inbox.set_token(self.raw_password)
        other_key = Fernet.generate_key().decode()
        with self.settings(FERNET_KEY=other_key):
            result = self.inbox.get_token()
            self.assertIsNone(result)


class SyncInboxTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='syncuser', password='pass1234')

    @patch('apps.inbox.services.sync.imaplib.IMAP4_SSL')
    def test_sync_inbox_no_password(self, mock_imap):
        inbox = EmailInbox.objects.create(
            user=self.user,
            provider='gmail',
            email_address='nopass@gmail.com',
        )
        result = sync_inbox(inbox, password='')
        self.assertEqual(result, 0)
        mock_imap.assert_not_called()

    @patch('apps.inbox.services.sync.imaplib.IMAP4_SSL')
    def test_sync_inbox_login_failure(self, mock_imap):
        inbox = EmailInbox.objects.create(
            user=self.user,
            provider='gmail',
            email_address='fail@gmail.com',
        )
        mock_instance = MagicMock()
        mock_imap.return_value = mock_instance
        mock_instance.login.side_effect = Exception('IMAP login failed')
        result = sync_inbox(inbox, password='somepass')
        self.assertEqual(result, 0)

    @patch('apps.inbox.services.sync.imaplib.IMAP4_SSL')
    def test_sync_inbox_no_new_messages(self, mock_imap):
        inbox = EmailInbox.objects.create(
            user=self.user,
            provider='gmail',
            email_address='empty@gmail.com',
        )
        mock_instance = MagicMock()
        mock_imap.return_value = mock_instance
        mock_instance.search.return_value = ('OK', [b''])
        result = sync_inbox(inbox, password='pass')
        self.assertEqual(result, 0)

    @patch('apps.inbox.services.sync.imaplib.IMAP4_SSL')
    def test_sync_inbox_invalid_provider(self, mock_imap):
        inbox = EmailInbox.objects.create(
            user=self.user,
            provider='unknown',
            email_address='unknown@example.com',
        )
        result = sync_inbox(inbox, password='pass')
        self.assertEqual(result, 0)
        mock_imap.assert_not_called()


class InboxViewsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='viewuser', email='viewuser@example.com',
            password='pass1234',
        )
        logged_in = self.client.login(email='viewuser@example.com', password='pass1234')
        self.assertTrue(logged_in, 'Login failed in setUp')

    @override_settings(FERNET_KEY=_make_test_key())
    @patch('apps.inbox.tasks.sync_inbox_task')
    def test_inbox_connect_encrypts_password(self, mock_task):
        mock_task.delay.return_value = None
        form_data = {
            'provider': 'gmail',
            'email_address': 'new@example.com',
            'imap_password': 'my-raw-password',
        }
        resp = self.client.post(reverse('inbox:connect'), form_data, follow=True)
        self.assertEqual(resp.status_code, 200)
        inbox = EmailInbox.objects.get(email_address='new@example.com')
        self.assertNotEqual(inbox.access_token, 'my-raw-password')
        self.assertEqual(inbox.get_token(), 'my-raw-password')

    def test_dashboard_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('inbox:dashboard'))
        self.assertEqual(resp.status_code, 302)

    def test_dashboard_shows_stats(self):
        EmailInbox.objects.create(user=self.user, provider='gmail', email_address='a@b.com')
        resp = self.client.get(reverse('inbox:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'a@b.com')
        self.assertContains(resp, 'Sync')

    def test_inbox_disconnect(self):
        inbox = EmailInbox.objects.create(user=self.user, provider='gmail', email_address='del@me.com')
        resp = self.client.post(reverse('inbox:disconnect', args=[inbox.id]), follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(EmailInbox.objects.filter(id=inbox.id).exists())

    def test_trash_view_accessible(self):
        resp = self.client.get(reverse('inbox:trash'))
        self.assertEqual(resp.status_code, 200)
