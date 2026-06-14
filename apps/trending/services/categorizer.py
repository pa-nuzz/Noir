import json
import logging

from apps.intelligence.services.deepseek_client import get_deepseek_client

from ..models import FeedItem, Topic

logger = logging.getLogger(__name__)


class Categorizer:
    def categorize(self, item: FeedItem) -> FeedItem:
        text = (item.title + ' ' + (item.content_cleaned or item.content_raw or ''))[:3000]

        if not text:
            return item

        client = get_deepseek_client()
        topic_names = list(Topic.objects.filter(is_active=True).values_list('name', flat=True))

        if not topic_names:
            return item

        if client.is_configured():
            system_prompt = "You are a content categorizer. Given a list of topics, return a JSON array of the most relevant topic names (max 2) that match the content. Only use topics from the provided list."
            user_prompt = f"Available topics: {', '.join(topic_names)}\n\nContent:\n{text[:2000]}"

            result = client.chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.1,
                max_tokens=100,
                response_format='json',
            )

            if result:
                try:
                    categories = json.loads(result)
                    if isinstance(categories, list):
                        valid = [c for c in categories if c in topic_names]
                        if valid:
                            item.ai_categories = valid
                            topic = Topic.objects.filter(name=valid[0]).first()
                            if topic:
                                item.topic = topic
                            return item
                except (json.JSONDecodeError, TypeError):
                    logger.warning("Failed to parse DeepSeek categories: %s", result)

        text_lower = text.lower()
        matched = []
        for topic in Topic.objects.filter(is_active=True):
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
