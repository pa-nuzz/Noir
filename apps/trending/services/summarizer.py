import logging
import re

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
            sentences = re.split(r'[.!?]\s*', text)
            sentences = [s.strip() for s in sentences if s.strip()]
            item.ai_summary = '. '.join(sentences[:3])
            return item

        system_prompt = (
            "You are a concise news summarizer. Given a news article, produce exactly 2-3 "
            "complete sentences that capture the core news value (who, what, why, when).\n\n"
            "Rules:\n"
            "- Output exactly 2-3 sentences, 30-50 words total, no more\n"
            "- Start fresh — do NOT repeat the article's opening phrase verbatim\n"
            "- Be specific: include numbers, names, and key facts\n"
            '- Do NOT use "TL;DR", "In today\'s world", or filler phrases\n'
            '- End with a complete sentence (no trailing "...")'
        )
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
            # Fall back to generic LLM (LLM_API_KEY) when DeepSeek fails
            try:
                from apps.content_studio.llm.llm_service import _call_llm
                result = _call_llm(system_prompt, user_prompt)
                if result['success'] and result['content']:
                    item.ai_summary = result['content']
                    return item
            except Exception:
                pass
            sentences = re.split(r'[.!?]\s*', text)
            sentences = [s.strip() for s in sentences if s.strip()]
            item.ai_summary = '. '.join(sentences[:3])

        return item
