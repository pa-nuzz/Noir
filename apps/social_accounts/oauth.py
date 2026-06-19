import base64
import hashlib
import logging
import secrets
from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)


def _generate_code_verifier():
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode()


def _generate_code_challenge(verifier):
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode()


def _generate_state():
    return secrets.token_urlsafe(32)


class OAuth2Flow:
    def __init__(self, platform, client_id=None, client_secret=None):
        self.platform = platform
        self.client_id = client_id
        self.client_secret = client_secret
        self.config = self._get_platform_config()

    def _get_platform_config(self):
        configs = {
            'facebook': {
                'authorize_url': 'https://www.facebook.com/v18.0/dialog/oauth',
                'token_url': 'https://graph.facebook.com/v18.0/oauth/access_token',
                'scopes': ['pages_manage_posts', 'pages_read_engagement', 'pages_show_list', 'instagram_basic', 'instagram_content_publish'],
                'extra_authorize_params': {'auth_type': 'rerequest'},
                'revoke_url': 'https://graph.facebook.com/v18.0/me/permissions',
            },
            'instagram': {
                'authorize_url': 'https://api.instagram.com/oauth/authorize',
                'token_url': 'https://api.instagram.com/oauth/access_token',
                'scopes': ['instagram_basic', 'instagram_content_publish', 'pages_show_list'],
                'extra_authorize_params': {'auth_type': 'rerequest'},
            },
            'twitter': {
                'authorize_url': 'https://twitter.com/i/oauth2/authorize',
                'token_url': 'https://api.twitter.com/2/oauth2/token',
                'scopes': ['tweet.read', 'tweet.write', 'users.read', 'offline.access'],
                'extra_authorize_params': {'force_login': 'true'},
                'revoke_url': 'https://api.twitter.com/2/oauth2/revoke',
                'needs_pkce': True,
            },
            'linkedin': {
                'authorize_url': 'https://www.linkedin.com/oauth/v2/authorization',
                'token_url': 'https://www.linkedin.com/oauth/v2/accessToken',
                'scopes': ['openid', 'profile', 'email', 'w_member_social', 'offline_access'],
                'extra_authorize_params': {},
                'revoke_url': 'https://www.linkedin.com/oauth/v2/revoke',
            },
            'tiktok': {
                'authorize_url': 'https://www.tiktok.com/v2/auth/authorize/',
                'token_url': 'https://open.tiktokapis.com/v2/oauth/token/',
                'scopes': ['user.info.basic', 'video.publish', 'video.upload'],
                'extra_authorize_params': {},
            },
            'youtube': {
                'authorize_url': 'https://accounts.google.com/o/oauth2/v2/auth',
                'token_url': 'https://oauth2.googleapis.com/token',
                'scopes': ['https://www.googleapis.com/auth/youtube.upload', 'https://www.googleapis.com/auth/youtube.readonly'],
                'extra_authorize_params': {'prompt': 'consent', 'access_type': 'offline'},
                'revoke_url': 'https://oauth2.googleapis.com/revoke',
            },
        }
        return configs.get(self.platform, {})

    def _build_redirect_uri(self, request):
        platform_override = getattr(settings, f'{self.platform.upper()}_REDIRECT_URI', None)
        if platform_override:
            return platform_override
        base = getattr(settings, 'PUBLIC_BASE_URL', '')
        if base:
            return f"{base}{reverse('social_accounts:oauth_callback', args=[self.platform])}"
        return request.build_absolute_uri(reverse('social_accounts:oauth_callback', args=[self.platform]))

    def get_authorize_url(self, request, redirect_uri=None):
        if not redirect_uri:
            redirect_uri = self._build_redirect_uri(request)

        client_id = self.client_id or getattr(settings, f'{self.platform.upper()}_CLIENT_ID', '')
        if not client_id:
            client_id = getattr(settings, 'SOCIAL_OAUTH_CLIENT_IDS', {}).get(self.platform, '')

        state = _generate_state()
        request.session[f'oauth_state_{self.platform}'] = state

        params = {
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(self.config.get('scopes', [])),
            'state': state,
        }

        if self.config.get('needs_pkce'):
            verifier = _generate_code_verifier()
            request.session[f'oauth_code_verifier_{self.platform}'] = verifier
            params['code_challenge'] = _generate_code_challenge(verifier)
            params['code_challenge_method'] = 'S256'

        extra = self.config.get('extra_authorize_params', {})
        params.update(extra)
        return f"{self.config['authorize_url']}?{urlencode(params)}"

    def exchange_code(self, code, request, redirect_uri=None, state=None):
        if not redirect_uri:
            redirect_uri = self._build_redirect_uri(request)

        if state:
            expected_state = request.session.pop(f'oauth_state_{self.platform}', None)
            if not expected_state or not secrets.compare_digest(str(expected_state), str(state)):
                logger.error(f"OAuth state mismatch for {self.platform}")
                return None

        client_id = self.client_id or getattr(settings, f'{self.platform.upper()}_CLIENT_ID', '')
        client_secret = self.client_secret or getattr(settings, f'{self.platform.upper()}_CLIENT_SECRET', '')
        if not client_id:
            client_id = getattr(settings, 'SOCIAL_OAUTH_CLIENT_IDS', {}).get(self.platform, '')
            client_secret = getattr(settings, 'SOCIAL_OAUTH_CLIENT_SECRETS', {}).get(self.platform, '')

        data = {
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
        }

        if self.config.get('needs_pkce'):
            verifier = request.session.pop(f'oauth_code_verifier_{self.platform}', None)
            if verifier:
                data['code_verifier'] = verifier

        import requests
        response = requests.post(self.config['token_url'], data=data)
        if response.status_code != 200:
            logger.error(f"OAuth token exchange failed for {self.platform}: {response.text}")
            return None
        return response.json()

    def revoke_token(self, access_token):
        revoke_url = self.config.get('revoke_url')
        if not revoke_url:
            return True
        import requests
        try:
            if self.platform == 'facebook':
                resp = requests.delete(revoke_url, params={'access_token': access_token})
                return resp.status_code in (200, 201, 204)
            elif self.platform in ('youtube',):
                resp = requests.post(revoke_url, params={'token': access_token})
                return resp.status_code in (200, 201, 204)
            elif self.platform == 'twitter':
                client_id = self.client_id or getattr(settings, f'{self.platform.upper()}_CLIENT_ID', '')
                if not client_id:
                    client_id = getattr(settings, 'SOCIAL_OAUTH_CLIENT_IDS', {}).get(self.platform, '')
                resp = requests.post(revoke_url, data={
                    'token': access_token,
                    'client_id': client_id,
                    'token_type_hint': 'access_token',
                })
                return resp.status_code in (200, 201, 204)
            elif self.platform == 'linkedin':
                client_id = self.client_id or getattr(settings, f'{self.platform.upper()}_CLIENT_ID', '')
                client_secret = self.client_secret or getattr(settings, f'{self.platform.upper()}_CLIENT_SECRET', '')
                if not client_id:
                    client_id = getattr(settings, 'SOCIAL_OAUTH_CLIENT_IDS', {}).get(self.platform, '')
                    client_secret = getattr(settings, 'SOCIAL_OAUTH_CLIENT_SECRETS', {}).get(self.platform, '')
                resp = requests.post(revoke_url, data={
                    'token': access_token,
                    'client_id': client_id,
                    'client_secret': client_secret,
                })
                return resp.status_code in (200, 201, 204)
            return True
        except Exception as e:
            logger.warning(f"Token revocation failed for {self.platform}: {e}")
            return False
