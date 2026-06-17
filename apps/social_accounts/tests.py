import tempfile
from unittest.mock import Mock, patch

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import SimpleTestCase, override_settings

from apps.social_accounts.models import SocialAccount
from apps.social_accounts.platforms.linkedin import LinkedInPlatform


class LinkedInMediaUploadTests(SimpleTestCase):
    def setUp(self):
        self.media_root = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_root.name,
            MEDIA_URL='/media/',
            PUBLIC_BASE_URL='https://ida.example.com',
        )
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        self.media_root.cleanup()

    def test_absolute_media_url_uses_public_base_for_relative_urls(self):
        platform = LinkedInPlatform()

        self.assertEqual(
            platform._absolute_media_url('/media/social_post_uploads/post.jpg'),
            'https://ida.example.com/media/social_post_uploads/post.jpg',
        )

    def test_fetch_media_bytes_reads_local_media_without_http_request(self):
        default_storage.save('social_post_uploads/post.jpg', ContentFile(b'image-bytes'))
        platform = LinkedInPlatform()

        with patch('apps.social_accounts.platforms.linkedin.requests.get') as get:
            content, content_type = platform._fetch_media_bytes('/media/social_post_uploads/post.jpg')

        self.assertEqual(content, b'image-bytes')
        self.assertEqual(content_type, 'image/jpeg')
        get.assert_not_called()

    @patch('apps.social_accounts.platforms.linkedin.requests.put')
    @patch('apps.social_accounts.platforms.linkedin.requests.post')
    def test_upload_image_asset_uploads_local_media_to_linkedin(self, post, put):
        default_storage.save('social_post_uploads/post.png', ContentFile(b'image-bytes'))
        post.return_value = Mock(
            status_code=200,
            json=lambda: {
                'value': {
                    'uploadUrl': 'https://upload.linkedin.example',
                    'image': 'urn:li:image:abc123',
                },
            },
        )
        put.return_value = Mock(status_code=201, text='')
        platform = LinkedInPlatform()

        media = platform._upload_image_asset(
            'urn:li:person:123',
            '/media/social_post_uploads/post.png',
        )

        self.assertEqual(media, 'urn:li:image:abc123')
        self.assertEqual(post.call_args.args[0], 'https://api.linkedin.com/rest/images?action=initializeUpload')
        put.assert_called_once()
        self.assertEqual(put.call_args.kwargs['data'], b'image-bytes')
        self.assertEqual(put.call_args.kwargs['headers']['Content-Type'], 'image/png')
        self.assertIn('Authorization', put.call_args.kwargs['headers'])

    @patch.object(LinkedInPlatform, '_upload_image_asset', return_value='urn:li:image:abc123')
    @patch('apps.social_accounts.platforms.linkedin.requests.post')
    def test_publish_post_uses_rest_posts_with_image_content(self, post, upload_image):
        account = SocialAccount(
            platform='linkedin',
            account_id='person123',
            account_name='IDA',
            access_token='token',
        )
        post.return_value = Mock(
            status_code=201,
            headers={'x-restli-id': 'urn:li:ugcPost:456'},
            json=lambda: {},
        )
        platform = LinkedInPlatform(account)

        result = platform.publish_post('Hello LinkedIn', media_urls=['/media/social_post_uploads/post.png'])

        self.assertEqual(result['post_id'], 'urn:li:ugcPost:456')
        self.assertEqual(post.call_args.args[0], 'https://api.linkedin.com/rest/posts')
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['content']['media']['id'], 'urn:li:image:abc123')
        self.assertEqual(payload['commentary'], 'Hello LinkedIn')
        upload_image.assert_called_once_with('urn:li:person:person123', '/media/social_post_uploads/post.png')
