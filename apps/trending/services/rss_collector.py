import logging
from datetime import datetime, timezone

import feedparser

from ..models import ContentSource, FeedItem, Topic

logger = logging.getLogger(__name__)


class RSSCollector:
    def collect(self, source: ContentSource) -> int:
        logger.info("Fetching RSS feed: %s (%s)", source.name, source.url)
        try:
            feed = feedparser.parse(source.url)
        except Exception as e:
            logger.error("Failed to parse RSS feed %s: %s", source.url, e)
            return 0

        entries = feed.get('entries', [])
        if not entries:
            logger.warning("No entries in RSS feed: %s", source.name)
            return 0

        created = 0
        for entry in entries:
            title = (entry.get('title') or '').strip()
            link = (entry.get('link') or '').strip()
            if not title or not link:
                continue

            if FeedItem.objects.filter(url=link).exists():
                continue

            raw_content = entry.get('content', [{}])[0].get('value', '') if entry.get('content') else ''
            raw_content = raw_content or entry.get('summary', '') or entry.get('description', '') or ''

            published = entry.get('published_parsed') or entry.get('updated_parsed')
            pub_dt = None
            if published:
                try:
                    pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
                except Exception:
                    pub_dt = None

            author = entry.get('author', '') or ''

            FeedItem.objects.create(
                source=source,
                title=title,
                url=link,
                author=author,
                content_raw=raw_content,
                published_at=pub_dt,
            )
            created += 1

        logger.info("RSS collector created %d items from %s", created, source.name)
        return created
