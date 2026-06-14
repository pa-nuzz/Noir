import logging

import requests

from .base import BaseSocialPlatform

logger = logging.getLogger(__name__)

TWITTER_API = 'https://api.twitter.com/2'


class TwitterPlatform(BaseSocialPlatform):
    def validate_token(self):
        resp = requests.get(f"{TWITTER_API}/users/me", headers=self._headers())
        return resp.status_code == 200

    def _headers(self):
        return {'Authorization': f'Bearer {self.access_token}', 'Content-Type': 'application/json'}

    def get_profile(self):
        resp = requests.get(f"{TWITTER_API}/users/me", headers=self._headers(), params={
            'user.fields': 'id,name,username,profile_image_url,url',
        })
        if resp.status_code == 200:
            data = resp.json().get('data', {})
            return {
                'account_id': data.get('id'),
                'account_name': f"@{data.get('username', '')}",
                'avatar_url': data.get('profile_image_url', ''),
                'profile_url': f"https://x.com/{data.get('username', '')}",
            }
        return None

    def publish_post(self, content, media_urls=None, link_url=None, scheduled_at=None):
        text = content or ''
        if link_url:
            text = f"{text}\n{link_url}"
        payload = {'text': text}
        if media_urls:
            media_id = self._upload_media(media_urls[0])
            if media_id:
                payload['media'] = {'media_ids': [media_id]}

        resp = requests.post(f"{TWITTER_API}/tweets", headers=self._headers(), json=payload)
        if resp.status_code == 201:
            data = resp.json().get('data', {})
            return {'post_id': data.get('id'), 'url': f"https://x.com/user/status/{data.get('id')}"}
        logger.error(f"Twitter publish failed: {resp.text}")
        return None

    def _upload_media(self, media_url):
        resp = requests.post('https://upload.twitter.com/1.1/media/upload.json', headers={
            'Authorization': f'Bearer {self.access_token}',
        }, data={'media_url': media_url})
        if resp.status_code == 200:
            return resp.json().get('media_id_string')
        return None

    def schedule_post(self, content, scheduled_at, media_urls=None, link_url=None):
        logger.warning("Twitter API v2 does not support scheduling via API. Use platform scheduler.")
        return self.publish_post(content, media_urls, link_url)

    def delete_post(self, post_id):
        resp = requests.delete(f"{TWITTER_API}/tweets/{post_id}", headers=self._headers())
        return resp.status_code == 200

    def get_post_analytics(self, post_id):
        resp = requests.get(f"{TWITTER_API}/tweets/{post_id}", headers=self._headers(), params={
            'tweet.fields': 'public_metrics',
        })
        if resp.status_code == 200:
            metrics = resp.json().get('data', {}).get('public_metrics', {})
            return metrics
        return {}

    def get_account_analytics(self, since=None, until=None):
        user_id = self.account.account_id if self.account else 'me'
        resp = requests.get(f"{TWITTER_API}/users/{user_id}", headers=self._headers(), params={
            'user.fields': 'public_metrics',
        })
        if resp.status_code == 200:
            return resp.json().get('data', {}).get('public_metrics', {})
        return {}

    def refresh_token(self):
        return None
