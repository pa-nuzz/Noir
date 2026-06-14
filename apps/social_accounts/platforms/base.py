import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class BaseSocialPlatform:
    def __init__(self, account=None):
        self.account = account
        self.access_token = account.access_token if account else None

    def validate_token(self):
        raise NotImplementedError

    def get_profile(self):
        raise NotImplementedError

    def publish_post(self, content, media_urls=None, link_url=None, scheduled_at=None):
        raise NotImplementedError

    def schedule_post(self, content, scheduled_at, media_urls=None, link_url=None):
        raise NotImplementedError

    def delete_post(self, post_id):
        raise NotImplementedError

    def get_post_analytics(self, post_id):
        raise NotImplementedError

    def get_account_analytics(self, since=None, until=None):
        raise NotImplementedError

    def refresh_token(self):
        raise NotImplementedError

    def _format_content(self, content, hashtags=None):
        text = content or ''
        if hashtags:
            tags_text = ' '.join([f"#{t.strip('# ')}" for t in hashtags])
            text = f"{text}\n\n{tags_text}" if text else tags_text
        return text.strip()
