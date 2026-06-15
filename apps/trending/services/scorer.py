import logging
import math
from datetime import datetime, timezone

from ..models import ContentSource, FeedItem

logger = logging.getLogger(__name__)


class Scorer:
    FRESHNESS_HOURS = 72
    SOURCE_AUTHORITY = {
        'rss': 1.0,
        'api': 1.2,
        'web': 0.8,
    }

    def score(self, item: FeedItem) -> float:
        score = 0.0

        if item.published_at:
            now = datetime.now(timezone.utc)
            if item.published_at.tzinfo is None:
                pub = item.published_at.replace(tzinfo=timezone.utc)
            else:
                pub = item.published_at
            age_hours = (now - pub).total_seconds() / 3600
            freshness = max(0, 1 - (age_hours / self.FRESHNESS_HOURS))
            score += freshness * 40

        if item.source:
            authority = self.SOURCE_AUTHORITY.get(item.source.source_type, 0.5)
            score += authority * 20

        if item.topic:
            topic_popularity = min(item.topic.subscriber_count / 100, 1)
            score += topic_popularity * 15

        content_len = len(item.content_cleaned or item.content_raw or '')
        if content_len > 200:
            score += 10
        elif content_len > 50:
            score += 5

        duplicate_count = FeedItem.objects.filter(
            is_duplicate=False,
            topic=item.topic,
        ).count()
        if duplicate_count > 0:
            engagement = min(duplicate_count / 100, 1)
            score += engagement * 15

        return round(score, 2)
