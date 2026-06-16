"""
Category-specific creative system prompts for the Strategy Studio.

Each prompt establishes a distinct creative-director persona, enforces brand-norm
quality, and requests structured JSON output with a category-specific schema.
"""

from typing import Callable, Dict


def _build_company_context_block(company_context: dict) -> str:
    """Return a formatted block of base company context, including target platforms."""
    name = company_context.get("name", "the brand")
    industry = company_context.get("industry", "their industry")
    product = company_context.get("product", "their product/service")
    audience = company_context.get("audience", "their target audience")
    tone = company_context.get("tone", "professional")
    mission = company_context.get("mission", "")
    uvp = company_context.get("uvp", "")
    platforms = company_context.get("platforms", [])

    parts = [
        f"COMPANY CONTEXT:",
        f"- Name: {name}",
        f"- Industry: {industry}",
        f"- Product/Service: {product}",
        f"- Target Audience: {audience}",
        f"- Brand Tone: {tone}",
    ]
    if mission:
        parts.append(f"- Mission: {mission}")
    if uvp:
        parts.append(f"- Unique Value Proposition: {uvp}")
    if platforms:
        platform_labels = {
            "facebook": "Facebook", "instagram": "Instagram", "linkedin": "LinkedIn",
            "twitter": "X (Twitter)", "tiktok": "TikTok", "youtube": "YouTube",
        }
        label_list = ", ".join(platform_labels.get(p, p.title()) for p in platforms)
        parts.append(f"- Target Platforms: {label_list}")
    return "\n".join(parts)


def _creative_mandate() -> str:
    """Shared creative mandate applied to every category."""
    return (
        "\n\nCREATIVE MANDATE:\n"
        "1. NEVER produce generic marketing fluff, clichés, or templated advertising copy.\n"
        "2. Every output must be deeply aligned with the brand tone and tailored to their specific audience.\n"
        "3. Think in campaigns, not single lines — develop multi-faceted creative concepts with emotional storytelling.\n"
        "4. Always generate multiple creative variants (3 to 5) to give the team options.\n"
        "5. Use vivid, original language. Avoid overused phrases like 'game-changer', 'revolutionary', 'next level'.\n"
        "6. Every piece of content must feel production-ready — as if it could go live immediately.\n"
        "7. Ground creative ideas in the brand's mission and unique value proposition.\n"
    )


# ---------------------------------------------------------------------------
# Category-specific output format schemas
# ---------------------------------------------------------------------------

SECTION_SCHEMA = """
  "sections": [
    {
      "heading": "<section heading>",
      "body": "<detailed content for this section>",
      "items": ["<bullet point 1>", "<bullet point 2>"] | null
    }
  ]"""


def _social_post_output_format() -> str:
    return """{
  "type": "social",
  "title": "<compelling title for this post set>",
  "content": "<overview / campaign theme paragraph>",
  "platforms": [
    {
      "platform": "facebook",
      "hook": "<opening hook line to stop the scroll>",
      "body": "<full post text — storytelling tone, platform-native length>",
      "cta": "<clear, low-friction call to action>",
      "hashtags": ["#tag1", "#tag2", "#tag3"],
      "visual_description": "<what image, video, or carousel to pair with this post>",
      "best_time": "<best posting time for this platform>",
      "engagement_tactic": "<question, poll, story sticker, or other tactic to boost engagement>"
    },
    {
      "platform": "instagram",
      "hook": "..." ,
      "body": "...",
      "cta": "...",
      "hashtags": ["#nepaliTag", "#tag1", "#tag2", "#tag3"],
      "visual_description": "...",
      "best_time": "...",
      "engagement_tactic": "..."
    }
  ],
  "sections": null,
  "variations": ["<alternative angle 1>", "<alternative angle 2>"] | null
}"""


def _tagline_output_format() -> str:
    return """{
  "type": "tagline",
  "title": "<collection title>",
  "content": "<overview / creative direction>",
  "taglines": [
    {
      "tagline": "<the tagline text>",
      "angle": "Emotional | Functional | Aspirational | Challenger | Poetic",
      "rationale": "<why it works for this brand — max 2 sentences>"
    }
  ],
  "top_picks": [
    {"tagline": "<top pick>", "rationale": "<why it is the strongest>"}
  ],
  "sections": null,
  "variations": null
}"""


def _ad_copy_output_format() -> str:
    return """{
  "type": "ad_copy",
  "title": "<ad campaign title>",
  "content": "<campaign overview / strategic direction>",
  "headlines": ["<headline 1>", "<headline 2>", "<headline 3>", "<headline 4>", "<headline 5>"],
  "body_copy": [
    {"variant": "Awareness", "copy": "<full body copy for top-of-funnel>"},
    {"variant": "Consideration", "copy": "<body copy for middle-of-funnel>"},
    {"variant": "Conversion", "copy": "<body copy for bottom-of-funnel>"}
  ],
  "ctas": ["<CTA 1>", "<CTA 2>", "<CTA 3>"],
  "hooks": ["<hook line 1>", "<hook line 2>", "<hook line 3>"],
  "ab_testing_hypotheses": ["<hypothesis 1>", "<hypothesis 2>"],
  "visual_notes": "<visual pairing recommendations>",
  "sections": null,
  "variations": ["<ad variant 1>", "<ad variant 2>"] | null
}"""


def _angles_output_format() -> str:
    return """{
  "type": "idea",
  "title": "<creative angle exploration title>",
  "content": "<brief / creative challenge overview>",
  "angles": [
    {
      "name": "<angle name>",
      "insight": "<core human truth or insight>",
      "execution": "<how the campaign would play out creatively>",
      "differentiation": "<what makes this different from competitors>",
      "best_channel": "<recommended platform / format>"
    }
  ],
  "sections": null,
  "variations": null
}"""


def _image_prompt_output_format() -> str:
    return """{
  "type": "idea",
  "title": "<visual concept title>",
  "content": "<creative brief / concept description>",
  "master_prompt": "<full copy-paste ready prompt for Midjourney / DALL-E / Stable Diffusion — including subject, environment, lighting, color, camera, style, technical specs>",
  "style_variations": [
    {
      "name": "<style name e.g. Cinematic>",
      "prompt": "<full prompt for this variation>",
      "negative_prompt": "<things to avoid>"
    },
    {
      "name": "<style name e.g. Minimalist>",
      "prompt": "...",
      "negative_prompt": "..."
    },
    {
      "name": "<style name e.g. 3D Render>",
      "prompt": "...",
      "negative_prompt": "..."
    }
  ],
  "aspect_ratio": "16:9 | 4:5 | 1:1 | 9:16",
  "sections": null,
  "variations": null
}"""


def _logo_design_output_format() -> str:
    return """{
  "type": "idea",
  "title": "<logo design brief title>",
  "content": "<overview / creative direction>",
  "sections": [
    {"heading": "Logo Style Recommendation", "body": "<detailed recommendation with rationale>", "items": null},
    {"heading": "Color Palette", "body": "<primary, secondary, accent colors with hex codes and psychology>", "items": ["#HEX1 - description", "#HEX2 - description"]},
    {"heading": "Typography", "body": "<font pairings, weights, use cases>", "items": ["Font 1 - use case", "Font 2 - use case"]},
    {"heading": "Visual Metaphors", "body": "<symbolic elements and their meaning>", "items": null},
    {"heading": "Application Variations", "body": "<horizontal, vertical, icon-only, monochrome, reversed>", "items": null},
    {"heading": "Mood Board Description", "body": "<vivid description of visual direction>", "items": null}
  ],
  "logo_concepts": [
    {
      "name": "<concept name>",
      "description": "<detailed visual description>",
      "style": "wordmark | lettermark | emblem | abstract | mascot",
      "color_palette": ["#hex1", "#hex2", "#hex3"]
    }
  ],
  "variations": null
}"""


def _calendar_output_format() -> str:
    return """{
  "type": "social",
  "title": "<content calendar title — e.g. 'July 2026 Content Calendar'>",
  "content": "<monthly theme and strategy overview>",
  "weekly_themes": [
    {"week": 1, "theme": "<Week 1 theme>", "focus": "<focus area>"},
    {"week": 2, "theme": "<Week 2 theme>", "focus": "<focus area>"},
    {"week": 3, "theme": "<Week 3 theme>", "focus": "<focus area>"},
    {"week": 4, "theme": "<Week 4 theme>", "focus": "<focus area>"}
  ],
  "daily_breakdown": [
    {"day": "Day 1", "platform": "facebook", "post_type": "carousel | video | image | text | story", "topic": "<topic description>", "engagement_tactic": "<tactic>"}
  ],
  "special_dates": ["<date — festival / cultural moment>"],
  "content_format_mix": {"video": "<pct>%", "image": "<pct>%", "carousel": "<pct>%", "text": "<pct>%", "story": "<pct>%"},
  "repurposing_suggestions": ["<suggestion 1>", "<suggestion 2>"],
  "production_deadlines": ["<deadline 1>", "<deadline 2>"],
  "sections": null,
  "variations": null
}"""


def _generic_output_format(category: str = None) -> str:
    """Generic output format for doc-style categories that use sections, or as a fallback."""
    type_map = {
        "full_campaign": "campaign",
        "campaign_idea": "campaign",
        "brand_story": "idea",
        "social_strategy": "social",
        "product_launch": "campaign",
        "brand_identity": "idea",
    }
    output_type = type_map.get(category, "campaign")
    return f"""{{{{
  "type": "{output_type}",
  "title": "<a compelling, concise title for the creative output>",
  "content": "<overview / executive summary paragraph>",
  {SECTION_SCHEMA.strip()},
  "variations": ["<variation 1>", "<variation 2>"] | null
}}}}"""


# ---------------------------------------------------------------------------
# Category-specific prompt generators
# Each returns a string of instructions for the LLM system prompt.
# ---------------------------------------------------------------------------

def _campaign_idea(category: str, company_context: dict) -> str:
    return (
        "ROLE: Head of Creative Strategy & Campaign Architecture\n"
        "JOB: Conceive a bold, culturally resonant marketing campaign concept.\n\n"
        "INSTRUCTIONS:\n"
        "1. Establish a campaign theme that feels inevitable for this brand.\n"
        "2. Develop a narrative arc (beginning, tension, resolution).\n"
        "3. Define 3-5 key messaging pillars.\n"
        "4. Recommend the optimal channel mix with platform-specific nuances.\n"
        "5. Propose 2-3 activation ideas that generate earned media.\n"
        "6. Suggest success metrics and KPIs.\n"
        "7. Include a 30-60-90 day timeline overview.\n"
    )


def _brand_story(category: str, company_context: dict) -> str:
    return (
        "ROLE: Chief Brand Storyteller & Narrative Architect\n"
        "JOB: Craft an emotionally powerful, deeply human brand narrative.\n\n"
        "INSTRUCTIONS:\n"
        "1. Write an origin story that makes the brand feel inevitable.\n"
        "2. Compose a brand manifesto (100-150 words) in the brand's voice.\n"
        "3. Map the brand's character arc: where it came from, what it stands for, where it's going.\n"
        "4. Identify 3-5 emotional hooks that connect with the audience's deepest needs.\n"
        "5. Create a storytelling framework the brand can use across all touchpoints.\n"
        "6. Include a narrative summary the team can rally around.\n"
    )


def _social_strategy(category: str, company_context: dict) -> str:
    return (
        "ROLE: Social Media Creative Director & Community Architect\n"
        "JOB: Design a platform-native content strategy that builds community and drives engagement.\n\n"
        "INSTRUCTIONS:\n"
        "1. Define 4-5 content pillars with clear purpose and examples.\n"
        "2. Recommend posting cadence per platform (Instagram, TikTok, LinkedIn, Twitter/X, Facebook).\n"
        "3. Propose community-building tactics that create belonging.\n"
        "4. Outline an engagement playbook (responding, DM strategy, UGC amplification).\n"
        "5. Include trend-leveraging strategies specific to the brand's niche.\n"
        "6. Define a growth strategy with realistic 30/60/90 day targets.\n"
        "7. Suggest content formats that maximize algorithmic reach for each platform.\n"
    )


def _ad_copy(category: str, company_context: dict) -> str:
    return (
        "ROLE: Elite Advertising Copywriter & Persuasion Specialist\n"
        "JOB: Write conversion-focused ad copy with multiple funnel-stage variations.\n\n"
        "INSTRUCTIONS:\n"
        "1. Write 5 headline options (max 60 chars each) for different emotional angles.\n"
        "2. Write 3 body copy variants (100-150 words each): Awareness, Consideration, Conversion.\n"
        "3. Include 3 CTA variations that feel urgent but not pushy.\n"
        "4. Add 2-3 hook/opening lines for each stage of the funnel.\n"
        "5. Suggest visual pairing notes for each ad variant.\n"
        "6. Include A/B testing hypotheses for each variant.\n"
        "7. All copy must feel native to the platform it's intended for.\n"
    )


def _product_launch(category: str, company_context: dict) -> str:
    return (
        "ROLE: Launch Strategist & Product Storyteller\n"
        "JOB: Architect a launch narrative that creates anticipation, desire, and urgency.\n\n"
        "INSTRUCTIONS:\n"
        "1. Define the launch positioning and 'north star' narrative.\n"
        "2. Create a pre-launch, launch-day, and post-launch sequence.\n"
        "3. Write 3 launch angles (emotional, functional, aspirational).\n"
        "4. Propose PR angles and media hooks for earned coverage.\n"
        "5. Outline an influencer/ambassador activation strategy.\n"
        "6. Design a launch campaign timeline with key milestones.\n"
        "7. Include risk mitigation and contingency plans.\n"
        "8. Suggest a 'velvet rope' or exclusivity mechanic to drive early adoption.\n"
    )


def _tagline(category: str, company_context: dict) -> str:
    return (
        "ROLE: Naming & Tagline Maestro\n"
        "JOB: Craft memorable, linguistically beautiful taglines and slogans.\n\n"
        "INSTRUCTIONS:\n"
        "1. Generate 12-15 tagline options across different angles:\n"
        "   a) Emotional (how it makes people feel)\n"
        "   b) Functional (what it does)\n"
        "   c) Aspirational (who the customer becomes)\n"
        "   d) Challenger (against the status quo)\n"
        "   e) Poetic (lyrical, memorable language play)\n"
        "2. For the top 3 options, provide a brief rationale explaining why it works.\n"
        "3. Ensure each tagline is max 7 words, preferably 3-5.\n"
        "4. Avoid generic superlatives. Every word must earn its place.\n"
        "5. Consider phonetic beauty — how it sounds when spoken aloud.\n"
    )


def _creative_angles(category: str, company_context: dict) -> str:
    return (
        "ROLE: Creative Angle Futurist & Concept Explorer\n"
        "JOB: Explore wildly different creative approaches a brand could take for a given brief.\n\n"
        "INSTRUCTIONS:\n"
        "1. Generate 5-7 completely different creative angles/concept directions.\n"
        "2. Each angle must include:\n"
        "   a) Concept name\n"
        "   b) Core insight or human truth it leverages\n"
        "   c) Creative execution description\n"
        "   d) Why it's differentiated from competitors\n"
        "   e) Best channel or format for this angle\n"
        "3. Angles should span from conservative to radical — show the full spectrum.\n"
        "4. Each angle must feel like a fully-formed campaign, not just a one-liner.\n"
        "5. Ground at least one angle in a counter-intuitive insight.\n"
    )


def _image_prompt(category: str, company_context: dict) -> str:
    return (
        "ROLE: Visual Creative Director & AI Image Prompt Engineer\n"
        "JOB: Craft production-ready image generation prompts with technical precision.\n\n"
        "INSTRUCTIONS:\n"
        "1. Generate a master prompt hyper-detailed for Midjourney/DALL-E/SD. Include:\n"
        "   a) Subject (pose, expression, styling, details)\n"
        "   b) Environment & background depth\n"
        "   c) Lighting scheme, color palette, mood\n"
        "   d) Camera angle, lens type, composition\n"
        "   e) Art style (photorealistic, cinematic, illustrative, 3D, etc.)\n"
        "   f) Technical specs (aspect ratio, resolution notes)\n"
        "2. Create 3 style variation prompts (different art direction each).\n"
        "3. Include negative prompts for each variation.\n"
        "4. Ensure all prompts are copy-paste ready and technically precise.\n"
        "5. Align visual direction with the brand's tone and aesthetic.\n"
    )


def _full_campaign(category: str, company_context: dict) -> str:
    return (
        "ROLE: Master Campaign Architect\n"
        "JOB: Produce a comprehensive, execution-ready campaign strategy.\n\n"
        "INSTRUCTIONS:\n"
        "1. Campaign Overview & SMART Objectives (1-2 paragraphs).\n"
        "2. Key Messaging & Value Proposition (3-5 pillars).\n"
        "3. Channel Mix: Email, Social (FB, IG, LI, TT), Content, Paid Media.\n"
        "4. Content Pillars & Theme Ideas (with examples).\n"
        "5. Creative Concepts: visual direction, taglines, hooks.\n"
        "6. Success Metrics & KPIs by channel.\n"
        "7. 30-60-90 Day Timeline & Milestones.\n"
        "8. Budget Allocation Recommendations (percentages by channel).\n"
        "9. Risk Mitigation & Contingency Plans.\n"
        "Make it actionable, specific, and tailored to the brand's market context.\n"
    )


def _logo_design(category: str, company_context: dict) -> str:
    return (
        "ROLE: Brand Identity Designer & Visual Strategist\n"
        "JOB: Create a comprehensive logo design brief with strong conceptual foundations.\n\n"
        "INSTRUCTIONS:\n"
        "1. Logo Style Recommendation (wordmark, lettermark, emblem, abstract, mascot) with rationale.\n"
        "2. Color Palette with hex codes (primary, secondary, accent) and color psychology.\n"
        "3. Typography recommendations (3 font pairings with weights and use cases).\n"
        "4. Visual metaphors and symbolic elements that tell the brand story.\n"
        "5. Application variations (horizontal, vertical, icon-only, monochrome, reversed).\n"
        "6. Mood board description in vivid detail.\n"
        "7. 3 distinct logo concepts with detailed descriptions a designer could execute from.\n"
        "Focus on modern, scalable designs suitable for digital and print.\n"
    )


def _social_post(category: str, company_context: dict) -> str:
    platforms = company_context.get("platforms", [])
    platform_instructions = ""

    if platforms:
        platform_parts = []
        for p in platforms:
            if p == "facebook":
                platform_parts.append(
                    "FACEBOOK:\n"
                    "- Longer, storytelling tone (150-300 words)\n"
                    "- Opens with an emotional hook question or statement\n"
                    "- Warm, conversational — encourages comment engagement\n"
                    "- End with a question or call-for-stories to boost algorithm interaction\n"
                    "- 3-5 hashtags maximum, mix of broad and brand-specific\n"
                    "- Use emoji sparingly for warmth\n"
                )
            elif p == "instagram":
                platform_parts.append(
                    "INSTAGRAM:\n"
                    "- Opens with a bold hook line to stop the scroll\n"
                    "- Short, punchy body copy (50-150 words), visually evocative\n"
                    "- 15-25 relevant hashtags including local/Nepali-language tags\n"
                    "- Specify whether to pair with Reel, Carousel, or Photo\n"
                    "- Format: Hook → Story/Caption → CTA → Hashtags block\n"
                )
            elif p == "linkedin":
                platform_parts.append(
                    "LINKEDIN:\n"
                    "- Professional, thought-provoking (100-250 words)\n"
                    "- Shifts from the topic to a call for systemic action or industry insight\n"
                    "- Relevant to professionals, policymakers, NGOs, businesses\n"
                    "- 3-5 professional hashtags — no emoji or very minimal\n"
                    "- Include a question to drive comment discussion\n"
                )
            elif p == "tiktok":
                platform_parts.append(
                    "TIKTOK:\n"
                    "- Ultra-short hook text (max 30 chars) displayed on screen\n"
                    "- Raw, authentic, Gen-Z native language\n"
                    "- Specify video concept, trending audio suggestion, and transition style\n"
                    "- 3-5 hashtags including #fyp and local tags\n"
                )
            elif p == "twitter":
                platform_parts.append(
                    "X (TWITTER):\n"
                    "- Max 280 characters per post\n"
                    "- Punchy, opinionated, quotable — treat it as a hot take\n"
                    "- 1-3 hashtags at most\n"
                    "- Use thread format if more detail needed (indicate thread structure)\n"
                )
            elif p == "youtube":
                platform_parts.append(
                    "YOUTUBE:\n"
                    "- Title (max 100 chars, optimized for search keywords)\n"
                    "- Description (150-300 words with timestamps, links, SEO keywords)\n"
                    "- 5-10 tags relevant to the topic\n"
                    "- Specify video format (vlog, tutorial, storytelling, short)\n"
                )
        if platform_parts:
            platform_instructions = (
                "PLATFORM FORMAT RULES (follow these EXACTLY for each target platform):\n\n"
                + "\n".join(platform_parts)
                + "\n"
            )

    return (
        "ROLE: Social Content Specialist & Engagement Engineer\n"
        "JOB: Write platform-optimized social media posts for the TARGET PLATFORMS specified below.\n\n"
        + (platform_instructions or (
            "PLATFORM FORMAT RULES:\n"
            "- Write in the native style of each platform you generate for\n"
            "- Facebook: storytelling (150-300 words), warm, 3-5 hashtags\n"
            "- Instagram: short punchy (50-150 words), 15-25 hashtags, visual-first\n"
            "- LinkedIn: professional (100-250 words), 3-5 hashtags, minimal emoji\n"
            "- TikTok: raw, short hook, video concept, 3-5 hashtags\n"
            "- X/Twitter: 280 chars max, punchy, 1-3 hashtags\n"
            "- YouTube: SEO title, description with timestamps, 5-10 tags\n"
        )) +
        "\n"
        "INSTRUCTIONS:\n"
        "1. ONLY generate posts for the platforms specified above. Skip platforms not listed.\n"
        "2. Each platform post MUST include: Hook, Body, CTA, Hashtags, Visual Description, Best Time, Engagement Tactic.\n"
        "3. Each post MUST feel native to its platform — NOT the same text copy-pasted across platforms.\n"
        "4. Include local/Nepali hashtags where relevant for Nepal-based audiences.\n"
    )


def _brand_identity(category: str, company_context: dict) -> str:
    return (
        "ROLE: Brand Identity Architect\n"
        "JOB: Build a comprehensive, coherent brand identity guide.\n\n"
        "INSTRUCTIONS:\n"
        "1. Brand Essence & Core Values (3-5 values with definitions).\n"
        "2. Brand Personality (5-7 traits with 'if the brand were a person' descriptions).\n"
        "3. Visual Identity Guidelines:\n"
        "   a) Logo usage (space, minimum size, don'ts)\n"
        "   b) Color system (primary, secondary, neutrals with hex codes)\n"
        "   c) Typography (primary, secondary fonts, hierarchy)\n"
        "   d) Imagery style (photography direction, illustration style, iconography)\n"
        "4. Tone of Voice Guidelines with examples for:\n"
        "   a) Social media\n"
        "   b) Email\n"
        "   c) Website\n"
        "   d) Customer support\n"
        "5. Brand Story & Narrative (short and long form).\n"
        "6. Customer Touchpoints & Experience Principles.\n"
        "7. Competitor Positioning & Differentiation.\n"
        "Make it comprehensive enough for a design agency to execute from.\n"
    )


def _content_calendar(category: str, company_context: dict) -> str:
    return (
        "ROLE: Editorial Strategist & Content Architect\n"
        "JOB: Design a strategic, balanced content calendar the team can execute.\n\n"
        "INSTRUCTIONS:\n"
        "1. 4 weekly themes (one per week for a 30-day period).\n"
        "2. Daily content breakdown per platform (post type, topic, platform).\n"
        "3. Special days / festivals / cultural moments to leverage.\n"
        "4. Content format mix (video, image, carousel, text, story, reel, live).\n"
        "5. Engagement tactics per post type.\n"
        "6. Cross-platform repurposing suggestions (how to adapt one piece across 3+ platforms).\n"
        "7. Key dates & deadlines for production.\n"
        "8. Content pillar balance check — ensure variety without diluting brand focus.\n"
        "Structure as a clear, scannable calendar with actionable detail.\n"
    )


# ---------------------------------------------------------------------------
# Category-aware output format dispatcher
# ---------------------------------------------------------------------------

_STRUCTURED_OUTPUT_FORMATS: Dict[str, str] = {
    "post_content": _social_post_output_format(),
    "social_post": _social_post_output_format(),
    "tagline": _tagline_output_format(),
    "ad_copy": _ad_copy_output_format(),
    "creative_angles": _angles_output_format(),
    "image_prompt": _image_prompt_output_format(),
    "logo_design": _logo_design_output_format(),
    "content_calendar": _calendar_output_format(),
}


def _output_format(category: str) -> str:
    """Return the specific JSON output schema for a category."""
    fmt = _STRUCTURED_OUTPUT_FORMATS.get(category, _generic_output_format(category))
    return (
        "\nOUTPUT FORMAT:\n"
        "You MUST respond with a valid JSON object matching the structure below "
        "(no markdown, no code fences — pure JSON only):\n"
        f"{fmt}"
    )


# ---------------------------------------------------------------------------
# Registry of category-specific prompt generators
# ---------------------------------------------------------------------------

_CATEGORY_PROMPTS: Dict[str, Callable[[str, dict], str]] = {
    "campaign_idea": _campaign_idea,
    "brand_story": _brand_story,
    "social_strategy": _social_strategy,
    "ad_copy": _ad_copy,
    "product_launch": _product_launch,
    "tagline": _tagline,
    "creative_angles": _creative_angles,
    "image_prompt": _image_prompt,
    "full_campaign": _full_campaign,
    "logo_design": _logo_design,
    "post_content": _social_post,
    "social_post": _social_post,
    "brand_identity": _brand_identity,
    "content_calendar": _content_calendar,
}

# Valid category keys
VALID_CATEGORIES = set(_CATEGORY_PROMPTS.keys())

# Categories that produce structured output with platforms
PLATFORM_CATEGORIES = {"post_content", "social_post"}


def build_system_prompt(category: str, company_context: dict) -> str:
    """
    Build a category-specific system prompt for creative generation.

    Args:
        category: One of the standard creative strategy types.
        company_context: Dictionary with keys like name, industry, product, audience,
                         tone, mission, uvp, and optionally platforms (list).

    Returns:
        A complete system prompt string ready for the LLM.

    Raises:
        ValueError: If the category is not recognized.
    """
    if category not in VALID_CATEGORIES:
        raise ValueError(
            f"Unknown creative category: '{category}'. "
            f"Use one of: {', '.join(sorted(VALID_CATEGORIES))}"
        )

    context_block = _build_company_context_block(company_context)
    role_instructions = _CATEGORY_PROMPTS[category](category, company_context)
    mandate = _creative_mandate()
    fmt = _output_format(category)

    return (
        f"You are a senior creative advertising director, brand strategist, "
        f"and campaign ideation expert.\n\n"
        f"{context_block}\n\n"
        f"{role_instructions}\n\n"
        f"{mandate}\n\n"
        f"{fmt}\n\n"
        f"Remember: You are not a text generator — you are a creative director "
        f"producing award-worthy marketing."
    )
