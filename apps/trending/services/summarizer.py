import logging

from apps.intelligence.services.deepseek_client import get_deepseek_client

from ..models import FeedItem

logger = logging.getLogger(__name__)


class Summarizer:
    def summarize(self, item: FeedItem) -> FeedItem:
        text = item.content_cleaned or item.content_raw or ''
        text = text[:4000]

        if not text:
            return item

        client = get_deepseek_client()
        if not client.is_configured():
            words = text.split()
            item.ai_summary = ' '.join(words[:60]) + ('...' if len(words) > 60 else '')
            return item

        system_prompt = "You are a content summarizer. Summarize the following article in 2-3 concise sentences. Focus on key takeaways."
        user_prompt = f"Title: {item.title}\n\nContent:\n{text}"

        summary = client.chat(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.2,
            max_tokens=200,
        )

        if summary:
            item.ai_summary = summary
        else:
            words = text.split()
            item.ai_summary = ' '.join(words[:60]) + ('...' if len(words) > 60 else '')

        return item
