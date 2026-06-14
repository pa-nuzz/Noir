import logging
import re
from datetime import timezone

from ..models import FeedItem, Topic

logger = logging.getLogger(__name__)


class ContentCleaner:
    def clean(self, item: FeedItem) -> FeedItem:
        raw = item.content_raw or ''

        cleaned = re.sub(r'<[^>]+>', ' ', raw)
        cleaned = re.sub(r'&[a-zA-Z]+;', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        lines = cleaned.split('\n')
        cleaned = '\n'.join(l for l in lines if l.strip())

        item.content_cleaned = cleaned[:10000]

        if not item.published_at:
            from django.utils import timezone as tz
            item.published_at = tz.now()

        if item.language == 'en' and item.published_at and not item.published_at.tzinfo:
            item.published_at = item.published_at.replace(tzinfo=timezone.utc)

        return item

    def detect_duplicate(self, item: FeedItem) -> bool:
        threshold = 0.85
        title = item.title.lower().strip()
        if not title:
            return False

        existing = FeedItem.objects.filter(
            is_duplicate=False,
        ).exclude(pk=item.pk)

        for other in existing:
            other_title = other.title.lower().strip()
            words_a = set(title.split())
            words_b = set(other_title.split())
            if not words_a or not words_b:
                continue
            intersection = words_a & words_b
            union = words_a | words_b
            similarity = len(intersection) / len(union)
            if similarity >= threshold:
                logger.info("Duplicate detected: %s matches %s (score=%.2f)", item.title[:60], other.title[:60], similarity)
                return True

        return False

    def classify_topic(self, item: FeedItem) -> FeedItem:
        if not item.content_cleaned:
            return item

        text = (item.title + ' ' + item.content_cleaned).lower()
        topics = Topic.objects.filter(is_active=True)

        best_topic = None
        best_score = 0

        for topic in topics:
            keywords = topic.keywords or []
            score = 0
            for kw in keywords:
                kw_lower = kw.lower()
                count = text.count(kw_lower)
                score += count
            if score > best_score:
                best_score = score
                best_topic = topic

        if best_topic and best_score > 0:
            item.topic = best_topic

        return item
