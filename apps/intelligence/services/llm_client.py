import logging
import httpx
import os
from typing import Optional
from decouple import config
from django.conf import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified LLM client for Gemini API with fallback handling."""
    
    def __init__(self):
        self.api_key = (
            config('GEMINI_API_KEY', default=None)
            or getattr(settings, 'GEMINI_API_KEY', None)
            or os.environ.get('GEMINI_API_KEY')
        )
        self.model = 'gemini-2.5-flash'
        self.timeout = 30.0
    
    def is_configured(self) -> bool:
        """Check if API key is available."""
        return bool(self.api_key)
    
    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        response_format: Optional[str] = None
    ) -> str:
        """Generate response from Gemini API.
        
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
            logger.error("GEMINI_API_KEY not configured")
            return ""
        
        payload = {
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        
        if response_format == 'json':
            payload["generationConfig"]["responseMimeType"] = "application/json"
        
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
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
            error_text = e.response.text
            logger.error(f"Gemini API error ({e.response.status_code}): {error_text}")
            return ""
        except httpx.RequestError as e:
            logger.error(f"Gemini request failed: {e}")
            return ""
        except Exception as e:
            logger.exception(f"Unexpected error calling Gemini: {e}")
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