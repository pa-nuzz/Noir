import logging

import requests

from .base import BaseSocialPlatform

logger = logging.getLogger(__name__)

TIKTOK_API = 'https://open.tiktokapis.com/v2'


class TikTokPlatform(BaseSocialPlatform):
    def validate_token(self):
        resp = requests.get(f"{TIKTOK_API}/user/info/", params={
            'fields': 'open_id',
        }, headers=self._headers())
        return resp.status_code == 200

    def _headers(self):
        return {'Authorization': f'Bearer {self.access_token}', 'Content-Type': 'application/json'}

    def get_profile(self):
        resp = requests.get(f"{TIKTOK_API}/user/info/", headers=self._headers(), params={
            'fields': 'open_id,union_id,avatar_url,display_name,profile_deep_link',
        })
        if resp.status_code == 200:
            data = resp.json().get('data', {}).get('user', {})
            return {
                'account_id': data.get('open_id', ''),
                'account_name': data.get('display_name', ''),
                'avatar_url': data.get('avatar_url', ''),
                'profile_url': data.get('profile_deep_link', ''),
            }
        return None

    def publish_post(self, content, media_urls=None, link_url=None, scheduled_at=None):
        if not media_urls:
            logger.error("TikTok requires at least one media URL")
            return None
        video_url = media_urls[0]

        init = requests.post(f"{TIKTOK_API}/video/publish/init/", headers=self._headers(), json={
            'source_info': {
                'source': 'FILE_UPLOAD',
                'video_url': video_url,
            },
            'post_info': {
                'privacy_level': 'PUBLIC_TO_EVERYONE',
                'title': content or '',
                'disable_duet': False,
                'disable_comment': False,
                'disable_stitch': False,
            },
        })
        if init.status_code != 200:
            logger.error(f"TikTok init failed: {init.text}")
            return None

        publish_id = init.json().get('data', {}).get('publish_id')
        import time
        for _ in range(30):
            status = requests.get(f"{TIKTOK_API}/video/publish/status/", headers=self._headers(), params={
                'publish_id': publish_id,
            })
            if status.status_code == 200:
                s = status.json().get('data', {}).get('status')
                if s == 'PUBLISH_COMPLETE':
                    post_id = status.json().get('data', {}).get('post_id', '')
                    return {'post_id': post_id, 'url': f"https://tiktok.com/@{self.account.account_name}/video/{post_id}"}
                elif s == 'PUBLISH_FAILED':
                    logger.error(f"TikTok publish failed: {status.text}")
                    return None
            time.sleep(2)
        return None

    def schedule_post(self, content, scheduled_at, media_urls=None, link_url=None):
        return self.publish_post(content, media_urls, link_url)

    def delete_post(self, post_id):
        resp = requests.post(f"{TIKTOK_API}/video/publish/delete/", headers=self._headers(), json={
            'post_id': post_id,
        })
        return resp.status_code == 200

    def get_post_analytics(self, post_id):
        resp = requests.get(f"{TIKTOK_API}/video/query/", headers=self._headers(), params={
            'fields': 'view_count,like_count,comment_count,share_count',
            'video_ids': [post_id],
        })
        if resp.status_code == 200:
            videos = resp.json().get('data', {}).get('videos', [])
            return videos[0] if videos else {}
        return {}

    def get_account_analytics(self, since=None, until=None):
        params = {
            'fields': 'follower_count,follower_count_delta,view_count,like_count',
        }
        if since:
            params['since'] = since
        if until:
            params['until'] = until
        resp = requests.get(f"{TIKTOK_API}/user/info/", headers=self._headers(), params=params)
        if resp.status_code == 200:
            return resp.json().get('data', {})
        return {}

    def refresh_token(self):
        return None
