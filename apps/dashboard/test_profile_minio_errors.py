"""Tests for the profile section.

These tests verify defensive behavior against MinIO/S3 client errors so a
broken storage backend yields a user-friendly message rather than a 500.

Run with:  ./venv/bin/python -m pytest apps/dashboard/test_profile_minio_errors.py -v
(Or: manage.py test apps.dashboard.test_profile_minio_errors -v 2)
"""
import struct
import zlib
from unittest import mock

from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from botocore.exceptions import ClientError

from apps.accounts.models import User
from apps.dashboard.forms import ProfileForm
from apps.dashboard.views import profile_view


def _fake_png_bytes():
    sig = b'\x89PNG\r\n\x1a\n'

    def chunk(t, d):
        c = t + d
        return struct.pack('>I', len(d)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
    idat = chunk(b'IDAT', zlib.compress(b'\x00\x00\x00\x00'))
    iend = chunk(b'IEND', b'')
    return sig + ihdr + idat + iend


class _BoomStorage:
    def save(self, name, content, max_length=None):
        raise ClientError(
            {'Error': {'Code': 'InvalidAccessKeyId', 'Message': 'bad'}},
            'PutObject',
        )


class ProfileViewClientErrorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='alice', email='alice@example.com', password='pw'
        )
        self.factory = RequestFactory()

    def _post_request(self):
        png = _fake_png_bytes()
        upload = SimpleUploadedFile('avatar.png', png, content_type='image/png')
        req = self.factory.post(
            '/dashboard/profile/',
            data={
                'action': 'update_profile',
                'first_name': 'A',
                'last_name': 'B',
                'email': 'alice@example.com',
            },
            files={'avatar': upload},
        )
        req.user = self.user
        # Attach session + message storage so the view can `messages.success`.
        req.session = {}
        req._messages = FallbackStorage(req)
        return req

    def test_profile_view_minio_failure_does_not_500(self):
        req = self._post_request()

        with mock.patch.object(self.user.avatar, 'storage', _BoomStorage()):
            response = profile_view(req)

        # Must NOT raise; should re-render the profile template with form errors
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/profile.html')


class ProfileFormSaveTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='bob', email='bob@example.com', password='pw'
        )

    def test_form_save_reraises_storage_failure_as_value_error(self):
        upload = SimpleUploadedFile(
            'avatar.png', _fake_png_bytes(), content_type='image/png'
        )
        form = ProfileForm(
            data={
                'first_name': 'A',
                'last_name': 'B',
                'email': 'bob@example.com',
            },
            files={'avatar': upload},
            instance=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)

        with mock.patch.object(self.user.avatar, 'storage', _BoomStorage()):
            from django.core.exceptions import ValidationError
            with self.assertRaises((ValueError, ValidationError)):
                form.save()
