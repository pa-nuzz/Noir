import logging
import os
from typing import Optional

import httpx
from decouple import config
from django.conf import settings

logger = logging.getLogger(__name__)


class DeepSeekClient:
    """DeepSeek LLM client for trending topics summarization, categorization, and personalization."""

    def __init__(self):
        self.api_key = (
            config('DEEPSEEK_API_KEY', default=None)
            or getattr(settings, 'DEEPSEEK_API_KEY', None)
            or os.environ.get('DEEPSEEK_API_KEY')
        )
        self.base_url = 'https://api.deepseek.com/v1'
        self.model = 'deepseek-chat'
        self.timeout = 30.0

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        response_format: Optional[str] = None,
    ) -> str:
        if not self.api_key:
            logger.error("DEEPSEEK_API_KEY not configured")
            return ""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format == 'json':
            payload["response_format"] = {"type": "json_object"}

        try:
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            response = httpx.post(url, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()

            result = response.json()
            choices = result.get("choices", [])
            if not choices:
                logger.warning("No choices in DeepSeek response")
                return ""

            return choices[0].get("message", {}).get("content", "").strip()

        except httpx.HTTPStatusError as e:
            error_text = e.response.text
            logger.error(f"DeepSeek API error ({e.response.status_code}): {error_text}")
            return ""
        except httpx.RequestError as e:
            logger.error(f"DeepSeek request failed: {e}")
            return ""
        except Exception as e:
            logger.exception(f"Unexpected error calling DeepSeek: {e}")
            return ""


_deepseek_client = None


def get_deepseek_client() -> DeepSeekClient:
    global _deepseek_client
    if _deepseek_client is None:
        _deepseek_client = DeepSeekClient()
    return _deepseek_client
