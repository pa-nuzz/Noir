import json
import logging

from apps.intelligence.services.deepseek_client import get_deepseek_client

from ..models import FeedItem, Topic, UserFeedInteraction, UserTopicPreference

logger = logging.getLogger(__name__)


class Personalizer:
    def personalize(self, user, feed_items) -> list:
        if not feed_items:
            return []

        prefs = list(UserTopicPreference.objects.filter(user=user).select_related('topic'))
        topic_ids = [p.topic_id for p in prefs]

        dismissed_urls = set(
            UserFeedInteraction.objects.filter(
                user=user, interaction_type='dismissed'
            ).values_list('feed_item__url', flat=True)
        )
        feed_items = [f for f in feed_items if f.url not in dismissed_urls]

        if not topic_ids:
            return sorted(feed_items, key=lambda x: x.trending_score, reverse=True)[:50]

        topic_items = sorted(
            [f for f in feed_items if f.topic_id in topic_ids],
            key=lambda x: x.trending_score, reverse=True
        )
        other_items = sorted(
            [f for f in feed_items if f.topic_id not in topic_ids],
            key=lambda x: x.trending_score, reverse=True
        )
        return (topic_items[:40] + other_items[:10])[:50]

    def _llm_rank(self, user, feed_items) -> list:
        client = get_deepseek_client()
        if not client.is_configured():
            return self.personalize(user, feed_items)

        items_text = []
        for item in feed_items[:30]:
            items_text.append({
                'id': item.id,
                'title': item.title[:200],
                'summary': (item.ai_summary or item.content_cleaned or '')[:300],
            })

        try:
            profile = user.trending_profile
            keywords = profile.inferred_keywords or []
        except Exception:
            keywords = []

        system_prompt = "You are a content personalization assistant. Rank the following content items by relevance to the user's interests. Return a JSON array of item IDs in order of relevance (most relevant first)."
        user_prompt = (
            f"User interests: {', '.join(keywords[:15])}\n\n"
            f"Candidate items:\n{json.dumps(items_text, indent=2)}"
        )

        result = client.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=500,
            response_format='json',
        )

        if result:
            try:
                ranked_ids = json.loads(result)
                if isinstance(ranked_ids, list):
                    id_map = {f.id: f for f in feed_items}
                    ranked = [id_map[i] for i in ranked_ids if i in id_map]
                    remaining = [f for f in feed_items if f not in ranked]
                    return ranked + remaining
            except (json.JSONDecodeError, TypeError):
                logger.warning("Failed to parse LLM ranking")

        return feed_items
