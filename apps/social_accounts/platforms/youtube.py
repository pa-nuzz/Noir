import logging

import requests

from .base import BaseSocialPlatform

logger = logging.getLogger(__name__)

YOUTUBE_API = 'https://www.googleapis.com/youtube/v3'


class YouTubePlatform(BaseSocialPlatform):
    def validate_token(self):
        resp = requests.get(f"{YOUTUBE_API}/channels", params={
            'part': 'id',
            'mine': 'true',
        }, headers=self._headers())
        return resp.status_code == 200

    def _headers(self):
        return {'Authorization': f'Bearer {self.access_token}', 'Content-Type': 'application/json'}

    def get_profile(self):
        resp = requests.get(f"{YOUTUBE_API}/channels", headers=self._headers(), params={
            'part': 'snippet',
            'mine': 'true',
        })
        if resp.status_code == 200:
            items = resp.json().get('items', [])
            if items:
                ch = items[0]
                snippet = ch.get('snippet', {})
                return {
                    'account_id': ch.get('id', ''),
                    'account_name': snippet.get('title', ''),
                    'avatar_url': snippet.get('thumbnails', {}).get('default', {}).get('url', ''),
                    'profile_url': f"https://youtube.com/channel/{ch.get('id', '')}",
                }
        return None

    def publish_post(self, content, media_urls=None, link_url=None, scheduled_at=None):
        if not media_urls:
            logger.error("YouTube requires a video URL")
            return None

        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseDownload
        import io

        body = {
            'snippet': {
                'title': (content or 'Video')[:100],
                'description': content or '',
            },
            'status': {
                'privacyStatus': 'private' if scheduled_at else 'public',
                'publishAt': scheduled_at.isoformat() + 'Z' if scheduled_at else None,
            },
        }

        headers = self._headers()
        headers['Content-Type'] = 'application/json'
        headers['X-Upload-Content-Type'] = 'video/*'

        resp = requests.post(
            f"{YOUTUBE_API}/videos?part=snippet,status&uploadType=resumable",
            headers=headers, json=body,
        )
        if resp.status_code != 200:
            logger.error(f"YouTube video init failed: {resp.text}")
            return None

        upload_url = resp.headers.get('Location', '')
        if upload_url:
            with requests.get(media_urls[0], stream=True) as video:
                upload = requests.put(upload_url, data=video.content, headers={
                    'Content-Type': 'video/*',
                    'Content-Length': str(len(video.content)),
                })
                if upload.status_code in (200, 201):
                    video_id = upload.json().get('id', '')
                    return {'post_id': video_id, 'url': f"https://youtu.be/{video_id}"}
        return None

    def schedule_post(self, content, scheduled_at, media_urls=None, link_url=None):
        return self.publish_post(content, media_urls, link_url, scheduled_at)

    def delete_post(self, post_id):
        resp = requests.delete(f"{YOUTUBE_API}/videos", params={'id': post_id}, headers=self._headers())
        return resp.status_code == 204

    def get_post_analytics(self, post_id):
        resp = requests.get(f"{YOUTUBE_API}/videos", headers=self._headers(), params={
            'part': 'statistics',
            'id': post_id,
        })
        if resp.status_code == 200:
            items = resp.json().get('items', [])
            return items[0].get('statistics', {}) if items else {}
        return {}

    def get_account_analytics(self, since=None, until=None):
        resp = requests.get(f"{YOUTUBE_API}/channels", headers=self._headers(), params={
            'part': 'statistics',
            'mine': 'true',
        })
        if resp.status_code == 200:
            items = resp.json().get('items', [])
            return items[0].get('statistics', {}) if items else {}
        return {}

    def refresh_token(self):
        return None
