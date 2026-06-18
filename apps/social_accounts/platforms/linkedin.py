import logging
import mimetypes
from urllib.parse import urljoin, urlparse

from django.conf import settings
from django.core.files.storage import default_storage
from django.urls import resolve
import requests

from .base import BaseSocialPlatform

logger = logging.getLogger(__name__)

LINKEDIN_API = 'https://api.linkedin.com/v2'
LINKEDIN_REST_API = 'https://api.linkedin.com/rest'
LINKEDIN_VERSION = getattr(settings, 'LINKEDIN_VERSION', '202605')


class LinkedInPlatform(BaseSocialPlatform):
    def validate_token(self):
        resp = requests.get(f"{LINKEDIN_API}/userinfo", headers=self._headers())
        return resp.status_code == 200

    def _headers(self):
        return {
            'Authorization': f'Bearer {self.access_token}',
            'X-Restli-Protocol-Version': '2.0.0',
            'Linkedin-Version': LINKEDIN_VERSION,
        }

    def _json_headers(self):
        headers = self._headers()
        headers['Content-Type'] = 'application/json'
        return headers

    def get_profile(self):
        resp = requests.get(f"{LINKEDIN_API}/userinfo", headers=self._headers())
        if resp.status_code == 200:
            data = resp.json()
            return {
                'account_id': data.get('sub'),
                'account_name': data.get('name', ''),
                'avatar_url': data.get('picture', ''),
                'profile_url': '',
            }
        return None

    def _get_author_urn(self):
        if self.account:
            return f"urn:li:person:{self.account.account_id}"
        resp = requests.get(f"{LINKEDIN_API}/userinfo", headers=self._headers())
        if resp.status_code == 200:
            return f"urn:li:person:{resp.json().get('sub', 'me')}"
        return 'urn:li:person:me'

    def publish_post(self, content, media_urls=None, link_url=None, scheduled_at=None):
        author = self._get_author_urn()
        
        # If we have both media and a link, append the link to the text 
        # since we can only attach media as the main content object.
        if link_url and media_urls:
            content = f"{content}\n\n{link_url}" if content else link_url

        commentary = (content or '').replace('\r\n', '\n').replace('\r', '\n').strip()
        logger.info("Publishing LinkedIn post with %s commentary characters and %s media item(s).", len(commentary), len(media_urls or []))
        payload = {
            'author': author,
            'commentary': commentary,
            'visibility': 'PUBLIC',
            'distribution': {
                'feedDistribution': 'MAIN_FEED',
                'targetEntities': [],
                'thirdPartyDistributionChannels': [],
            },
            'lifecycleState': 'PUBLISHED',
            'isReshareDisabledByAuthor': False,
        }

        if media_urls:
            image_urn = self._upload_image_asset(author, media_urls[0])
            payload['content'] = {
                'media': {
                    'id': image_urn,
                },
            }

        if link_url and not media_urls:
            payload['content'] = {
                'article': {
                    'source': link_url,
                    'title': link_url,
                    'description': commentary[:200],
                },
            }

        resp = requests.post(f"{LINKEDIN_REST_API}/posts", headers=self._json_headers(), json=payload)
        if resp.status_code == 201:
            post_id = resp.headers.get('x-restli-id', '')
            if not post_id:
                try:
                    post_id = resp.json().get('id', '')
                except ValueError:
                    post_id = ''
            return {'post_id': post_id, 'url': f"https://linkedin.com/feed/update/{post_id}" if post_id else ''}
        logger.error(f"LinkedIn publish failed: {resp.text}")
        return None

    def _absolute_media_url(self, media_url):
        if not media_url:
            return ''
        parsed = urlparse(media_url)
        if parsed.scheme and parsed.netloc:
            return media_url
        base_url = getattr(settings, 'PUBLIC_BASE_URL', '').rstrip('/') or 'http://127.0.0.1:8000'
        return urljoin(base_url + '/', media_url.lstrip('/'))

    def _media_from_default_storage(self, media_url):
        parsed = urlparse(media_url)
        path = parsed.path or media_url
        media_prefix = getattr(settings, 'MEDIA_URL', '/media/')
        if not path.startswith(media_prefix):
            return None

        storage_path = path[len(media_prefix):].lstrip('/')
        if not storage_path or not default_storage.exists(storage_path):
            return None

        with default_storage.open(storage_path, 'rb') as media_file:
            content = media_file.read()
        content_type, _encoding = mimetypes.guess_type(storage_path)
        return content, content_type or 'application/octet-stream'

    def _media_from_asset_proxy(self, media_url):
        parsed = urlparse(media_url)
        path = parsed.path or media_url
        try:
            match = resolve(path)
        except Exception:
            return None

        if match.url_name != 'serve_asset' or match.namespace != 'media_assets':
            return None

        asset_id = match.kwargs.get('asset_id')
        file_type = match.kwargs.get('file_type', 'original')
        if not asset_id or not self.account:
            return None

        from apps.media_assets.models import MediaAsset
        from apps.media_assets.services import MediaService

        asset = MediaAsset.objects.filter(id=asset_id, user=self.account.user).first()
        if not asset:
            return None

        storage_path = asset.thumbnail_path if file_type == 'thumbnail' else asset.storage_path
        if not storage_path:
            return None

        service = MediaService(self.account.user)
        with service.storage.open(storage_path) as media_file:
            content = media_file.read()
        content_type = 'image/webp' if file_type == 'thumbnail' else (asset.mime_type or mimetypes.guess_type(asset.original_filename)[0])
        return content, content_type or 'application/octet-stream'

    def _fetch_media_bytes(self, media_url):
        local_media = self._media_from_default_storage(media_url)
        if local_media:
            return local_media

        asset_media = self._media_from_asset_proxy(media_url)
        if asset_media:
            return asset_media

        absolute_url = self._absolute_media_url(media_url)
        try:
            resp = requests.get(absolute_url, timeout=30)
        except requests.RequestException as exc:
            logger.exception("LinkedIn media download failed for %s", absolute_url)
            raise RuntimeError(f"LinkedIn media download failed: {exc}") from exc

        if resp.status_code >= 400:
            logger.error("LinkedIn media download failed for %s: HTTP %s", absolute_url, resp.status_code)
            raise RuntimeError(f"LinkedIn media download failed with HTTP {resp.status_code}.")

        content_type = resp.headers.get('Content-Type', '').split(';')[0] or mimetypes.guess_type(absolute_url)[0]
        return resp.content, content_type or 'application/octet-stream'

    def _upload_image_asset(self, author, media_url):
        media_content, content_type = self._fetch_media_bytes(media_url)
        if not content_type.startswith('image/'):
            raise RuntimeError('LinkedIn image posts require an image attachment. Video support is not enabled yet.')

        resp = requests.post(f"{LINKEDIN_REST_API}/images?action=initializeUpload", headers=self._json_headers(), json={
            'initializeUploadRequest': {
                'owner': author,
            }
        })
        if resp.status_code != 200:
            logger.error("LinkedIn image upload initialization failed: %s", resp.text)
            raise RuntimeError(f"LinkedIn image upload initialization failed with HTTP {resp.status_code}.")

        data = resp.json()
        value = data.get('value', {})
        upload_url = value.get('uploadUrl')
        image_urn = value.get('image')
        if not upload_url or not image_urn:
            logger.error("LinkedIn image initialization response missing upload data: %s", data)
            raise RuntimeError('LinkedIn image initialization response was missing upload data.')

        upload_headers = self._headers()
        upload_headers['Content-Type'] = content_type
        upload_resp = requests.put(upload_url, data=media_content, headers=upload_headers, timeout=60)
        if upload_resp.status_code not in (200, 201, 202):
            logger.error("LinkedIn media upload failed: %s", upload_resp.text)
            raise RuntimeError(f"LinkedIn media upload failed with HTTP {upload_resp.status_code}.")

        return image_urn

    def schedule_post(self, content, scheduled_at, media_urls=None, link_url=None):
        return self.publish_post(content, media_urls, link_url)

    def delete_post(self, post_id):
        resp = requests.delete(f"{LINKEDIN_API}/ugcPosts/{post_id}", headers=self._headers())
        return resp.status_code == 200

    def get_post_analytics(self, post_id):
        urn = f"urn:li:share:{post_id.split(':')[-1] if ':' in post_id else post_id}"
        resp = requests.get(
            f"{LINKEDIN_API}/organizationalEntityShareStatistics?q=owners&owners={urn}",
            headers=self._headers(),
        )
        if resp.status_code == 200:
            elements = resp.json().get('elements', [])
            if elements:
                stats = elements[0].get('totalShareStatistics', {})
                return {
                    'impressions': stats.get('impressionCount', 0),
                    'clicks': stats.get('clickCount', 0),
                    'likes': stats.get('likeCount', 0),
                    'comments': stats.get('commentCount', 0),
                    'shares': stats.get('shareCount', 0),
                    'engagement_rate': round(
                        (stats.get('likeCount', 0) + stats.get('commentCount', 0) + stats.get('shareCount', 0))
                        / max(stats.get('impressionCount', 1), 1) * 100, 2
                    ),
                }
        return {}

    def get_account_analytics(self, since=None, until=None):
        author = self._get_author_urn()
        params = {'q': 'owners', 'owners': [author]}
        if since:
            params['timeIntervals.timeRange.start'] = int(since.timestamp() * 1000) if hasattr(since, 'timestamp') else since
        if until:
            params['timeIntervals.timeRange.end'] = int(until.timestamp() * 1000) if hasattr(until, 'timestamp') else until

        resp = requests.get(
            f"{LINKEDIN_API}/organizationalEntityShareStatistics",
            headers=self._headers(), params=params,
        )
        if resp.status_code == 200:
            elements = resp.json().get('elements', [])
            total = {'impressions': 0, 'clicks': 0, 'likes': 0, 'comments': 0, 'shares': 0}
            for el in elements:
                stats = el.get('totalShareStatistics', {})
                total['impressions'] += stats.get('impressionCount', 0)
                total['clicks'] += stats.get('clickCount', 0)
                total['likes'] += stats.get('likeCount', 0)
                total['comments'] += stats.get('commentCount', 0)
                total['shares'] += stats.get('shareCount', 0)
            total['engagement_rate'] = round(
                (total['likes'] + total['comments'] + total['shares'])
                / max(total['impressions'], 1) * 100, 2
            )
            return total
        return {}

    def refresh_token(self):
        return None
