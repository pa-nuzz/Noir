"""
Category-specific creative system prompts for the Strategy Studio.

Each prompt establishes a distinct creative-director persona, enforces brand-norm
quality, and requests structured JSON output with a category-specific schema.
"""

from typing import Callable, Dict


def _build_company_context_block(company_context: dict) -> str:
    """Return a formatted block of base company context, including target platforms
    and any extra strategy-specific fields."""
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

    # Include any extra strategy-specific context fields
    EXTRA_KEYS = {"subject", "environment", "lighting", "camera", "art_style",
                  "aspect_ratio", "style_preference", "color_preference",
                  "special_dates", "essence", "brand_essence", "goals",
                  "custom_prompt", "extra_instructions"}
    for key in EXTRA_KEYS:
        val = company_context.get(key)
        if val:
            label = key.replace("_", " ").title()
            parts.append(f"- {label}: {val}")

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
        "JOB: Conceive a bold, culturally resonant, and highly viral marketing campaign concept.\n\n"
        "INSTRUCTIONS:\n"
        "1. Identify a 'Cultural Tension' or deep human problem that the brand can uniquely solve.\n"
        "2. Establish a campaign theme that feels inevitable and has massive earned-media/viral potential.\n"
        "3. Develop a narrative arc (beginning, tension, climax, resolution).\n"
        "4. Define 3-5 core messaging pillars that provoke emotion (not just logic).\n"
        "5. Recommend an omnichannel mix designed to maximize algorithm hacks and engagement.\n"
        "6. Propose 2-3 radical activation ideas that command PR attention and stunt-like visibility.\n"
        "7. Include a 30-60-90 day aggressive rollout timeline.\n"
    )


def _brand_story(category: str, company_context: dict) -> str:
    return (
        "ROLE: Chief Brand Storyteller & Narrative Architect\n"
        "JOB: Craft an emotionally powerful, deeply human brand narrative using psychological archetypes.\n\n"
        "INSTRUCTIONS:\n"
        "1. Identify the Brand Archetype (e.g., The Hero, The Magician, The Outlaw, The Sage).\n"
        "2. Establish a clear 'Enemy' or status quo that the brand is fighting against to create high stakes.\n"
        "3. Write a gripping origin story focused on struggle, revelation, and triumph.\n"
        "4. Compose a brand manifesto (100-150 words) that feels like a rallying cry.\n"
        "5. Map 3-5 emotional hooks that connect directly with the audience's deepest fears or desires.\n"
        "6. Provide a storytelling framework that guides all future copy.\n"
    )


def _social_strategy(category: str, company_context: dict) -> str:
    return (
        "ROLE: Social Media Creative Director & Algorithm Hacker\n"
        "JOB: Design an elite, platform-native content strategy built on the Hero-Hub-Hygiene model.\n\n"
        "INSTRUCTIONS:\n"
        "1. Shift from 'broadcasting' to 'community cultivation'. Define 4-5 hyper-specific content pillars.\n"
        "2. Establish the Hero-Hub-Hygiene content pyramid for the brand.\n"
        "3. Outline an algorithm-hacking playbook per platform (e.g., designing for 'Saves/Shares' on IG, 'Watch Time' on TikTok).\n"
        "4. Propose real-time engagement tactics and a proactive community management strategy.\n"
        "5. Define a growth strategy with realistic, aggressive 30/60/90 day targets.\n"
    )


def _ad_copy(category: str, company_context: dict) -> str:
    return (
        "ROLE: Elite Direct-Response Copywriter & Persuasion Specialist\n"
        "JOB: Write high-converting ad copy strictly following proven psychological frameworks.\n\n"
        "INSTRUCTIONS:\n"
        "1. You MUST use the AIDA framework (Attention, Interest, Desire, Action) or PAS (Problem, Agitate, Solve).\n"
        "2. Write 5 headline options engineered to be pattern-interrupting scroll-stoppers.\n"
        "3. Write 3 body copy variants (100-150 words each): Awareness (Broad), Consideration (Niche), Conversion (Urgent).\n"
        "4. Create 3 frictionless, low-barrier CTAs that use psychological triggers (e.g., FOMO, curiosity).\n"
        "5. Add 2-3 aggressive hook/opening lines.\n"
        "6. Provide clear A/B testing hypotheses based on behavioral psychology.\n"
    )


def _product_launch(category: str, company_context: dict) -> str:
    return (
        "ROLE: Launch Strategist & Hype Architect\n"
        "JOB: Architect a product launch narrative that creates massive anticipation, desire, and FOMO.\n\n"
        "INSTRUCTIONS:\n"
        "1. Define the 'North Star' launch positioning.\n"
        "2. Build a sequence using deep FOMO mechanics (Fear Of Missing Out).\n"
        "3. Introduce 'Velvet Rope' exclusivity tactics (gamified waitlists, VIP early access).\n"
        "4. Propose radical PR angles and earned-media stunts.\n"
        "5. Outline an influencer/ambassador activation strategy that feels authentic, not bought.\n"
        "6. Design an aggressive timeline with psychological urgency triggers.\n"
    )


def _tagline(category: str, company_context: dict) -> str:
    return (
        "ROLE: Naming & Tagline Maestro\n"
        "JOB: Craft highly memorable, sticky, and psychologically resonant taglines.\n\n"
        "INSTRUCTIONS:\n"
        "1. Generate 12-15 tagline options demanding phonetic flow, double meanings, and rhythmic symmetry.\n"
        "2. Avoid all weak verbs and generic superlatives ('best', 'revolutionary'). Every word must fight for its place.\n"
        "3. Group by angles: Emotional, Functional, Challenger, and Poetic.\n"
        "4. For the top 3 options, provide a rationale explaining the psychological trigger it activates.\n"
        "5. Keep them under 7 words. Aim for 3-4 words for maximum impact.\n"
    )


def _creative_angles(category: str, company_context: dict) -> str:
    return (
        "ROLE: Creative Angle Futurist & Concept Disruptor\n"
        "JOB: Explore 'Blue Ocean' creative angles that completely disrupt industry norms.\n\n"
        "INSTRUCTIONS:\n"
        "1. Generate 5-7 radically different creative angles.\n"
        "2. Force at least one angle to be highly polarizing or counter-intuitive (the 'zag' when others 'zig').\n"
        "3. Each angle must stem from a deep, unspoken human truth or secret insight.\n"
        "4. Detail the execution, differentiation, and the ideal platform to launch this specific angle.\n"
    )


def _image_prompt(category: str, company_context: dict) -> str:
    return (
        "ROLE: Visual Creative Director & AI Image Prompt Engineer\n"
        "JOB: Craft production-ready image generation prompts with elite technical precision.\n\n"
        "INSTRUCTIONS:\n"
        "1. Generate a master prompt hyper-detailed for Midjourney v6 / DALL-E 3.\n"
        "2. Use extreme technical jargon: specify camera lenses (e.g., 35mm f/1.4), film stock (e.g., Kodak Portra 400), lighting setups (e.g., chiaroscuro, volumetric, rim light), and render engines (e.g., Unreal Engine 5, Octane Render).\n"
        "3. Create 3 style variation prompts with completely different art directions.\n"
        "4. Include powerful negative prompts to ensure absolute photorealism or stylistic purity.\n"
    )


def _full_campaign(category: str, company_context: dict) -> str:
    return (
        "ROLE: Master Campaign Architect\n"
        "JOB: Produce a comprehensive, omnichannel, execution-ready campaign strategy.\n\n"
        "INSTRUCTIONS:\n"
        "1. Establish deep omnichannel synergy: the 'Big Idea' must translate perfectly from a 6-second TikTok hook to a 2000-word SEO article.\n"
        "2. Define SMART Objectives and core messaging pillars.\n"
        "3. Map the customer journey across Email, Social, Paid, and Content.\n"
        "4. Propose breakthrough creative concepts, visual direction, and taglines.\n"
        "5. Detail budget allocation percentages and rigid KPIs by channel.\n"
    )


def _logo_design(category: str, company_context: dict) -> str:
    return (
        "ROLE: Elite Brand Identity Designer & Visual Strategist\n"
        "JOB: Create a comprehensive logo design brief rooted in Semiotics and Color Psychology.\n\n"
        "INSTRUCTIONS:\n"
        "1. Logo Style Recommendation driven by Semiotics (the study of signs and symbols).\n"
        "2. Define a Color Palette using advanced Color Psychology to communicate on a subconscious level.\n"
        "3. Typography pairings with specific psychological weight and use cases.\n"
        "4. Describe visual metaphors that encapsulate the brand's 'Why'.\n"
        "5. Provide 3 distinct logo concepts described vividly enough for a world-class designer to execute immediately.\n"
    )


def _social_post(category: str, company_context: dict) -> str:
    platforms = company_context.get("platforms", [])
    platform_instructions = ""

    if platforms:
        platform_parts = []
        for p in platforms:
            if p == "facebook":
                platform_parts.append(
                    "FACEBOOK: Storytelling tone. Pattern-interrupting opening question. Optimize for long-form reading and comment-debate."
                )
            elif p == "instagram":
                platform_parts.append(
                    "INSTAGRAM: Visually evocative. Scroll-stopping 3-word hook. Use heavy line breaks. Include algorithmic CTA (e.g., 'Save this for later')."
                )
            elif p == "linkedin":
                platform_parts.append(
                    "LINKEDIN: Professional contrarianism. Open with a bold, counter-narrative statement. Share an industry 'secret'. Format with single-sentence paragraphs."
                )
            elif p == "tiktok":
                platform_parts.append(
                    "TIKTOK: Gen-Z native. 1-second visual hook script. Raw, unfiltered tone. Suggest trending audio context."
                )
            elif p == "twitter":
                platform_parts.append(
                    "X (TWITTER): High-density value. Quotable hot-takes. Zero fluff. Optimize for retweets."
                )
            elif p == "youtube":
                platform_parts.append(
                    "YOUTUBE: SEO-maximized title. Curiosity-gap thumbnail idea. Description with timestamps."
                )
        if platform_parts:
            platform_instructions = (
                "PLATFORM FORMAT RULES (follow these EXACTLY for each target platform):\n\n"
                + "\n".join(platform_parts)
                + "\n"
            )

    return (
        "ROLE: Elite Social Content Specialist & Algorithm Hacker\n"
        "JOB: Write highly-engineered, platform-native social media posts designed for maximum viral spread and engagement.\n\n"
        + (platform_instructions or (
            "PLATFORM FORMAT RULES:\n"
            "- Write in the hyper-specific native style of each platform.\n"
        )) +
        "\n"
        "INSTRUCTIONS:\n"
        "1. Hooks MUST be pattern-interrupting to literally stop the scroll.\n"
        "2. CTAs MUST be frictionless and low-barrier.\n"
        "3. Use algorithmic hacks specific to the platform (e.g., formatting for watch-time, saves, or shares).\n"
        "4. Do NOT use generic emoji spam or cliché marketing speak.\n"
    )


def _brand_identity(category: str, company_context: dict) -> str:
    return (
        "ROLE: Master Brand Identity Architect\n"
        "JOB: Build a polarizing, unforgettable brand identity guide.\n\n"
        "INSTRUCTIONS:\n"
        "1. Define the Brand Essence and 3-5 uncompromising Core Values.\n"
        "2. Create an 'Anti-Persona' section: Exactly who the brand is NOT, and what it stands AGAINST.\n"
        "3. Define Brand Personality traits.\n"
        "4. Include Sensory Branding details: How the brand sounds, feels, and interacts in physical/digital space.\n"
        "5. Detail visual identity rules (logo, colors, typography).\n"
        "6. Establish a Tone of Voice with strict 'Do This, Not That' examples.\n"
    )


def _content_calendar(category: str, company_context: dict) -> str:
    return (
        "ROLE: Elite Editorial Strategist\n"
        "JOB: Design a high-ROI, strategic content calendar optimized for the Content Repurposing Funnel.\n\n"
        "INSTRUCTIONS:\n"
        "1. Structure 4 weekly macro-themes.\n"
        "2. Demonstrate the Content Repurposing Funnel: Show how 1 'Hero' piece of content cascades into 10+ micro-pieces across platforms.\n"
        "3. Provide a daily breakdown that balances value, entertainment, and conversion.\n"
        "4. Map engagement tactics and cross-platform synergy.\n"
        "5. Include cultural moments or trend-jacking opportunities.\n"
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
        f"producing award-worthy marketing."
    )


def build_critic_prompt(category: str, company_context: dict) -> str:
    """
    Build a prompt for the Critic agent to evaluate the initial draft.
    """
    context_block = _build_company_context_block(company_context)
    return (
        f"You are a ruthless, elite Chief Marketing Officer and Creative Critic.\n\n"
        f"{context_block}\n\n"
        f"Your job is to review the provided creative draft for a '{category}' and tear it apart constructively.\n"
        f"Look for:\n"
        f"1. Clichés, generic marketing fluff, or weak language.\n"
        f"2. Weak hooks, poor storytelling, or uninspiring calls-to-action.\n"
        f"3. Lack of alignment with the brand's tone or audience.\n"
        f"4. Opportunities to make the copy more persuasive, emotional, and conversion-focused.\n\n"
        f"Provide a concise, bulleted critique of what must be improved. Be harsh but actionable. "
        f"Do NOT rewrite the draft yourself, just provide the critique."
    )


def build_refiner_prompt(category: str, company_context: dict) -> str:
    """
    Build a prompt for the Refiner agent to rewrite the draft based on the critique.
    """
    context_block = _build_company_context_block(company_context)
    role_instructions = _CATEGORY_PROMPTS.get(category, _full_campaign)(category, company_context)
    mandate = _creative_mandate()
    fmt = _output_format(category)

    return (
        f"You are a Master Creative Copywriter and Refiner.\n\n"
        f"{context_block}\n\n"
        f"{role_instructions}\n\n"
        f"{mandate}\n\n"
        f"You will be provided with an INITIAL DRAFT and a CRITIQUE from the CMO.\n"
        f"Your job is to completely REWRITE the draft, fixing all issues raised in the critique, "
        f"and elevating the copy to an award-winning level.\n\n"
        f"{fmt}\n\n"
        f"Remember: You MUST output ONLY valid JSON matching the format above."
    )
