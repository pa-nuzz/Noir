import json
import logging
import re

logger = logging.getLogger(__name__)


def generate_llm_content(user, topic, platforms, items, rule_id=None):
    from core.tenant import get_current_tenant
    from apps.content_studio.llm.llm_service import _call_llm_fatal, LLMPipelineError
    from apps.content_studio.llm.critique_prompts import build_batch_critic_prompt, build_batch_refiner_prompt
    from apps.content_studio.models import ContentItem

    platform_reqs = {
        'linkedin': 'linkedin: Professional, thought-leadership, 1300-2000 chars, 3-5 hashtags',
        'twitter': 'twitter: Concise, under 280 chars, 1-2 hashtags',
        'instagram': 'instagram: Visual-first, 150-220 chars, 5-8 hashtags',
        'facebook': 'facebook: Conversational, 150-500 chars, 2-4 hashtags',
        'tiktok': 'tiktok: Casual and punchy, under 100 chars, 1-3 hashtags',
        'youtube': 'youtube: Engaging, 200-500 chars, 2-4 hashtags',
    }

    req_strs = [platform_reqs.get(p, f'{p}: Standard social media post') for p in platforms if p in platform_reqs]
    if not req_strs:
        req_strs = [f'{p}: Standard social media post' for p in platforms]

    prompt_parts = []
    for item in items:
        part = f"ITEM {item.id}:\nTitle: {item.title or ''}\nSummary: {(item.ai_summary or item.content_cleaned or '')[:500]}\n"
        prompt_parts.append(part)

    system_prompt = (
        "You are a social media content strategist. For each item below, generate "
        "a platform-optimized post with relevant hashtags for each requested platform.\n\n"
        "Platform requirements:\n" + "\n".join(req_strs) + "\n\n"
        "For each item, return ONLY a valid JSON array:\n"
        "[\n  {\n"
        '    "id": <item_id>,\n'
        '    "platforms": {\n'
    )
    for p in platforms:
        system_prompt += f'      "{p}": {{"body": "...", "hashtags": "#tag1 #tag2"}},\n'
    system_prompt += (
        "    }\n  }\n]\n"
        "Do NOT include markdown code fences, backticks, or text outside the JSON."
    )

    user_prompt = "\n---\n".join(prompt_parts)

    try:
        initial = _call_llm_fatal('ideator', system_prompt, user_prompt)
        critic_sys = build_batch_critic_prompt()
        critic_user = f"USER BRIEF:\n{system_prompt}\n\nJSON DRAFT:\n{initial}"
        critique = _call_llm_fatal('critic', critic_sys, critic_user)
        refiner_sys = build_batch_refiner_prompt()
        refiner_user = (
            f"USER BRIEF:\n{system_prompt}\n\n"
            f"JSON DRAFT:\n{initial}\n\n"
            f"EDITOR CRITIQUE:\n{critique}\n\n"
            f"Please completely rewrite the entire JSON array, fixing all issues raised in the critique."
        )
        refined = _call_llm_fatal('refiner', refiner_sys, refiner_user)
        result = {"success": True, "error": None, "message": None, "content": refined}
    except LLMPipelineError as e:
        logger.error("3-agent pipeline failed for generate_llm_content: %s", e)
        return []

    from django.db import close_old_connections
    close_old_connections()

    gen_map = {}
    if result['success'] and result['content']:
        text = result['content'].strip()
        json_match = re.search(r'\[.*\]', text, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            gen_map = {entry['id']: entry for entry in parsed if 'id' in entry}

    created = []
    for item in items:
        entry = gen_map.get(item.id, {})
        entry_platforms = entry.get('platforms', {}) if isinstance(entry, dict) else {}

        for platform in platforms:
            pdata = entry_platforms.get(platform, {}) if isinstance(entry_platforms, dict) else {}
            post_body = pdata.get('body', '') if isinstance(pdata, dict) else ''
            hashtags = pdata.get('hashtags', '') if isinstance(pdata, dict) else ''

            if not post_body:
                continue

            ci = ContentItem.objects.create(
                user=user,
                workspace=get_current_tenant(),
                title=item.title[:255],
                content_type='full_post',
                body=post_body,
                platform=platform,
                status='draft',
                is_auto_generated=True,
                source_prompt=f'Generated from trending: {item.url}',
                tags=[hashtags] if hashtags else (item.ai_categories or []),
            )
            ci.metadata.update({
                'source': 'trending_automation',
                'feed_item_id': item.id,
                'source_url': item.url,
                'topic_id': topic.id if hasattr(topic, 'id') else None,
                'topic_name': topic.name if hasattr(topic, 'name') else '',
                'platform': platform,
            })
            if rule_id:
                ci.metadata['automation_rule_id'] = rule_id
            ci.save(update_fields=['metadata'])

            created.append(ci)
    return created
