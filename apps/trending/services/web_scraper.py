import logging
import re
from datetime import datetime, timezone

import httpx

from ..models import ContentSource, FeedItem

logger = logging.getLogger(__name__)


class WebScraper:
    def collect(self, source: ContentSource) -> int:
        config = source.config_json or {}
        logger.info("Scraping URL: %s (%s)", source.name, source.url)

        try:
            resp = httpx.get(source.url, timeout=30.0, follow_redirects=True, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; IDA Trending Bot/1.0)',
            })
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.error("Web scrape failed for %s: %s", source.url, e)
            return 0

        title_pattern = config.get('title_pattern', '<title>(.*?)</title>')
        link_pattern = config.get('link_pattern', '<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>')
        content_pattern = config.get('content_pattern', '<article[^>]*>(.*?)</article>')

        titles = re.findall(title_pattern, html, re.IGNORECASE | re.DOTALL)
        article_matches = re.findall(content_pattern, html, re.IGNORECASE | re.DOTALL)

        created = 0
        for i, article_html in enumerate(article_matches[:config.get('max_items', 30)]):
            title = titles[i] if i < len(titles) else f"Article from {source.name} #{i + 1}"
            title = re.sub(r'<[^>]+>', '', title).strip()

            clean = re.sub(r'<[^>]+>', ' ', article_html)
            clean = re.sub(r'\s+', ' ', clean).strip()

            if not clean or len(clean) < 50:
                continue

            url = f"{source.url}#item-{i}"

            if FeedItem.objects.filter(url=url).exists():
                continue

            FeedItem.objects.create(
                source=source,
                title=title[:500],
                url=url,
                content_raw=clean,
                published_at=datetime.now(timezone.utc),
            )
            created += 1

        logger.info("Web scraper created %d items from %s", created, source.name)
        return created
