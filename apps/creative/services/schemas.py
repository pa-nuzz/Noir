"""
Per-strategy input schemas for the Strategy Studio chatbot.

Each strategy type defines its own set of input fields (steps) that are
served to the frontend via API. The frontend renders a dynamic chatbot
based on the schema for the selected strategy type.

Each step can have:
  - key: unique field identifier
  - label: user-facing label
  - type: input, textarea, option, multi, datetime
  - max_length: character limit for input/textarea (optional)
  - required: boolean
  - extra: boolean — when True, shown in an expandable "Extra Inputs" section
  - placeholder: optional placeholder text
  - options: for option/multi types
"""

STRATEGY_INPUT_SCHEMAS = {
    "full_campaign": {
        "label": "Full Campaign Strategy",
        "steps": [
            {"key": "title", "label": "Campaign Title", "type": "input", "max_length": 200, "required": True, "placeholder": "e.g., Dashain 2082 Campaign"},
            {"key": "goals", "label": "Campaign Goals & Objectives", "type": "textarea", "max_length": 2000, "required": True, "placeholder": "Describe your campaign goals, objectives, and any specific requirements..."},
            {"key": "target_audience", "label": "Target Audience", "type": "input", "max_length": 500, "required": True, "placeholder": "e.g., Urban millennials, SME owners, Gen Z in Kathmandu"},
            {"key": "tone", "label": "Tone", "type": "option", "required": True, "options": [["professional", "Professional"], ["casual", "Casual"], ["creative", "Creative"], ["urgent", "Urgent"]]},
            {"key": "platforms", "label": "Platforms", "type": "multi", "required": True, "options": [["facebook", "Facebook"], ["instagram", "Instagram"], ["linkedin", "LinkedIn"], ["twitter", "X (Twitter)"], ["tiktok", "TikTok"], ["youtube", "YouTube"]]},
            {"key": "scheduled_at", "label": "Schedule", "type": "datetime", "required": False, "extra": True, "placeholder": "Optional — pick a publish date"},
            {"key": "custom_prompt", "label": "Extra Instructions", "type": "textarea", "max_length": 1000, "required": False, "extra": True, "placeholder": "Any additional instructions, constraints, or specific directions for the AI..."},
        ],
    },
    "campaign_idea": {
        "label": "Marketing Campaign Ideas",
        "steps": [
            {"key": "title", "label": "Campaign Title", "type": "input", "max_length": 200, "required": True, "placeholder": "e.g., Monsoon 2082 Campaign"},
            {"key": "goals", "label": "Campaign Goals & Context", "type": "textarea", "max_length": 2000, "required": True, "placeholder": "What is the cultural tension or problem this campaign should address?"},
            {"key": "target_audience", "label": "Target Audience", "type": "input", "max_length": 500, "required": True, "placeholder": "e.g., Gen Z, working professionals, rural communities"},
            {"key": "tone", "label": "Tone", "type": "option", "required": True, "options": [["professional", "Professional"], ["casual", "Casual"], ["creative", "Creative"], ["urgent", "Urgent"]]},
            {"key": "platforms", "label": "Platforms", "type": "multi", "required": False, "extra": True, "options": [["facebook", "Facebook"], ["instagram", "Instagram"], ["linkedin", "LinkedIn"], ["twitter", "X (Twitter)"], ["tiktok", "TikTok"], ["youtube", "YouTube"]]},
            {"key": "custom_prompt", "label": "Extra Instructions", "type": "textarea", "max_length": 1000, "required": False, "extra": True, "placeholder": "Any additional instructions, constraints, or specific directions for the AI..."},
        ],
    },
    "brand_story": {
        "label": "Brand Storytelling Concepts",
        "steps": [
            {"key": "title", "label": "Brand / Story Title", "type": "input", "max_length": 200, "required": True, "placeholder": "e.g., The Origin of [Brand]"},
            {"key": "goals", "label": "Brand Background & Context", "type": "textarea", "max_length": 2000, "required": True, "placeholder": "Tell us about the brand's history, founding story, mission, and what makes it unique..."},
            {"key": "target_audience", "label": "Target Audience", "type": "input", "max_length": 500, "required": True, "placeholder": "Who are we telling this story to?"},
            {"key": "tone", "label": "Storytelling Tone", "type": "option", "required": True, "options": [["professional", "Professional"], ["casual", "Casual"], ["creative", "Creative"], ["urgent", "Urgent"]]},
            {"key": "custom_prompt", "label": "Extra Instructions", "type": "textarea", "max_length": 1000, "required": False, "extra": True, "placeholder": "Any additional instructions, constraints, or specific directions for the AI..."},
        ],
    },
    "social_strategy": {
        "label": "Social Media Content Strategy",
        "steps": [
            {"key": "title", "label": "Strategy Title", "type": "input", "max_length": 200, "required": True, "placeholder": "e.g., Q3 2082 Social Strategy"},
            {"key": "goals", "label": "Goals & Current Situation", "type": "textarea", "max_length": 2000, "required": True, "placeholder": "What are your social media goals? Current follower counts, engagement rates, pain points..."},
            {"key": "target_audience", "label": "Target Audience", "type": "input", "max_length": 500, "required": True, "placeholder": "e.g., Millennials, Gen Z, B2B buyers"},
            {"key": "tone", "label": "Brand Voice", "type": "option", "required": True, "options": [["professional", "Professional"], ["casual", "Casual"], ["creative", "Creative"], ["urgent", "Urgent"]]},
            {"key": "platforms", "label": "Platforms", "type": "multi", "required": True, "options": [["facebook", "Facebook"], ["instagram", "Instagram"], ["linkedin", "LinkedIn"], ["twitter", "X (Twitter)"], ["tiktok", "TikTok"], ["youtube", "YouTube"]]},
            {"key": "custom_prompt", "label": "Extra Instructions", "type": "textarea", "max_length": 1000, "required": False, "extra": True, "placeholder": "Any additional instructions, constraints, or specific directions for the AI..."},
        ],
    },
    "ad_copy": {
        "label": "Ad Copy Variations",
        "steps": [
            {"key": "title", "label": "Ad Campaign Title", "type": "input", "max_length": 200, "required": True, "placeholder": "e.g., Summer Sale 2082"},
            {"key": "goals", "label": "Offer & Campaign Details", "type": "textarea", "max_length": 2000, "required": True, "placeholder": "Describe the product/service, key offer, USP, and what makes this different from competitors..."},
            {"key": "target_audience", "label": "Target Audience", "type": "input", "max_length": 500, "required": True, "placeholder": "e.g., Online shoppers, business owners, parents"},
            {"key": "tone", "label": "Ad Tone", "type": "option", "required": True, "options": [["professional", "Professional"], ["casual", "Casual"], ["creative", "Creative"], ["urgent", "Urgent"]]},
            {"key": "platforms", "label": "Target Platforms", "type": "multi", "required": False, "extra": True, "options": [["facebook", "Facebook"], ["instagram", "Instagram"], ["linkedin", "LinkedIn"], ["twitter", "X (Twitter)"], ["tiktok", "TikTok"], ["youtube", "YouTube"]]},
            {"key": "custom_prompt", "label": "Extra Instructions", "type": "textarea", "max_length": 1000, "required": False, "extra": True, "placeholder": "Any additional instructions, constraints, or specific directions for the AI..."},
        ],
    },
    "product_launch": {
        "label": "Product Launch Ideas",
        "steps": [
            {"key": "title", "label": "Product / Launch Name", "type": "input", "max_length": 200, "required": True, "placeholder": "e.g., SmartHome X Launch"},
            {"key": "goals", "label": "Product Details & Launch Context", "type": "textarea", "max_length": 2000, "required": True, "placeholder": "Describe the product, key features, target market, launch date, and any existing buzz..."},
            {"key": "target_audience", "label": "Target Audience", "type": "input", "max_length": 500, "required": True, "placeholder": "e.g., Early adopters, tech enthusiasts, enterprise buyers"},
            {"key": "tone", "label": "Launch Tone", "type": "option", "required": True, "options": [["professional", "Professional"], ["casual", "Casual"], ["creative", "Creative"], ["urgent", "Urgent"]]},
            {"key": "platforms", "label": "Launch Platforms", "type": "multi", "required": False, "extra": True, "options": [["facebook", "Facebook"], ["instagram", "Instagram"], ["linkedin", "LinkedIn"], ["twitter", "X (Twitter)"], ["tiktok", "TikTok"], ["youtube", "YouTube"]]},
            {"key": "custom_prompt", "label": "Extra Instructions", "type": "textarea", "max_length": 1000, "required": False, "extra": True, "placeholder": "Any additional instructions, constraints, or specific directions for the AI..."},
        ],
    },
    "tagline": {
        "label": "Taglines & Slogans",
        "steps": [
            {"key": "title", "label": "Brand / Campaign Name", "type": "input", "max_length": 200, "required": True, "placeholder": "e.g., Mountain Peak Tea"},
            {"key": "goals", "label": "Brand Essence & Direction", "type": "textarea", "max_length": 2000, "required": True, "placeholder": "Describe the brand's personality, what it stands for, and the feeling you want the tagline to evoke..."},
            {"key": "tone", "label": "Desired Tone", "type": "option", "required": True, "options": [["professional", "Professional"], ["casual", "Casual"], ["creative", "Creative"], ["urgent", "Urgent"]]},
            {"key": "custom_prompt", "label": "Extra Instructions", "type": "textarea", "max_length": 1000, "required": False, "extra": True, "placeholder": "Any additional instructions, constraints, or specific directions for the AI..."},
        ],
    },
    "creative_angles": {
        "label": "Creative Angles",
        "steps": [
            {"key": "title", "label": "Campaign / Brief Title", "type": "input", "max_length": 200, "required": True, "placeholder": "e.g., Festival Campaign Angles"},
            {"key": "goals", "label": "Creative Brief", "type": "textarea", "max_length": 2000, "required": True, "placeholder": "Describe the brand, industry, product, and the challenge you want creative angles for..."},
            {"key": "target_audience", "label": "Target Audience", "type": "input", "max_length": 500, "required": True, "placeholder": "e.g., Gen Z, luxury buyers, budget-conscious shoppers"},
            {"key": "tone", "label": "Tone", "type": "option", "required": True, "options": [["professional", "Professional"], ["casual", "Casual"], ["creative", "Creative"], ["urgent", "Urgent"]]},
            {"key": "platforms", "label": "Platforms", "type": "multi", "required": False, "extra": True, "options": [["facebook", "Facebook"], ["instagram", "Instagram"], ["linkedin", "LinkedIn"], ["twitter", "X (Twitter)"], ["tiktok", "TikTok"], ["youtube", "YouTube"]]},
            {"key": "custom_prompt", "label": "Extra Instructions", "type": "textarea", "max_length": 1000, "required": False, "extra": True, "placeholder": "Any additional instructions, constraints, or specific directions for the AI..."},
        ],
    },
    "image_prompt": {
        "label": "Image Generation Prompt",
        "steps": [
            {"key": "title", "label": "Visual Concept Title", "type": "input", "max_length": 200, "required": True, "placeholder": "e.g., Himalayan Sunrise Product Shot"},
            {"key": "subject", "label": "Subject Description", "type": "textarea", "max_length": 2000, "required": True, "placeholder": "Describe the subject — pose, expression, styling, key elements..."},
            {"key": "environment", "label": "Environment & Background", "type": "input", "max_length": 500, "required": True, "placeholder": "e.g., Minimalist studio, mountain landscape, urban street"},
            {"key": "art_style", "label": "Art Style", "type": "option", "required": True, "options": [["photorealistic", "Photorealistic"], ["minimalist", "Minimalist"], ["cinematic", "Cinematic"], ["3d_render", "3D Render"], ["illustration", "Illustration"], ["abstract", "Abstract"]]},
            {"key": "aspect_ratio", "label": "Aspect Ratio", "type": "option", "required": True, "options": [["16:9", "16:9 (Landscape)"], ["4:5", "4:5 (Instagram)"], ["1:1", "1:1 (Square)"], ["9:16", "9:16 (Story/Reels)"], ["3:2", "3:2 (Print)"]]},
            {"key": "lighting", "label": "Lighting & Mood", "type": "input", "max_length": 500, "required": False, "extra": True, "placeholder": "e.g., Warm golden hour, dramatic chiaroscuro, soft diffused"},
            {"key": "camera", "label": "Camera & Composition", "type": "input", "max_length": 500, "required": False, "extra": True, "placeholder": "e.g., 35mm f/1.4, aerial drone shot, macro close-up"},
            {"key": "custom_prompt", "label": "Extra Instructions", "type": "textarea", "max_length": 1000, "required": False, "extra": True, "placeholder": "Any additional instructions, constraints, or specific directions for the AI..."},
        ],
    },
    "logo_design": {
        "label": "Logo Design Brief",
        "steps": [
            {"key": "title", "label": "Brand Name", "type": "input", "max_length": 200, "required": True, "placeholder": "e.g., Kathmandu Craft Brewery"},
            {"key": "goals", "label": "Brand Background & Industry", "type": "textarea", "max_length": 2000, "required": True, "placeholder": "Describe the brand, its industry, mission, target audience, and what makes it unique..."},
            {"key": "style_preference", "label": "Logo Style Preference", "type": "option", "required": False, "extra": True, "options": [["wordmark", "Wordmark (text-based)"], ["lettermark", "Lettermark (initials)"], ["emblem", "Emblem / Badge"], ["abstract", "Abstract Mark"], ["mascot", "Mascot"], ["combination", "Combination Mark"], ["no_preference", "No Preference / Surprise Me"]]},
            {"key": "color_preference", "label": "Color Preferences", "type": "input", "max_length": 500, "required": False, "extra": True, "placeholder": "e.g., Earth tones, blues and whites, bold and vibrant"},
            {"key": "custom_prompt", "label": "Extra Instructions", "type": "textarea", "max_length": 1000, "required": False, "extra": True, "placeholder": "Any additional instructions, constraints, or specific directions for the AI..."},
        ],
    },
    "post_content": {
        "label": "Social Media Post",
        "steps": [
            {"key": "title", "label": "Post Topic / Title", "type": "input", "max_length": 200, "required": True, "placeholder": "e.g., New Product Announcement"},
            {"key": "goals", "label": "Post Content & Message", "type": "textarea", "max_length": 2000, "required": True, "placeholder": "What do you want to say? Include key message, offer, or story you want to tell..."},
            {"key": "target_audience", "label": "Target Audience", "type": "input", "max_length": 500, "required": True, "placeholder": "e.g., Followers, customers, event attendees"},
            {"key": "tone", "label": "Post Tone", "type": "option", "required": True, "options": [["professional", "Professional"], ["casual", "Casual"], ["creative", "Creative"], ["urgent", "Urgent"], ["humorous", "Humorous"]]},
            {"key": "platforms", "label": "Platforms", "type": "multi", "required": True, "options": [["facebook", "Facebook"], ["instagram", "Instagram"], ["linkedin", "LinkedIn"], ["twitter", "X (Twitter)"], ["tiktok", "TikTok"], ["youtube", "YouTube"]]},
            {"key": "custom_prompt", "label": "Extra Instructions", "type": "textarea", "max_length": 1000, "required": False, "extra": True, "placeholder": "Any additional instructions, constraints, or specific directions for the AI..."},
        ],
    },
    "brand_identity": {
        "label": "Brand Identity Guide",
        "steps": [
            {"key": "title", "label": "Brand Name", "type": "input", "max_length": 200, "required": True, "placeholder": "e.g., Yeti Outfitters"},
            {"key": "goals", "label": "Brand Values & Vision", "type": "textarea", "max_length": 2000, "required": True, "placeholder": "Describe the brand's mission, core values, target audience, and what it stands for (and against)..."},
            {"key": "target_audience", "label": "Target Audience", "type": "input", "max_length": 500, "required": True, "placeholder": "e.g., Adventurers, young professionals, luxury consumers"},
            {"key": "tone", "label": "Brand Voice", "type": "option", "required": True, "options": [["professional", "Professional"], ["casual", "Casual"], ["creative", "Creative"], ["urgent", "Urgent"]]},
            {"key": "custom_prompt", "label": "Extra Instructions", "type": "textarea", "max_length": 1000, "required": False, "extra": True, "placeholder": "Any additional instructions, constraints, or specific directions for the AI..."},
        ],
    },
    "content_calendar": {
        "label": "Content Calendar",
        "steps": [
            {"key": "title", "label": "Calendar Title", "type": "input", "max_length": 200, "required": True, "placeholder": "e.g., July 2082 Content Calendar"},
            {"key": "goals", "label": "Monthly Theme & Goals", "type": "textarea", "max_length": 2000, "required": True, "placeholder": "What is the theme for this month? Any product launches, campaigns, or key messages?"},
            {"key": "target_audience", "label": "Target Audience", "type": "input", "max_length": 500, "required": True, "placeholder": "e.g., Existing customers, new prospects, festival shoppers"},
            {"key": "tone", "label": "Content Tone", "type": "option", "required": True, "options": [["professional", "Professional"], ["casual", "Casual"], ["creative", "Creative"], ["urgent", "Urgent"]]},
            {"key": "platforms", "label": "Platforms", "type": "multi", "required": True, "options": [["facebook", "Facebook"], ["instagram", "Instagram"], ["linkedin", "LinkedIn"], ["twitter", "X (Twitter)"], ["tiktok", "TikTok"], ["youtube", "YouTube"]]},
            {"key": "special_dates", "label": "Special Dates & Festivals", "type": "textarea", "max_length": 1000, "required": False, "extra": True, "placeholder": "e.g., Dashain, Tihar, Holi, New Year — any cultural moments to include"},
            {"key": "scheduled_at", "label": "Calendar Month", "type": "datetime", "required": False, "extra": True, "placeholder": "Pick the start date for this calendar"},
            {"key": "custom_prompt", "label": "Extra Instructions", "type": "textarea", "max_length": 1000, "required": False, "extra": True, "placeholder": "Any additional instructions, constraints, or specific directions for the AI..."},
        ],
    },
}


def get_strategy_schema(strategy_type: str) -> dict:
    """Return the input schema for a given strategy type, or None if not found."""
    schema = STRATEGY_INPUT_SCHEMAS.get(strategy_type)
    if schema:
        return {
            "label": schema["label"],
            "steps": schema["steps"],
            "has_extra": any(s.get("extra") for s in schema["steps"]),
        }
    return None


def get_all_strategy_schemas() -> dict:
    """Return all strategy schemas keyed by strategy type."""
    return {
        key: {
            "label": schema["label"],
            "steps": schema["steps"],
            "has_extra": any(s.get("extra") for s in schema["steps"]),
        }
        for key, schema in STRATEGY_INPUT_SCHEMAS.items()
    }
