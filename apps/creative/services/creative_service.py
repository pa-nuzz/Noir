import json
import logging
from typing import Optional

from .client import get_llm_client
from .prompts import build_system_prompt, build_critic_prompt, build_refiner_prompt

logger = logging.getLogger(__name__)

REQUIRED_CONTEXT_KEYS = {"name", "industry", "product", "audience", "tone", "mission", "uvp"}

# Keys that represent structured arrays/objects extracted from parsed JSON
_STRUCTURED_KEYS = {
    "platforms", "taglines", "top_picks", "headlines", "body_copy",
    "ctas", "hooks", "ab_testing_hypotheses", "visual_notes",
    "angles", "master_prompt", "style_variations", "aspect_ratio",
    "logo_concepts", "sections", "weekly_themes", "daily_breakdown",
    "special_dates", "content_format_mix", "repurposing_suggestions",
    "production_deadlines",
}


class CreativeServiceError(Exception):
    pass


def _validate_context(company_context: dict) -> None:
    missing = REQUIRED_CONTEXT_KEYS - set(company_context.keys())
    if missing:
        raise CreativeServiceError(
            f"Missing required company context keys: {', '.join(sorted(missing))}"
        )


def _parse_response(raw: str) -> dict:
    """Parse LLM JSON response, extracting both standard and category-specific keys."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("LLM response was not valid JSON, falling back to text extraction")
        return _fallback_parse(raw)

    result: dict = {
        "type": parsed.get("type", "idea"),
        "title": parsed.get("title", "Creative Concept"),
        "content": parsed.get("content", raw),
        "variations": parsed.get("variations", None),
        "sections": parsed.get("sections", None),
    }

    # Extract any category-specific structured keys
    for key in _STRUCTURED_KEYS:
        if key in parsed:
            result[key] = parsed[key]

    return result


def _fallback_parse(raw: str) -> dict:
    """Extract basic info from non-JSON text."""
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    title = "Creative Concept"
    content = raw

    for line in lines:
        if line.lower().startswith("title:"):
            title = line.split(":", 1)[1].strip()
            break
        if line.lower().startswith("# "):
            title = line[2:].strip()
            break

    return {
        "type": "idea",
        "title": title,
        "content": content,
        "variations": None,
        "sections": None,
    }


def _map_strategy_type_to_category(strategy_type: str) -> str:
    """Map legacy/internal strategy types to unified category names."""
    if strategy_type in {
        "campaign_idea", "brand_story", "social_strategy", "ad_copy",
        "product_launch", "tagline", "creative_angles", "image_prompt",
        "full_campaign", "logo_design", "post_content", "social_post",
        "brand_identity", "content_calendar",
    }:
        return strategy_type
    return "full_campaign"


def generate_creative_content(
    user_input: str,
    company_context: dict,
    category: str = "full_campaign",
    temperature: float = 0.85,
    max_tokens: int = 2048,
    use_multi_agent: bool = True,
) -> dict:
    """
    Generate creative content using an iterative multi-agent process (Ideator -> Critic -> Refiner).

    Args:
        user_input: The user's prompt / brief.
        company_context: Dictionary with company context.
        category: Creative strategy category.
        temperature: LLM temperature (default 0.85 for creative tasks).
        max_tokens: Max tokens for the LLM response.
        use_multi_agent: Whether to use the Critic -> Refiner loop.

    Returns:
        Parsed dict with standard keys (type, title, content, variations, sections)
        plus any category-specific keys (platforms, taglines, headlines, etc.).
    """
    _validate_context(company_context)

    resolved_category = _map_strategy_type_to_category(category)

    try:
        system_prompt = build_system_prompt(resolved_category, company_context)
    except ValueError as exc:
        raise CreativeServiceError(str(exc))

    client = get_llm_client()
    if not client.is_configured():
        raise CreativeServiceError(
            "LLM is not configured. Set LLM_API_KEY, LLM_BASE_URL, "
            "and LLM_MODEL in your .env file."
        )

    logger.info(f"Generating initial draft for {resolved_category}...")
    initial_raw = client.generate(
        system_prompt=system_prompt,
        user_prompt=user_input,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format='json',
    )

    if not initial_raw:
        raise CreativeServiceError(
            "LLM returned empty response during initial generation. Check your API key and network."
        )

    if not use_multi_agent:
        return _parse_response(initial_raw)

    # Agent 2: Critic
    logger.info(f"Generating critique for {resolved_category}...")
    critic_system_prompt = build_critic_prompt(resolved_category, company_context)
    critic_user_prompt = f"USER BRIEF:\n{user_input}\n\nINITIAL DRAFT:\n{initial_raw}"
    
    critique = client.generate(
        system_prompt=critic_system_prompt,
        user_prompt=critic_user_prompt,
        temperature=0.7,
        max_tokens=1024,
    )

    if not critique:
        logger.warning("Critic failed to return a response, falling back to initial draft.")
        return _parse_response(initial_raw)

    # Agent 3: Refiner
    logger.info(f"Refining draft for {resolved_category} based on critique...")
    refiner_system_prompt = build_refiner_prompt(resolved_category, company_context)
    refiner_user_prompt = (
        f"USER BRIEF:\n{user_input}\n\n"
        f"INITIAL DRAFT:\n{initial_raw}\n\n"
        f"CMO CRITIQUE:\n{critique}\n\n"
        f"Please completely rewrite the draft, fixing all issues raised in the critique, "
        f"and outputting the final JSON."
    )

    final_raw = client.generate(
        system_prompt=refiner_system_prompt,
        user_prompt=refiner_user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format='json',
    )

    if not final_raw:
        logger.warning("Refiner failed to return a response, falling back to initial draft.")
        return _parse_response(initial_raw)

    return _parse_response(final_raw)
