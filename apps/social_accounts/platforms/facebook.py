import logging

import requests

from .base import BaseSocialPlatform

logger = logging.getLogger(__name__)

GRAPH_API = 'https://graph.facebook.com/v18.0'


class FacebookPlatform(BaseSocialPlatform):
    def validate_token(self):
        resp = requests.get(f"{GRAPH_API}/me", params={'access_token': self.access_token})
        return resp.status_code == 200

    def get_profile(self):
        resp = requests.get(f"{GRAPH_API}/me", params={
            'access_token': self.access_token,
            'fields': 'id,name,picture,link',
        })
        if resp.status_code == 200:
            data = resp.json()
            return {
                'account_id': data.get('id'),
                'account_name': data.get('name'),
                'avatar_url': data.get('picture', {}).get('data', {}).get('url', ''),
                'profile_url': data.get('link', ''),
            }
        return None

    def get_pages(self):
        resp = requests.get(f"{GRAPH_API}/me/accounts", params={
            'access_token': self.access_token,
            'fields': 'id,name,picture,access_token,link',
        })
        if resp.status_code == 200:
            return resp.json().get('data', [])
        return []

    def publish_post(self, content, media_urls=None, link_url=None, scheduled_at=None):
        if self.account and self.account.platform == 'instagram':
            return self._publish_instagram(content, media_urls)
        return self._publish_facebook(content, media_urls, link_url, scheduled_at)

    def _publish_facebook(self, content, media_urls=None, link_url=None, scheduled_at=None):
        import json
        
        # If both media and a link are provided, Facebook doesn't allow both.
        # We append the link to the message and remove it from the dedicated link parameter.
        if link_url and media_urls:
            content = f"{content}\n\n{link_url}" if content else link_url
            link_url = None

        data = {
            'access_token': self.access_token,
            'message': content,
        }
        if link_url:
            data['link'] = link_url

        page_id = self.account.account_id if self.account else 'me'

        if media_urls:
            resp = self._upload_media(media_urls[0], page_id)
            if resp:
                data['attached_media'] = json.dumps([{'media_fbid': resp['id']}])

        if scheduled_at:
            data['published'] = False
            data['scheduled_publish_time'] = int(scheduled_at.timestamp())

        resp = requests.post(f"{GRAPH_API}/{page_id}/feed", data=data)
        if resp.status_code == 200:
            return {'post_id': resp.json().get('id'), 'url': f"https://facebook.com/{resp.json().get('id')}"}
        logger.error(f"Facebook publish failed: {resp.text}")
        return None

    def _publish_instagram(self, content, media_urls=None):
        if not media_urls:
            return None
        ig_user_id = self.account.account_id

        creation = requests.post(f"{GRAPH_API}/{ig_user_id}/media", data={
            'access_token': self.access_token,
            'image_url': media_urls[0],
            'caption': content,
        })
        if creation.status_code != 200:
            logger.error(f"Instagram media creation failed: {creation.text}")
            return None
        media_id = creation.json().get('id')

        publish = requests.post(f"{GRAPH_API}/{ig_user_id}/media_publish", data={
            'access_token': self.access_token,
            'creation_id': media_id,
        })
        if publish.status_code == 200:
            return {'post_id': publish.json().get('id'), 'url': f"https://instagram.com/p/{publish.json().get('id')}/"}
        logger.error(f"Instagram publish failed: {publish.text}")
        return None

    def _upload_media(self, media_url, page_id='me'):
        from django.conf import settings
        import os
        
        data = {
            'access_token': self.access_token,
            'published': False,
        }
        files = None

        if media_url.startswith('/'):
            file_path = os.path.join(settings.BASE_DIR, media_url.lstrip('/'))
            try:
                # requests handles closing the file when passed this way
                files = {'source': open(file_path, 'rb')}
            except Exception as e:
                logger.error(f"Failed to open media file {file_path}: {e}")
                return None
        else:
            data['url'] = media_url

        resp = requests.post(f"{GRAPH_API}/{page_id}/photos", data=data, files=files)
        
        # If files were opened, close them
        if files and 'source' in files and hasattr(files['source'], 'close'):
            files['source'].close()

        if resp.status_code == 200:
            return resp.json()
        logger.error(f"Facebook media upload failed: {resp.text}")
        return None

    def schedule_post(self, content, scheduled_at, media_urls=None, link_url=None):
        return self.publish_post(content, media_urls, link_url, scheduled_at)

    def delete_post(self, post_id):
        resp = requests.delete(f"{GRAPH_API}/{post_id}", params={'access_token': self.access_token})
        return resp.status_code == 200

    def get_post_analytics(self, post_id):
        resp = requests.get(f"{GRAPH_API}/{post_id}/insights", params={
            'access_token': self.access_token,
            'metric': 'impressions,reach,likes,shares,comments,clicks',
        })
        if resp.status_code == 200:
            data = resp.json().get('data', [])
            return {m['name']: m['values'][0]['value'] for m in data}
        return {}

    def get_account_analytics(self, since=None, until=None):
        page_id = self.account.account_id if self.account else 'me'
        params = {
            'access_token': self.access_token,
            'metric': 'page_impressions,page_engaged_users,page_fans',
        }
        if since:
            params['since'] = since
        if until:
            params['until'] = until
        resp = requests.get(f"{GRAPH_API}/{page_id}/insights", params=params)
        if resp.status_code == 200:
            return resp.json()
        return {}

    def refresh_token(self):
        resp = requests.get(f"{GRAPH_API}/oauth/access_token", params={
            'grant_type': 'fb_exchange_token',
            'client_id': None,
            'client_secret': None,
            'fb_exchange_token': self.access_token,
        })
        if resp.status_code == 200:
            return resp.json().get('access_token')
        return None
