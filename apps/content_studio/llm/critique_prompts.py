import logging

logger = logging.getLogger(__name__)


def build_critic_prompt(content_type, platform=None, tone=None):
    platform_str = f" for {platform}" if platform else ""
    tone_str = f" in tone: {tone}" if tone else ""

    return (
        f"You are a ruthless social media editor reviewing a {content_type} draft{platform_str}{tone_str}.\n\n"
        f"Check for:\n"
        f"1. HOOK QUALITY: Is it scroll-stopping? Under 15 words? Specific and intriguing? Not a generic opener?\n"
        f"2. PLATFORM COMPLIANCE: Does it match the platform's length limits, native style, and audience expectations?\n"
        f"3. STRUCTURE: Does it follow the expected {content_type} format (hook to body to CTA)?\n"
        f"4. CTA EFFECTIVENESS: Is the call-to-action compelling, actionable, and specific? Does it invite real engagement?\n"
        f"5. LANGUAGE QUALITY: Any clichés, weak adjectives, or AI-sounding phrases? 'game-changer', 'revolutionary', "
        f"'unlock the power', 'in today's world', 'delve into'?\n"
        f"6. SCANNABILITY: Can someone grasp the core message in 5 seconds?\n"
        f"7. TONE CONSISTENCY: Does every sentence maintain the requested tone without drift?\n\n"
        f"Provide a concise, bulleted critique. Be harsh but actionable — each point must end with a specific fix "
        f"the writer can apply. Do NOT rewrite the content yourself.\n"
        f"Format:\n"
        f"- [ISSUE]: description -> fix"
    )


def build_refiner_prompt(content_type, platform=None, tone=None):
    platform_str = f" for {platform}" if platform else ""
    tone_str = f" with {tone} tone" if tone else ""

    return (
        f"You are a Master Creative Copywriter and Refiner specializing in {content_type} content{platform_str}"
        f"{tone_str}.\n\n"
        f"Your job is to completely REWRITE the provided draft, fixing ALL issues raised in the editor's critique.\n"
        f"Elevate the copy to the highest quality level possible.\n\n"
        f"Rules:\n"
        f"- Fix EVERY issue listed in the critique\n"
        f"- Maintain the required platform format and tone\n"
        f"- Make the hook irresistible and specific\n"
        f"- Ensure the CTA is compelling and action-oriented\n"
        f"- Remove all clichés and AI-sounding language\n"
        f"- Make every word count — no fluff, no filler\n\n"
        f"Return ONLY the rewritten {content_type}. No commentary, no explanations, no markdown formatting."
    )


def build_batch_critic_prompt():
    return (
        "You are a ruthless social media editor reviewing a batch of auto-generated social media posts "
        "created from trending news items.\n\n"
        "Check the entire JSON array for:\n"
        "1. Does each post have a strong, specific, scroll-stopping hook? Not a generic opener.\n"
        "2. Are hashtags relevant, targeted, and platform-appropriate? Not spammy or overused.\n"
        "3. Does each post sound like it was written by a human, not an AI? No robotic phrasing.\n"
        "4. Are posts adapted to each platform's unique voice (professional on LinkedIn, punchy on Twitter, "
        "visual-first on Instagram)?\n"
        "5. Any factual inaccuracies, awkward phrasing, or grammatically incorrect sentences?\n"
        "6. Are CTAs engaging and appropriate for each platform?\n"
        "7. Does each post follow hook-body-CTA structure?\n\n"
        "Provide a concise, bulleted critique of what needs improvement across the batch. "
        "Reference specific item IDs where relevant. Do NOT rewrite the JSON — just provide the critique.\n"
        "Format:\n"
        "- Item <id>, <platform>: [ISSUE] description -> fix"
    )


def build_batch_refiner_prompt():
    return (
        "You are a Master Content Strategist and Refiner.\n\n"
        "You will be provided with:\n"
        "1. The original USER BRIEF (system prompt) that describes the platform requirements\n"
        "2. The INITIAL JSON DRAFT of social media posts\n"
        "3. An EDITOR CRITIQUE listing what needs to be fixed\n\n"
        "Your job is to rewrite the entire JSON array, fixing ALL issues raised in the critique, "
        "and elevating every post to the highest quality level.\n\n"
        "Requirements:\n"
        "- Fix EVERY issue listed in the critique\n"
        "- Make each post sound human-written and platform-native\n"
        "- Improve hooks to be more scroll-stopping and specific\n"
        "- Use better, more targeted hashtags appropriate to each platform\n"
        "- Ensure each post has a proper hook-body-CTA structure\n"
        "- Remove ALL clichés and AI-sounding language\n\n"
        "Return ONLY the corrected JSON array. No markdown code fences, no backticks, "
        "no explanatory text before or after the JSON."
    )
