import logging
from datetime import datetime, timedelta, timezone

import httpx

from ..models import ContentSource, FeedItem

logger = logging.getLogger(__name__)


class GitHubCollector:
    GITHUB_TRENDING_URL = "https://api.github.com/search/repositories"

    def collect(self, source: ContentSource) -> int:
        config = source.config_json or {}
        cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d')
        config.setdefault('query', f'pushed:>{cutoff} stars:>10')
        config.setdefault('sort', 'updated')
        config.setdefault('order', 'desc')
        config.setdefault('per_page', 30)
        query = config['query']
        sort = config['sort']
        order = config['order']
        per_page = config['per_page']

        logger.info("Fetching GitHub trending: q=%s sort=%s order=%s", query, sort, order)

        try:
            resp = httpx.get(
                self.GITHUB_TRENDING_URL,
                params={'q': query, 'sort': sort, 'order': order, 'per_page': per_page},
                timeout=30.0,
                headers={'Accept': 'application/vnd.github.v3+json'},
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error("GitHub API request failed: %s", e)
            return 0

        items = data.get('items', [])
        if not items:
            logger.warning("No items returned from GitHub API")
            return 0

        created = 0
        for item in items:
            url = item.get('html_url', '')
            if not url or FeedItem.objects.filter(url=url).exists():
                continue

            name = item.get('full_name', '')
            description = item.get('description', '') or ''
            stars = item.get('stargazers_count', 0)
            language = item.get('language', '')
            topics = item.get('topics', [])
            author = item.get('owner', {}).get('login', '')

            raw_content = f"Repository: {name}\nDescription: {description}\nLanguage: {language}\nStars: {stars}\nTopics: {', '.join(topics)}"

            published = item.get('pushed_at')
            pub_dt = None
            if published:
                try:
                    pub_dt = datetime.fromisoformat(published.replace('Z', '+00:00'))
                except Exception:
                    pub_dt = None

            FeedItem.objects.create(
                source=source,
                title=f"[{stars}★] {name}",
                url=url,
                author=author,
                content_raw=raw_content,
                published_at=pub_dt,
            )
            created += 1

        logger.info("GitHub collector created %d items", created)
        return created
