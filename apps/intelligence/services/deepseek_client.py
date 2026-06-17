import logging
from typing import Optional

import httpx
from decouple import config
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

CIRCUIT_KEY = 'llm_fast:circuit_open'
CIRCUIT_TTL = 3600


class DeepSeekClient:
    """Fast LLM client with circuit breaker for high-volume tasks (trending, etc.).

    Uses DEEPSEEK_API_KEY first; if not set, warns and falls back to the generic
    LLM_API_KEY / LLM_BASE_URL / LLM_MODEL settings.
    """

    def __init__(self):
        self.api_key = (
            config('DEEPSEEK_API_KEY', default=None)
            or getattr(settings, 'DEEPSEEK_API_KEY', None)
            or ''
        )

        if self.api_key:
            self.base_url = 'https://api.deepseek.com/v1'
            self.model = 'deepseek-chat'
        else:
            logger.warning(
                "DEEPSEEK_API_KEY not set, falling back to "
                "LLM_API_KEY/LLM_BASE_URL/LLM_MODEL"
            )
            self.api_key = (
                config('LLM_API_KEY', default=None)
                or getattr(settings, 'LLM_API_KEY', None)
                or ''
            )
            self.base_url = (
                config('LLM_BASE_URL', default=None)
                or getattr(settings, 'LLM_BASE_URL', 'https://api.openai.com/v1')
            )
            self.model = (
                config('LLM_MODEL', default=None)
                or getattr(settings, 'LLM_MODEL', 'gpt-4o')
            )

        self.timeout = 10.0

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
            logger.error("LLM_API_KEY not configured")
            return ""

        if cache.get(CIRCUIT_KEY):
            logger.warning("LLM fast circuit breaker open — skipping API call")
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
            url = f"{self.base_url.rstrip('/')}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            response = httpx.post(url, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()

            cache.delete(CIRCUIT_KEY)

            result = response.json()
            choices = result.get("choices", [])
            if not choices:
                logger.warning("No choices in LLM response")
                return ""

            return choices[0].get("message", {}).get("content", "").strip()

        except httpx.HTTPStatusError as e:
            error_text = e.response.text
            logger.error(f"LLM API error ({e.response.status_code}): {error_text}")
            if e.response.status_code in (402, 429):
                cache.set(CIRCUIT_KEY, True, timeout=CIRCUIT_TTL)
                logger.warning("LLM fast circuit breaker opened for %ss", CIRCUIT_TTL)
            return ""
        except httpx.RequestError as e:
            logger.error(f"LLM request failed: {e}")
            return ""
        except Exception as e:
            logger.exception(f"Unexpected error calling LLM: {e}")
            return ""


_deepseek_client = None


def get_deepseek_client() -> DeepSeekClient:
    global _deepseek_client
    if _deepseek_client is None:
        _deepseek_client = DeepSeekClient()
    return _deepseek_client
