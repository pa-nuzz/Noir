import json
import logging
import os
import time  # <--- Added for handling retry delays

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

LLM_MODEL = getattr(settings, 'LLM_MODEL', 'gpt-4o')
LLM_BASE_URL = getattr(settings, 'LLM_BASE_URL', 'https://api.openai.com/v1').rstrip('/')
LLM_API_KEY = getattr(settings, 'LLM_API_KEY', None) or os.environ.get('LLM_API_KEY')

SYSTEM_PROMPTS = {
    'caption': (
        "You are an expert social media copywriter specializing in scroll-stopping hooks.\n\n"
        "Write a platform-optimized caption based on the user's prompt. Follow this structure:\n"
        "- Hook: An opening line under 15 words using one of: curiosity gap, bold statement, "
        "relatable problem, or surprising statistic\n"
        "- Body: 3-5 short paragraphs delivering value (Instagram/LinkedIn) or 1 punchy "
        "paragraph (Twitter/X/TikTok)\n"
        "- CTA: End with a question or action that invites engagement\n\n"
        "Platform rules:\n"
        "- Instagram: First Read the prompt and  research about it online. Make a Linkedin post from this prompt. Pull out a problem, a fact, a benefit, the tone should be professional and informational no emojis, no hashtags. Start with a compelling headline, Tailor the content to industry relevance, providing insights or a professional takeaway and end with engaging questions to get engagement. make it one paragraph but keep it short. \n"
        "- LinkedIn: 1300-2000 chars, professional, use line breaks between sections\n"
        "- Twitter/X: under 280 chars total, concise\n"
        "- TikTok: under 100 chars, casual and punchy\n"
        "- Facebook: 150-500 chars, conversational\n"
        "- YouTube: descriptive, keyword-rich, 150-1000 chars\n\n"
        "Never use clichés like: 'In today's world', 'Let me tell you a story', "
        "'unlock the power', 'dive into', 'game-changer'.\n"
        "Return only the caption body. No commentary or explanations."
    ),
    'full_post': (
        "You are an expert social media content strategist. Write a complete, "
        "publication-ready social media post.\n\n"
        "Use this architecture:\n"
        "1. HOOK: Open with a bold statement, question, statistic, or relatable problem "
        "(under 15 words)\n"
        "2. PROBLEM/STORY: 1-2 short paragraphs establishing context or sharing insight\n"
        "3. SOLUTION/VALUE: 2-3 paragraphs delivering the core message, tips, or takeaways\n"
        "4. CTA: End with a clear action — question, comment prompt, or link direction\n\n"
        "Format rules:\n"
        "- Write in first-person voice for authenticity\n"
        "- Use short paragraphs (1-2 sentences each) separated by line breaks\n"
        "- No walls of text — each paragraph makes one point\n"
        "- Scannable: readers should get the gist in 5 seconds\n\n"
        "Platform-specific length:\n"
        "- LinkedIn: 1300-2000 chars, thought-leadership style\n"
        "- Facebook: 150-500 chars, conversational\n"
        "- X/Twitter: under 280 chars, punchy\n"
        "- Instagram: 150-220 chars before 'more'\n\n"
        "Adapt to the specified platform, tone, target audience, and key points.\n"
        "Return only the post body. No hashtags unless requested. No commentary."
    ),
    'hashtag_set': (
        "You are a social media hashtag strategist. Generate a strategic hashtag set "
        "based on the user's prompt and category.\n\n"
        "Use a 3-tier structure:\n"
        "- 5 broad hashtags (1M+ posts) — for discoverability\n"
        "- 10 medium hashtags (100K-1M posts) — for reach\n"
        "- 15 niche hashtags (<100K posts) — for targeted engagement\n\n"
        "Platform rules:\n"
        "- Instagram: 30 total, mix of all three tiers\n"
        "- LinkedIn: 3-5 professional hashtags, no broad tier\n"
        "- Twitter/X: 1-2 maximally relevant only\n"
        "- TikTok: 3-5 trending + 2-3 niche\n\n"
        "Return only the hashtags as a single space-separated line, highest relevance first. "
        "No numbers, category labels, duplicates, or banned hashtags."
    ),
    'carousel': (
        "You are a social media carousel expert. Create a slide-by-slide carousel "
        "that tells one cohesive story.\n\n"
        "Structure:\n"
        "- Slide 1 (Cover): A bold title and subtitle that works as a stand-alone "
        "attention-grabber — must make people want to swipe\n"
        "- Slides 2 to N-1: One key insight per slide, each building on the previous\n"
        "- Last Slide (CTA): Summary takeaway + clear call-to-action\n\n"
        "Format each slide as:\n"
        "SLIDE <N> | Heading: <headline> | Body: <2-3 sentences> | Visual: <description>\n\n"
        "Include a visual direction suggestion for each slide "
        "(e.g. 'infographic with stats', 'before/after photo', 'quote overlay').\n"
        "The carousel must have a narrative arc — hook, education, CTA."
    ),
    'script': (
        "You are a professional video scriptwriter specializing in short-form and "
        "long-form content. Write a timestamped video script.\n\n"
        "Use the template matching the specified format:\n\n"
        "For Reel/Shorts (15-30s):\n"
        "- 0-3s: Hook — pattern interrupt, bold statement, or visual surprise\n"
        "- 3-25s: Body — fast-paced value delivery, one core message\n"
        "- 25-30s: CTA — engagement ask (comment, share, save)\n\n"
        "For TikTok (30-60s):\n"
        "- 0-3s: Pattern interrupt hook\n"
        "- 3-45s: Value delivery with 2-3 quick points\n"
        "- 45-60s: Engagement ask + call-to-action\n\n"
        "For YouTube (3-5min):\n"
        "- 0-15s: Hook + preview of what's coming\n"
        "- 15-45s: Introduction + context\n"
        "- 45s+: Chaptered content body (3-4 chapters)\n"
        "- Last 30s: CTA + outro\n\n"
        "Format each section as:\n"
        "TIMESTAMP | Visual: <scene description> | Audio: <spoken text> | "
        "On-Screen: <text overlay suggestions> | Performance: <delivery notes in [brackets]>\n\n"
        "Include on-screen text overlay suggestions per scene. "
        "Note background music mood shifts where relevant."
    ),
    'image_prompt': (
        "You are an expert prompt engineer for AI image generation. Craft detailed, "
        "vivid prompts optimized for the specified model.\n\n"
        "Use this structure:\n"
        "[Subject] + [Subject Details] + [Setting/Background] + [Lighting] + "
        "[Mood/Atmosphere] + [Style/Art Direction] + [Technical Quality]\n\n"
        "Model-specific styles:\n"
        "- DALL-E 3: Natural language, descriptive paragraphs, no special syntax\n"
        "- Midjourney: Shorter, style-emphasis, include parameters like --ar 16:9 --v 6\n"
        "- Stable Diffusion: Comma-separated keyword format, include negative prompt\n\n"
        "Always include:\n"
        "- Lighting: dramatic, soft, golden hour, neon, studio\n"
        "- Color palette: specific colors or moods (warm, cool, monochrome)\n"
        "- Quality terms: highly detailed, 8k, sharp focus, photorealistic\n"
        "- Aspect ratio suggestion\n\n"
        "If negative prompt is supported (SD), provide it in a SEPARATE NEGATIVE: section.\n"
        "Avoid generic quality descriptors like 'masterpiece', 'beautiful', 'stunning'. "
        "Be specific instead.\n"
        "Return only the prompt(s). No explanations."
    ),
    'cta': (
        "You are a conversion copywriter specializing in high-performance calls-to-action.\n\n"
        "Write compelling CTAs based on the specified goal.\n\n"
        "Use proven copywriting frameworks:\n"
        "- AIDA: Attention → Interest → Desire → Action\n"
        "- PAS: Problem → Agitate → Solution\n"
        "- BAB: Before → After → Bridge\n\n"
        "Generate 5 CTA variants, each using a different psychological trigger:\n"
        "1. Direct command ('Sign up now')\n"
        "2. Question-based ('Ready to start?')\n"
        "3. Curiosity gap ('See what's inside')\n"
        "4. Benefit-first ('Get your free guide')\n"
        "5. Social proof ('Join 10,000+ members')\n\n"
        "Make each variant urgent, clear, and action-oriented.\n"
        "Adapt to the specified platform and goal.\n\n"
        "Return as:\n"
        "VARIANT 1 [<trigger_label>]: <CTA text>\n"
        "VARIANT 2 [<trigger_label>]: <CTA text>\n"
        "..."
    ),
}

TONE_DESCRIPTIONS = {
    'professional': 'polished, clear, and business-focused',
    'casual': 'friendly, conversational, and lighthearted',
    'humorous': 'funny, witty, and entertaining',
    'inspirational': 'uplifting, motivational, and empowering',
    'urgent': 'action-oriented, time-sensitive, and compelling',
}


def _extra_instructions(content_type, **kwargs):
    instructions = {
        'caption': lambda: (
            f"Target audience: {kwargs.get('target_audience', 'general audience')}. "
            f"Include {kwargs.get('caption_hashtag_count', 3)} relevant hashtags at the end."
        ),
        'full_post': lambda: (
            f"Target audience: {kwargs.get('target_audience', 'general audience')}. "
            f"Key points to cover: {kwargs.get('key_points', '')}."
        ),
        'hashtag_set': lambda: (
            f"Category: {kwargs.get('category', 'general')}. "
            f"Generate exactly {kwargs.get('count', 10)} hashtags."
        ),
        'carousel': lambda: (
            f"Generate exactly {kwargs.get('slides', 5)} slides."
        ),
        'script': lambda: (
            f"Format: {kwargs.get('format', 'short')}. "
            f"Target duration: {kwargs.get('target_duration', '')} seconds. "
            f"Adapt length and structure accordingly."
        ),
        'image_prompt': lambda: (
            f"Style: {kwargs.get('style', '')}. "
            f"Mood: {kwargs.get('mood', '')}. "
            f"Target model: {kwargs.get('model', 'dalle')}."
        ),
        'cta': lambda: (
            f"Goal: {kwargs.get('goal', 'engagement')}. "
            f"Target action: {kwargs.get('target_action', 'click')}."
        ),
    }
    fn = instructions.get(content_type)
    return fn() if fn else ''


def _build_system_prompt(content_type, platform=None, tone='professional', **kwargs):
    base = SYSTEM_PROMPTS.get(content_type, 'You are a helpful content creator.')
    tone_str = TONE_DESCRIPTIONS.get(tone, 'polished, clear, and business-focused')
    platform_str = f"Platform: {platform}." if platform else ""
    extra = _extra_instructions(content_type, **kwargs)

    negative = (
        "Plain text only. Do NOT use markdown, bold (**), italic (*), headers, or any formatting markup. "
        "Never explain or comment on the output. Return only the requested content."
    )

    parts = [base, tone_str, platform_str, extra, negative]
    return "\n\n".join(p for p in parts if p)


def _call_llm(system_prompt, user_prompt, api_key):
    url = f"{LLM_BASE_URL}/chat/completions"

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    max_retries = 3
    retry_delay = 1.5

    for attempt in range(max_retries):
        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=30.0)

            if response.status_code == 503:
                if attempt < max_retries - 1:
                    logger.warning(f"LLM API 503 service unavailable. Retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    logger.error("LLM API 503 retry quota exhausted.")
                    return {"success": False, "error": "server_overloaded", "message": "AI service is momentarily busy. Please try again in a few seconds.", "content": None}

            if response.status_code == 401:
                logger.error("LLM API returned 401 — invalid API key.")
                return {"success": False, "error": "api_key_invalid", "message": "LLM API key is invalid. Please check your LLM_API_KEY.", "content": None}

            if response.status_code == 403:
                logger.error("LLM API returned 403 — forbidden.")
                return {"success": False, "error": "forbidden", "message": "Access forbidden. Check your LLM_API_KEY and permissions.", "content": None}

            if response.status_code == 429:
                logger.error("LLM API returned 429 — rate limited.")
                return {"success": False, "error": "rate_limited", "message": "AI rate limit exceeded. Please wait a moment and try again.", "content": None}

            if response.status_code == 400:
                body = response.text[:500]
                logger.error(f"LLM API returned 400 — bad request: {body}")
                return {"success": False, "error": "bad_request", "message": f"AI request was invalid: {body}", "content": None}

            response.raise_for_status()
            result = response.json()

            try:
                text = result["choices"][0]["message"]["content"].strip()
            except (KeyError, IndexError, AttributeError):
                return {"success": False, "error": "unexpected_response", "message": "Received an unexpected response format from the AI API.", "content": None}

            return {"success": True, "error": None, "message": None, "content": text}

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 503 and attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            logger.exception(f"LLM HTTP status exception caught: {e}")
            return {"success": False, "error": "http_error", "message": "A connection status error occurred with the AI service.", "content": None}
            
        except httpx.TimeoutException:
            logger.error("LLM API request timed out.")
            return {"success": False, "error": "timeout", "message": "AI request timed out. Please try again.", "content": None}
            
        except Exception as e:
            logger.exception(f"LLM API request failed: {e}")
            return {"success": False, "error": "unknown", "message": f"An error occurred while contacting the AI API: {str(e)}", "content": None}


def generate_llm(content_type, prompt, platform=None, tone='professional', **kwargs):
    api_key = LLM_API_KEY

    if not api_key:
        logger.warning("LLM_API_KEY is not configured.")
        return {
            "success": False,
            "error": "api_key_missing",
            "message": "LLM API key is not configured. Please set LLM_API_KEY in your .env file.",
            "content": None,
        }

    system_prompt = _build_system_prompt(content_type, platform, tone, **kwargs)
    return _call_llm(system_prompt, prompt, api_key)


def refine_llm(content_type, content, feedback, platform=None, tone='professional', **kwargs):
    api_key = LLM_API_KEY

    if not api_key:
        return {"success": False, "error": "api_key_missing", "message": "LLM API key is not configured. Please set LLM_API_KEY in your .env file.", "content": None}

    tone_str = TONE_DESCRIPTIONS.get(tone, 'polished, clear, and business-focused')
    platform_str = f"Platform: {platform}." if platform else ""

    system_prompt = (
        f"You are an expert content editor. Revise the given content based on the user's feedback. "
        f"Maintain the original {content_type} format. Tone: {tone_str}. {platform_str}\n\n"
        f"Return only the revised content, no explanations. Plain text only — no markdown, bold, italic, or formatting markup."
    )

    user_prompt = f"Original content:\n{content}\n\nFeedback:\n{feedback}\n\nPlease revise accordingly."

    return _call_llm(system_prompt, user_prompt, api_key)


MULTI_PLATFORM_SYSTEM_PROMPT = (
    "You are an expert social media content strategist. Generate platform-specific "
    "{content_type} for each applicable platform based on the user's prompt.\n\n"
    "For each platform, adapt the content to that platform's unique style, length, "
    "and audience expectations. Some platforms may not be suitable for this content "
    "type — set 'status' to false for those.\n\n"
    "Return ONLY a valid JSON object with no additional text before or after:\n"
    '{{\n'
    '  "instagram": {{"content": "...", "status": true}},\n'
    '  "facebook": {{"content": "...", "status": true}},\n'
    '  "twitter": {{"content": "...", "status": true}},\n'
    '  "linkedin": {{"content": "...", "status": true}},\n'
    '  "tiktok": {{"content": "...", "status": true}},\n'
    '  "youtube": {{"content": "...", "status": false}}\n'
    "}}\n\n"
    "Set 'status' to false for platforms where this content type is not a good fit. "
    "Do NOT include markdown code fences or any text outside the JSON."
)

MULTI_PLATFORM_TONE = (
    "Tone: {tone_str}.\n"
)

MULTI_PLATFORM_EXTRA = (
    "Extra instructions: {extra}\n"
)


def _extract_json(text):
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start:end + 1]


def generate_llm_multi(content_type, prompt, tone='professional', **kwargs):
    api_key = LLM_API_KEY

    try:
        from apps.content_studio.models import ALL_PLATFORMS
    except ImportError:
        from ..models import ALL_PLATFORMS

    if not api_key:
        logger.warning("LLM_API_KEY is not configured.")
        return {"success": False, "error": "api_key_missing", "message": "LLM API key is not configured.", "content": None, "platform_data": None}

    tone_str = TONE_DESCRIPTIONS.get(tone, 'polished, clear, and business-focused')
    extra = _extra_instructions(content_type, **kwargs)

    system_prompt = (
        MULTI_PLATFORM_SYSTEM_PROMPT.format(content_type=content_type)
        + f"\n\n{tone_str}.\n\n"
        + f"Extra instructions: {extra}\n\n"
        + "Plain text only. Do NOT use markdown, bold (**), italic (*), headers, or any formatting markup in the content values."
    )

    # Fixed dynamic import lookup to avoid reloader scope leakage drops
    try:
        from apps.content_studio.models import ALL_PLATFORMS
    except ImportError:
        from ..models import ALL_PLATFORMS

    result = _call_llm(system_prompt, prompt, api_key)
    if not result['success']:
        return {"success": False, "error": result['error'], "message": result['message'], "content": None, "platform_data": None}

    raw = result['content']
    json_str = _extract_json(raw)
    if not json_str:
        logger.error("No JSON found in multi-platform response")
        return {"success": False, "error": "parse_error", "message": "Could not parse multi-platform response.", "content": None, "platform_data": None}

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse multi-platform JSON: {e}")
        return {"success": False, "error": "parse_error", "message": f"Invalid JSON in response: {e}", "content": None, "platform_data": None}

    platform_data = {}
    first_active = None
    for platform in ALL_PLATFORMS:
        entry = parsed.get(platform, {})
        if isinstance(entry, dict) and entry.get('status') and entry.get('content'):
            platform_data[platform] = {
                "content": entry['content'],
                "status": True,
            }
            if first_active is None:
                first_active = platform
        else:
            platform_data[platform] = {
                "content": "",
                "status": False,
            }

    return {
        "success": True,
        "error": None,
        "message": None,
        "content": platform_data[first_active]['content'] if first_active else "",
        "platform_data": platform_data,
        "first_active": first_active,
    }