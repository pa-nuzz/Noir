import logging
from django.conf import settings
from .llm_client import get_llm_client

logger = logging.getLogger(__name__)


def generate_ai_copy(prompt: str, tone: str = "professional") -> dict:
    """
    Generate email subject and body copy based on a user prompt and tone configuration.
    Uses LLM (OpenAI-compatible) for high-quality AI copy generation.

    Args:
        prompt (str): The user's instructions for the email copy.
        tone (str): The desired tone ('casual', 'urgent', 'professional', 'creative').

    Returns:
        dict: A dictionary with 'subject', 'body', and 'mode' keys.
    """
    llm = get_llm_client()
    
    if not llm.is_configured():
        logger.warning("No AI API keys configured. Returning mock values.")
        return {
            "subject": f"[Configure AI] Subject in {tone} tone",
            "body": f"To enable AI copy generation, set your LLM_API_KEY in the .env file.",
            "mode": "mock"
        }

    tone_descriptions = {
        "professional": "polished, clear, and business-focused",
        "urgent": "action-oriented, time-sensitive, and compelling",
        "casual": "friendly, conversational, and lighthearted",
        "creative": "highly engaging, story-driven, and unique"
    }
    tone_desc = tone_descriptions.get(tone.lower(), "professional")

    system_instruction = (
        f"You are an expert marketing email copywriter. Write a highly converting marketing email "
        f"based on the instructions. The email tone must be {tone_desc}. "
        f"Do not include placeholders like '[First Name]' or similar tags; "
        f"instead write generic natural copy that reads well. "
        f"Respond in JSON format with keys 'subject' and 'body'."
    )

    user_prompt = f"Write a {tone} marketing email based on: {prompt}"

    try:
        structured_data = llm.generate(
            system_prompt=system_instruction,
            user_prompt=user_prompt,
            temperature=0.4,
            max_tokens=800,
            response_format='json'
        )
        
        if structured_data:
            import json
            try:
                parsed = json.loads(structured_data)
                model_name = getattr(settings, 'LLM_MODEL', 'gpt-4o')
                return {
                    "subject": parsed.get("subject", "").strip(),
                    "body": parsed.get("body", "").strip(),
                    "mode": model_name
                }
            except (json.JSONDecodeError, TypeError):
                pass
    except Exception as e:
        logger.error(f"AI copy generation failed: {e}")

    return {
        "subject": "Error generating copy",
        "body": "Could not generate copy. Check API key and try again.",
        "mode": "error"
    }
