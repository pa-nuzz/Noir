import logging

from ..models import FeedItem, Topic

logger = logging.getLogger(__name__)


class Categorizer:
    _topics_cache = None

    def _get_topics(self, topics=None):
        if topics is not None:
            return topics
        if self._topics_cache is None:
            self._topics_cache = list(Topic.objects.filter(is_active=True))
        return self._topics_cache

    def categorize(self, item: FeedItem, topics=None) -> FeedItem:
        if item.ai_categories:
            return item

        text = (item.title + ' ' + (item.content_cleaned or item.content_raw or ''))[:3000]

        if not text:
            return item

        text_lower = text.lower()
        matched = []
        for topic in self._get_topics(topics):
            keywords = topic.keywords or []
            for kw in keywords:
                if kw.lower() in text_lower and topic.name not in matched:
                    matched.append(topic.name)
                    if not item.topic:
                        item.topic = topic
                    break
            if len(matched) >= 2:
                break

        item.ai_categories = matched[:2]
        return item
