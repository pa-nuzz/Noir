import logging
import time
import httpx
import os
from urllib.parse import urljoin
from typing import Optional
from decouple import config
from django.conf import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified LLM client with Gemini-native and OpenAI-compatible support."""

    def __init__(self):
        # API Key — prefer Gemini if configured, else fall back to OpenAI
        self.api_key = (
            config('GEMINI_API_KEY', default=None)
            or getattr(settings, 'GEMINI_API_KEY', None)
            or os.environ.get('GEMINI_API_KEY')
            or config('LLM_API_KEY', default=None)
            or getattr(settings, 'LLM_API_KEY', None)
            or os.environ.get('LLM_API_KEY')
        )

        # Base URL — Gemini or OpenAI
        self.base_url = (
            config('GEMINI_BASE_URL', default=None)
            or getattr(settings, 'GEMINI_BASE_URL', 'https://generativelanguage.googleapis.com/v1beta')
            or config('LLM_BASE_URL', default=None)
            or getattr(settings, 'LLM_BASE_URL', 'https://api.openai.com/v1')
        ).rstrip('/')

        # Model — default to Gemini if using Gemini endpoint, else GPT-4o
        self.model = (
            config('GEMINI_MODEL', default=None)
            or getattr(settings, 'GEMINI_MODEL', 'gemini-1.5-flash')
            or getattr(settings, 'LLM_MODEL', default=None)
            or getattr(settings, 'LLM_MODEL', 'gpt-4o')
        )

        self.timeout = 30.0
        self.max_retries = 3

    def _uses_gemini_native_api(self) -> bool:
        """Check if we're using Google's Gemini native endpoint."""
        base = self.base_url.lower()
        return 'generativelanguage.googleapis.com' in base and '/openai' not in base

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        response_format: Optional[str] = None,
    ) -> str:
        """Generate a response from the configured LLM provider."""
        if not self.api_key:
            logger.error("LLM_API_KEY or GEMINI_API_KEY is not configured")
            return ""

        if self._uses_gemini_native_api():
            return self._generate_gemini_native(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )

        # Default: OpenAI-compatible API
        return self._generate_openai_compatible(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

    def _generate_gemini_native(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        response_format: Optional[str] = None,
    ) -> str:
        """Generate via Google's native Gemini generateContent endpoint."""
        content = [
            {"role": "user", "parts": [{"text": user_prompt}]},
            {"role": "model", "parts": [{"text": system_prompt}]},
        ]
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        headers = {
            "Content-Type": "application/json",
        }
        payload = {
            "contents": content,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if response_format == 'json':
            payload["generationConfig"]["responseMimeType"] = "application/json"

        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = httpx.post(url, json=payload, timeout=self.timeout)
                response.raise_for_status()
                result = response.json()
                candidates = result.get("candidates", [])

                if not candidates:
                    logger.warning("No candidates in Gemini response")
                    return ""

                parts = candidates[0].get("content", {}).get("parts", [])
                if not parts:
                    logger.warning("No parts in candidate content")
                    return ""

                return parts[0].get("text", "").strip()

            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429, 500, 502, 503) and attempt < self.max_retries - 1:
                    wait = 2 ** attempt + 1
                    logger.warning("Gemini API error (%s), retrying in %ss (attempt %s)", e.response.status_code, wait, attempt + 1)
                    time.sleep(wait)
                    last_error = e
                    continue
                error_text = e.response.text
                logger.error("Gemini API error (%s): %s", e.response.status_code, error_text)
                return ""
            except httpx.RequestError as e:
                if attempt < self.max_retries - 1:
                    wait = 2 ** attempt + 1
                    logger.warning("Gemini request failed, retrying in %ss (attempt %s): %s", wait, attempt + 1, e)
                    time.sleep(wait)
                    last_error = e
                    continue
                logger.error("Gemini request failed after %s attempts: %s", self.max_retries, e)
                return ""
            except Exception as e:
                logger.exception("Unexpected error calling Gemini: %s", e)
                return ""
        return ""

    def _generate_openai_compatible(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        response_format: Optional[str] = None,
    ) -> str:
        """Generate via an OpenAI-compatible /chat/completions endpoint."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format == 'json':
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = urljoin(f"{self.base_url}/", "chat/completions")

        for attempt in range(self.max_retries):
            try:
                response = httpx.post(url, json=payload, headers=headers, timeout=self.timeout)
                response.raise_for_status()
                result = response.json()
                choices = result.get("choices", [])
                if not choices:
                    logger.warning("No choices in LLM response")
                    return ""
                return choices[0].get("message", {}).get("content", "").strip()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (429, 500, 502, 503) and attempt < self.max_retries - 1:
                    wait = 2 ** attempt + 1
                    logger.warning("LLM API error (%s), retrying in %ss (attempt %s)", exc.response.status_code, wait, attempt + 1)
                    time.sleep(wait)
                    continue
                logger.error("LLM API error (%s): %s", exc.response.status_code, exc.response.text)
                return ""
            except httpx.RequestError as exc:
                if attempt < self.max_retries - 1:
                    wait = 2 ** attempt + 1
                    logger.warning("LLM request failed, retrying in %ss (attempt %s): %s", wait, attempt + 1, exc)
                    time.sleep(wait)
                    continue
                logger.error("LLM request failed after %s attempts: %s", attempt + 1, str(exc))
                return ""
            except Exception as exc:
                logger.exception("Unexpected error calling LLM: %s", exc)
                return ""
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