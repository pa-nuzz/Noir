import logging
import httpx
from typing import Optional
from decouple import config
from django.conf import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified LLM client for any OpenAI-compatible API."""

    def __init__(self):
        self.api_key = (
            config('LLM_API_KEY', default=None)
            or getattr(settings, 'LLM_API_KEY', None)
            or os.environ.get('LLM_API_KEY')
        )
        self.base_url = (
            config('LLM_BASE_URL', default=None)
            or getattr(settings, 'LLM_BASE_URL', 'https://api.openai.com/v1')
        ).rstrip('/')
        self.model = (
            config('LLM_MODEL', default=None)
            or getattr(settings, 'LLM_MODEL', 'gpt-4o')
        )
        self.timeout = 30.0

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        response_format: Optional[str] = None
    ) -> str:
        """Generate response from an OpenAI-compatible API.

        Args:
            system_prompt: System instructions
            user_prompt: User's request
            temperature: Creativity level (0.0-1.0)
            max_tokens: Maximum output tokens
            response_format: Optional 'json' for JSON response

        Returns:
            Generated text response
        """
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
                logger.warning("No choices in LLM response")
                return ""

            content = choices[0].get("message", {}).get("content", "").strip()
            return content

        except httpx.HTTPStatusError as e:
            error_text = e.response.text
            logger.error(f"LLM API error ({e.response.status_code}): {error_text}")
            return ""
        except httpx.RequestError as e:
            logger.error(f"LLM request failed: {e}")
            return ""
        except Exception as e:
            logger.exception(f"Unexpected error calling LLM: {e}")
            return ""

    def generate_with_fallback(
        self,
        system_prompt: str,
        user_prompt: str,
        fallback_response: str,
        **kwargs
    ) -> str:
        """Generate response with automatic fallback.

        Args:
            system_prompt: System instructions
            user_prompt: User's request
            fallback_response: Response to return if generation fails
            **kwargs: Additional args passed to generate()

        Returns:
            Generated response or fallback
        """
        result = self.generate(system_prompt, user_prompt, **kwargs)
        return result if result else fallback_response


# Global instance
_llm_client = None

def get_llm_client() -> LLMClient:
    """Get or create global LLM client instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
