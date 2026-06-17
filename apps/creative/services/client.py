import logging
from typing import Optional

import httpx
from decouple import config
from django.conf import settings

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self):
        self.api_key = (
            config('LLM_API_KEY', default=None)
            or getattr(settings, 'LLM_API_KEY', None)
        )
        self.base_url = (
            config('LLM_BASE_URL', default=None)
            or getattr(settings, 'LLM_BASE_URL', 'https://api.openai.com/v1')
        ).rstrip('/')
        self.model = (
            config('LLM_MODEL', default=None)
            or getattr(settings, 'LLM_MODEL', 'gpt-4o')
        )
        self.timeout = 180.0

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.8,
        max_tokens: int = 2048,
        response_format: Optional[str] = None,
    ) -> str:
        if not self.api_key:
            logger.error("LLM_API_KEY not configured")
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

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(2):
            try:
                # Using a Client context manager and HTTP/1.1 to avoid some HTTP/2 chunking issues
                timeout_config = httpx.Timeout(self.timeout, connect=10.0)
                with httpx.Client(timeout=timeout_config, http2=False) as client:
                    response = client.post(url, json=payload, headers=headers)
                    response.raise_for_status()

                result = response.json()
                choices = result.get("choices", [])
                if not choices:
                    logger.warning("No choices in LLM response")
                    return ""

                return choices[0].get("message", {}).get("content", "").strip()

            except httpx.HTTPStatusError as e:
                error_text = e.response.text
                logger.error(f"LLM API error ({e.response.status_code}): {error_text}")
                return ""
            except httpx.RequestError as e:
                logger.error(f"LLM request failed on attempt {attempt + 1}: {e}")
                if attempt == 1:
                    return ""
            except Exception as e:
                logger.exception(f"Unexpected error calling LLM: {e}")
                return ""


_llm_client = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
