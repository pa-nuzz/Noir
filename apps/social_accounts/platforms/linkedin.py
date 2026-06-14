import logging

import requests

from .base import BaseSocialPlatform

logger = logging.getLogger(__name__)

LINKEDIN_API = 'https://api.linkedin.com/v2'


class LinkedInPlatform(BaseSocialPlatform):
    def validate_token(self):
        resp = requests.get(f"{LINKEDIN_API}/userinfo", headers=self._headers())
        return resp.status_code == 200

    def _headers(self):
        return {'Authorization': f'Bearer {self.access_token}'}

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
        share_content = {
            'shareCommentary': {'text': content},
            'shareMediaCategory': 'NONE',
        }
        payload = {
            'author': author,
            'lifecycleState': 'PUBLISHED',
            'specificContent': {'com.linkedin.ugc.ShareContent': share_content},
            'visibility': {'com.linkedin.ugc.MemberNetworkVisibility': 'PUBLIC'},
        }

        if media_urls:
            media_article = self._register_upload(author, media_urls[0])
            if media_article:
                share_content['shareMediaCategory'] = 'IMAGE'
                share_content['media'] = [media_article]

        if link_url and not media_urls:
            share_content['shareMediaCategory'] = 'ARTICLE'
            share_content['media'] = [{
                'status': 'READY',
                'description': {'text': content},
                'originalUrl': link_url,
            }]

        resp = requests.post(f"{LINKEDIN_API}/ugcPosts", headers=self._headers(), json=payload)
        if resp.status_code == 201:
            post_id = resp.json().get('id', '')
            return {'post_id': post_id, 'url': f"https://linkedin.com/feed/update/{post_id}"}
        logger.error(f"LinkedIn publish failed: {resp.text}")
        return None

    def _register_upload(self, author, media_url):
        resp = requests.post(f"{LINKEDIN_API}/assets", headers=self._headers(), json={
            'registerUploadRequest': {
                'recipes': ['urn:li:digitalmediaRecipe:feedshare-image'],
                'owner': author,
                'serviceRelationships': [{
                    'relationshipType': 'OWNER',
                    'identifier': 'urn:li:userGeneratedContent',
                }],
            }
        })
        if resp.status_code == 200:
            upload_url = resp.json()['value']['uploadMechanism']['com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest']['uploadUrl']
            asset = resp.json()['value']['asset']
            import requests as req
            with req.get(media_url, stream=True) as img:
                req.put(upload_url, data=img.content)
            return {'status': 'READY', 'media': asset}
        return None

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
