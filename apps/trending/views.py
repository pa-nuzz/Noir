import json
import logging
import math
import re
from datetime import datetime

logger = logging.getLogger(__name__)

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.db.utils import OperationalError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from core.tenant import get_current_tenant

from .models import ContentSource, FeedItem, CurrentItem, Topic, UserActivityProfile, UserFeedInteraction
from .services.user_profiler import UserProfiler
from .services.content_generator import generate_llm_content


ALL_PLATFORMS = ['linkedin', 'twitter', 'instagram', 'facebook', 'tiktok']
PLATFORM_LIMITS = {
    'twitter': 280,
    'linkedin': 2000,
    'instagram': 220,
    'facebook': 500,
    'tiktok': 100,
    'youtube': 500,
}
PLATFORM_REQS = {
    'linkedin': 'Professional, 1300-2000 chars including hashtags, 3-5 hashtags',
    'twitter': 'Concise, under 280 chars including hashtags, 1-2 hashtags',
    'instagram': 'Visual-first, 150-220 chars including hashtags, 5-8 hashtags',
    'facebook': 'Conversational, 150-500 chars including hashtags, 2-4 hashtags',
    'tiktok': 'Casual and punchy, under 100 chars including hashtags, 1-3 hashtags',
    'youtube': 'Engaging, 200-500 chars including hashtags, 2-4 hashtags',
}


def _first_n_sentences(text, n=5):
    if not text:
        return ''
    parts = re.split(r'\n+', text.strip())
    if len(parts) < 2:
        parts = re.split(r'(?<=[.!?])\s+', text.strip())
    parts = [s.strip() for s in parts if len(s.strip()) > 3]
    return ' '.join(parts[:n])


def _scrape_article_text(url, fallback=''):
    try:
        import httpx
        from html.parser import HTMLParser

        resp = httpx.get(url, timeout=10.0, follow_redirects=True, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; IDA Trending Bot/1.0)',
        })
        resp.raise_for_status()
        html = resp.text

        class _TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self._text = []
                self._skip = False
            def handle_starttag(self, tag, attrs):
                if tag in ('script', 'style'):
                    self._skip = True
            def handle_endtag(self, tag):
                if tag in ('script', 'style'):
                    self._skip = False
            def handle_data(self, data):
                if not self._skip:
                    stripped = data.strip()
                    if stripped:
                        self._text.append(stripped)
            def get_text(self):
                return ' '.join(self._text)

        m = re.search(r'<article[^>]*>.*?</article>', html, re.IGNORECASE | re.DOTALL)
        extract_html = m.group(0) if m else (
            re.search(r'<body[^>]*>.*?</body>', html, re.IGNORECASE | re.DOTALL).group(0)
            if re.search(r'<body[^>]*>.*?</body>', html, re.IGNORECASE | re.DOTALL) else html
        )
        extractor = _TextExtractor()
        extractor.feed(extract_html)
        text = extractor.get_text()[:5000]
        return text
    except Exception as e:
        logger.warning("_scrape_article_text failed for URL %s: %s", url, e)
        return fallback


def _run_refine_pipeline(user, items, workspace=None):
    """Run the full refine pipeline per-item: scrape, LLM, create snapshots.
    Returns (True, {'batch_id': ...}) on success or (False, error_dict) on failure.
    """
    import uuid
    from .models import TrendingAutomationRule, CurrentsSnapshot

    try:
        rule_filter = {'user': user, 'is_active': True}
        if workspace:
            rule_filter['workspace'] = workspace
        topic_platforms = {
            r.topic_id: r.platforms
            for r in TrendingAutomationRule.objects.filter(
                **rule_filter,
            ).exclude(platforms=[])
        }
        all_platforms = sorted(set(p for plats in topic_platforms.values() for p in plats))
    except OperationalError:
        return (False, {'error': 'db_error'})

    if not all_platforms:
        from apps.social_accounts.models import SocialAccount
        connected = SocialAccount.objects.filter(
            user=user, is_active=True,
        ).values_list('platform', flat=True).distinct()
        connected_platforms = sorted(set(p for p in connected if p))
        if connected_platforms:
            all_platforms = connected_platforms
        else:
            return (False, {'error': 'no_platforms'})

    from apps.content_studio.llm.llm_service import _call_llm_fatal, LLMPipelineError
    from apps.content_studio.llm.critique_prompts import build_batch_critic_prompt, build_batch_refiner_prompt

    req_lines = [f'- {p}: {PLATFORM_REQS.get(p, "Standard post")}' for p in all_platforms]
    platform_entries = '\n'.join(f'      "{p}": {{"body": "...", "hashtags": "#tag1"}},' for p in all_platforms)
    req_block = '\n'.join(req_lines)
    plat_block = platform_entries

    # Build batched user prompt from ai_summary (no per-item re-scrape)
    item_summaries = []
    for item in items:
        summary = item.ai_summary or item.content_cleaned or item.content_raw or ''
        item_summaries.append(f"ITEM {item.id}:\nTitle: {item.title or ''}\nSummary: {summary[:500]}")
    user_prompt = "\n---\n".join(item_summaries)

    system_prompt = (
        "You are a social media content strategist. Generate platform-optimized posts for each item.\n\n"
        "Platforms:\n" + req_block + "\n\n"
        "For each item, return a JSON array (one entry per item):\n"
        "[\n  {\n"
        '    "id": <item_id>,\n'
        '    "platforms": {\n' + plat_block + "    }\n  }\n]\n"
        "Body length MUST include hashtags. Do not exceed the platform's character limit.\n"
        "No markdown, no backticks, no text outside the JSON."
    )

    batch_id = uuid.uuid4().hex
    new_snapshots = []
    length_rules = "\n".join(f"- {p}: {PLATFORM_LIMITS.get(p, 280)} chars max (body + hashtags)" for p in all_platforms)

    try:
        initial = _call_llm_fatal('ideator', system_prompt, user_prompt, max_tokens=3000)

        critic_user = f"Platform length rules:\n{length_rules}\n\nJSON DRAFT:\n{initial}"
        critique = _call_llm_fatal('critic', build_batch_critic_prompt(), critic_user, max_tokens=500)

        refiner_user = (
            f"Platform length rules:\n{length_rules}\n\n"
            f"JSON DRAFT:\n{initial}\n\n"
            f"EDITOR CRITIQUE:\n{critique}\n\n"
            f"Please completely rewrite the entire JSON array, fixing all issues raised in the critique."
        )
        refined = _call_llm_fatal('refiner', build_batch_refiner_prompt(), refiner_user, max_tokens=3000)

        text = refined.strip()
        m = re.search(r'\[.*\]', text, re.DOTALL)
        parsed = json.loads(m.group()) if m else []
        gen_map = {entry['id']: entry for entry in parsed if isinstance(entry, dict) and 'id' in entry}
    except (LLMPipelineError, json.JSONDecodeError, Exception) as e:
        logger.error("_run_refine_pipeline batch LLM failed: %s", e)
        return (False, {'error': 'llm_failed', 'reason': str(e)})

    for item in items:
        platforms_data = {}
        entry = gen_map.get(item.id, {})
        entry_platforms = entry.get('platforms', {}) if isinstance(entry, dict) else {}
        active = topic_platforms.get(item.topic_id, all_platforms)

        for p, info in entry_platforms.items():
            if p not in active or not isinstance(info, dict):
                continue
            body = (info.get('body', '') or '').strip()
            hashtags = info.get('hashtags', '')

            if not body:
                continue

            # Enforce platform length limits including hashtag budget
            ht_formatted = ' '.join(f'#{h.strip().lstrip("#")}' for h in hashtags.split() if h.strip()) if hashtags else ''
            ht_len = len(ht_formatted) + (1 if ht_formatted else 0)
            limit = PLATFORM_LIMITS.get(p, 280)
            max_body = limit - ht_len
            if max_body < 20:
                ht_formatted = ''
                max_body = limit
            if len(body) > max_body:
                body = body[:max_body]

            platforms_data[p] = {'body': body, 'hashtags': ht_formatted}

        new_snapshots.append(CurrentsSnapshot(
            user=user, feed_item=item, workspace=workspace,
            topic=item.topic, platforms_data=platforms_data, batch_id=batch_id,
        ))

    if new_snapshots:
        from django.db import close_old_connections, transaction
        close_old_connections()
        with transaction.atomic():
            CurrentsSnapshot.objects.filter(
                user=user, feed_item__in=items,
            ).delete()
            CurrentsSnapshot.objects.bulk_create(new_snapshots)

    return (True, {'batch_id': batch_id, 'item_errors': []})


@login_required
@require_GET
def feed_data(request):
    from .models import TrendingAutomationRule
    from core.tenant import get_current_tenant

    PAGE_SIZE = 40
    page = max(1, int(request.GET.get('page', 1) or 1))
    offset = (page - 1) * PAGE_SIZE

    topic_id = request.GET.get('topic_id')
    if topic_id:
        try:
            topic_id = int(topic_id)
        except (ValueError, TypeError):
            topic_id = None

    workspace = get_current_tenant()
    rule_filter = {'user': request.user, 'is_active': True}
    if workspace:
        rule_filter['workspace'] = workspace
    automation_topic_ids = list(
        TrendingAutomationRule.objects.filter(**rule_filter).values_list('topic_id', flat=True)
    )

    if topic_id and topic_id in automation_topic_ids:
        automation_topic_ids = [topic_id]

    if not automation_topic_ids:
        return JsonResponse({
            'items': [], 'total': 0,
            'needs_categories': True,
            'page': 1, 'total_pages': 0,
            'has_next': False, 'has_prev': False,
        })

    qs = FeedItem.objects.filter(
        is_duplicate=False,
        topic_id__in=automation_topic_ids,
    ).select_related('topic', 'source').order_by('-published_at')

    dismissed_ids = set(
        UserFeedInteraction.objects.filter(
            user=request.user, interaction_type='dismissed',
        ).values_list('feed_item_id', flat=True)
    )
    if dismissed_ids:
        qs = qs.exclude(id__in=dismissed_ids)

    total = qs.count()
    if total == 0:
        return JsonResponse({
            'items': [], 'total': 0,
            'collecting': True,
            'page': 1, 'total_pages': 0,
            'has_next': False, 'has_prev': False,
        })
    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = min(page, total_pages)
    offset = (page - 1) * PAGE_SIZE

    items = list(qs[offset:offset + PAGE_SIZE])

    bookmarked_ids = set(
        UserFeedInteraction.objects.filter(
            user=request.user,
            interaction_type='bookmarked',
            feed_item_id__in=[i.id for i in items],
        ).values_list('feed_item_id', flat=True)
    )

    data = []
    for item in items:
        data.append({
            'id': item.id,
            'title': item.title,
            'url': item.url,
            'author': item.author,
            'summary': _first_n_sentences(item.content_cleaned or item.content_raw or ''),
            'topic': {
                'id': item.topic.id if item.topic else None,
                'name': item.topic.name if item.topic else 'Uncategorized',
                'icon': item.topic.icon if item.topic else '📰',
                'color': item.topic.color if item.topic else '#94A3B8',
            } if item.topic else None,
            'source': item.source.name if item.source else 'Unknown',
            'score': item.trending_score,
            'is_bookmarked': item.id in bookmarked_ids,
            'published_at': item.published_at.isoformat() if item.published_at else None,
            'image_url': item.image_url or '',
        })

    return JsonResponse({
        'items': data,
        'total': total,
        'page': page,
        'total_pages': total_pages,
        'has_next': page < total_pages,
        'has_prev': page > 1,
    })


@login_required
@require_GET
def topic_list(request):
    from .models import TrendingAutomationRule
    from core.tenant import get_current_tenant
    topics = Topic.objects.filter(is_active=True).order_by('-subscriber_count')

    workspace = get_current_tenant()
    rule_filter = {'user': request.user, 'is_active': True}
    if workspace:
        rule_filter['workspace'] = workspace
    auto_ids = set(
        TrendingAutomationRule.objects.filter(**rule_filter).values_list('topic_id', flat=True)
    )

    data = []
    for topic in topics:
        data.append({
            'id': topic.id,
            'name': topic.name,
            'slug': topic.slug,
            'description': topic.description,
            'icon': topic.icon,
            'color': topic.color,
            'subscriber_count': topic.subscriber_count,
            'is_subscribed': topic.id in auto_ids,
        })

    return JsonResponse({'topics': data})





@login_required
@require_POST
def save_as_draft(request, item_id):
    feed_item = get_object_or_404(FeedItem, id=item_id, is_duplicate=False)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        body = {}

    platforms = body.get('platforms', [])
    platform_content = body.get('platform_content', {})

    if not platforms or not platform_content:
        return JsonResponse({'error': 'platforms and platform_content are required'}, status=400)

    from apps.content_studio.models import ContentItem

    created_items = []
    for platform in platforms:
        content = platform_content.get(platform, {})
        post_body = content.get('body', feed_item.ai_summary or feed_item.content_cleaned or feed_item.content_raw or '')
        hashtags = content.get('hashtags', '')

        item = ContentItem.objects.create(
            user=request.user,
            workspace=get_current_tenant(),
            title=feed_item.title[:255],
            content_type='full_post',
            body=post_body,
            platform=platform,
            status='draft',
            is_auto_generated=True,
            source_prompt=f'Imported from Currents: {feed_item.url}',
            tags=hashtags.split() if hashtags else (feed_item.ai_categories or []),
        )
        
        item.metadata.update({
            'source': 'trending',
            'feed_item_id': feed_item.id,
            'source_url': feed_item.url,
            'source_name': feed_item.source.name if feed_item.source else '',
            'platform': platform,
        })
        item.save(update_fields=['metadata'])

        # Adapt content for platform (translate + smart truncate)
        try:
            from apps.content_studio.services.content_service import ContentService
            hashtag_list = [h.strip().lstrip('#') for h in hashtags.split() if h.strip()] if hashtags else []
            cs = ContentService(request.user)
            cs.adapt_for_platform(item, platform, hashtags=hashtag_list)
        except Exception as e:
            logger.warning("save_as_draft: adaptation failed for platform %s: %s", platform, e)

        # Attach image from feed item
        if feed_item.image_url:
            try:
                import httpx
                from django.core.files.base import ContentFile
                from apps.media_assets.services import MediaService

                resp = httpx.get(feed_item.image_url, timeout=15.0, follow_redirects=True)
                resp.raise_for_status()

                filename = feed_item.image_url.rstrip('/').split('/')[-1].split('?')[0] or 'image.jpg'
                content_file = ContentFile(resp.content, name=filename)

                ms = MediaService(request.user)
                asset = ms.upload(
                    content_file,
                    title=f"Illustration: {feed_item.title[:50]}",
                )
                item.attachments.add(asset)
            except Exception as e:
                logger.warning("save_as_draft: failed to attach image for feed item %d: %s", feed_item.id, e)

        created_items.append(item.id)

    # Update user profile once
    from django.utils import timezone
    from .models import UserActivityProfile, UserFeedInteraction
    profile, _ = UserActivityProfile.objects.get_or_create(user=request.user)
    profile.last_analyzed_at = timezone.now()
    profile.save(update_fields=['last_analyzed_at'])

    UserFeedInteraction.objects.get_or_create(
        user=request.user, feed_item=feed_item, interaction_type='saved',
    )

    return JsonResponse({
        'content_item_ids': created_items,
        'count': len(created_items),
    })


@login_required
@require_POST
def dismiss_item(request, item_id):
    feed_item = get_object_or_404(FeedItem, id=item_id, is_duplicate=False)
    UserFeedInteraction.objects.get_or_create(
        user=request.user,
        feed_item=feed_item,
        interaction_type='dismissed',
    )
    return JsonResponse({'dismissed': True})


@login_required
@require_POST
def toggle_bookmark(request, item_id):
    feed_item = get_object_or_404(FeedItem, id=item_id, is_duplicate=False)

    existing = UserFeedInteraction.objects.filter(
        user=request.user,
        feed_item=feed_item,
        interaction_type='bookmarked',
    ).first()

    if existing:
        existing.delete()
        return JsonResponse({'bookmarked': False})

    UserFeedInteraction.objects.create(
        user=request.user,
        feed_item=feed_item,
        interaction_type='bookmarked',
    )
    return JsonResponse({'bookmarked': True})


@login_required
@require_GET
def currents_data(request):
    from .models import TrendingAutomationRule, CurrentsSnapshot
    from collections import OrderedDict
    from django.core.cache import cache
    from core.tenant import get_current_tenant

    workspace = get_current_tenant()
    rule_filter = {'user': request.user, 'is_active': True}
    if workspace:
        rule_filter['workspace'] = workspace

    rules = TrendingAutomationRule.objects.filter(**rule_filter)
    if not rules.exists():
        return JsonResponse({'items': [], 'total': 0, 'needs_automation': True})

    needs_platform = cache.get(f'needs_platform_{request.user.id}')
    if needs_platform:
        cache.delete(f'needs_platform_{request.user.id}')
        return JsonResponse({'items': [], 'total': 0, 'needs_platform': True})

    llm_error = cache.get(f'llm_error_{request.user.id}')
    if llm_error:
        cache.delete(f'llm_error_{request.user.id}')
        return JsonResponse({'items': [], 'total': 0, 'llm_error': llm_error})

    retry_info = cache.get(f'llm_retry_{request.user.id}')
    if retry_info and isinstance(retry_info, dict):
        return JsonResponse({
            'items': [], 'total': 0,
            'llm_retry': True,
            'retry_attempt': retry_info.get('attempt', 1),
        })

    snap_filter = {'user': request.user}
    if workspace:
        snap_filter['workspace'] = workspace
    latest = CurrentsSnapshot.objects.filter(
        **snap_filter,
    ).order_by('-created_at').values('batch_id', 'created_at').first()

    if not latest:
        return JsonResponse({
            'items': [], 'total': 0,
            'needs_feed_load': True,
        })

    snapshots = CurrentsSnapshot.objects.filter(
        user=request.user, batch_id=latest['batch_id'],
    ).select_related('feed_item__topic', 'feed_item__source')

    # Build response from snapshots
    ci_filter = {'user': request.user}
    if workspace:
        ci_filter['workspace'] = workspace
    ready_ids = set(
        CurrentItem.objects.filter(**ci_filter).values_list('feed_item_id', flat=True)
    )
    item_map = OrderedDict()

    for s in snapshots:
        feed = s.feed_item
        if feed.id not in item_map:
            topic = feed.topic
            item_map[feed.id] = {
                'id': feed.id,
                'title': feed.title,
                'url': feed.url,
                'author': feed.author,
                'summary': _first_n_sentences(feed.ai_summary or feed.content_cleaned or feed.content_raw or ''),
                'topic': {
                    'id': topic.id,
                    'name': topic.name,
                    'icon': topic.icon,
                    'color': topic.color,
                } if topic else None,
                'source': feed.source.name if feed.source else 'Unknown',
                'score': feed.trending_score,
                'is_queued': feed.id in ready_ids,
                'published_at': feed.published_at.isoformat() if feed.published_at else None,
                'image_url': feed.image_url or '',
                'generated_content': {},
                'active_platforms': [],
            }
        if s.platforms_data and isinstance(s.platforms_data, dict):
            item_map[feed.id]['generated_content'].update(s.platforms_data)

    for d in item_map.values():
        if d['generated_content']:
            d['active_platforms'] = list(d['generated_content'].keys())
        else:
            d['active_platforms'] = ALL_PLATFORMS

    return JsonResponse({
        'items': list(item_map.values()),
        'total': len(item_map),
        'generated_at': latest['created_at'].isoformat(),
        'batch_id': latest['batch_id'],
    })


@login_required
@require_POST
def currents_batch_action(request):
    import json
    from .models import CurrentsSnapshot, TrendingAutomationRule
    from apps.content_studio.models import ContentItem
    from core.tenant import get_current_tenant

    workspace = get_current_tenant()

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    batch_id = body.get('batch_id', '')
    action = body.get('action', 'draft')
    scheduled_at_str = body.get('scheduled_at')

    if not batch_id:
        return JsonResponse({'success': False, 'error': 'batch_id required'}, status=400)

    snap_filter = {'user': request.user, 'batch_id': batch_id}
    if workspace:
        snap_filter['workspace'] = workspace
    snapshots = CurrentsSnapshot.objects.filter(
        **snap_filter,
    ).select_related('feed_item', 'topic')

    if not snapshots.exists():
        return JsonResponse({'success': False, 'error': 'No snapshots found for this batch'}, status=404)

    processed = 0
    errors = []

    rule_filter = {'user': request.user, 'is_active': True}
    if workspace:
        rule_filter['workspace'] = workspace
    fallback_rules = list(TrendingAutomationRule.objects.filter(
        **rule_filter,
    ).exclude(platforms=[]).values('topic_id', 'platforms'))
    fallback_rule_map = {}
    for r in fallback_rules:
        fallback_rule_map.setdefault(r['topic_id'], []).extend(r['platforms'])

    for snap in snapshots:
        feed = snap.feed_item
        platforms_data = snap.platforms_data or {}

        # Fallback when LLM content is missing — use feed data
        if not platforms_data:
            platforms_data = {}
            for p in fallback_rule_map.get(snap.topic_id, []):
                platforms_data.setdefault(p, {})
            if not platforms_data:
                for plats in fallback_rule_map.values():
                    for p in plats:
                        platforms_data.setdefault(p, {})
            if not platforms_data:
                from apps.social_accounts.models import SocialAccount
                connected = SocialAccount.objects.filter(
                    user=request.user, is_active=True,
                ).values_list('platform', flat=True).distinct()
                for p in connected:
                    if p:
                        platforms_data[p] = {}

        for platform, content in platforms_data.items():
            if not isinstance(content, dict):
                content = {}
            body_text = content.get('body', '') or feed.ai_summary or feed.content_cleaned or feed.content_raw or ''
            hashtags = content.get('hashtags', '')

            if not body_text:
                continue

            try:
                existing = ContentItem.objects.filter(
                    user=request.user,
                    platform=platform,
                    metadata__source='currents',
                    metadata__feed_item_id=feed.id,
                ).first()
                if existing:
                    continue

                item = ContentItem.objects.create(
                    user=request.user,
                    workspace=workspace,
                    title=feed.title[:255],
                    content_type='full_post',
                    body=body_text,
                    platform=platform,
                    status='draft',
                    is_auto_generated=True,
                    source_prompt=f'Currents snapshot: {feed.url}',
                    tags=hashtags.split() if hashtags else [],
                )

                meta = {
                    'source': 'currents',
                    'feed_item_id': feed.id,
                    'source_url': feed.url,
                    'source_name': feed.source.name if feed.source else '',
                    'platform': platform,
                    'topic_id': snap.topic_id,
                    'topic_name': snap.topic.name if snap.topic else '',
                    'batch_id': batch_id,
                }
                item.metadata.update(meta)
                item.save(update_fields=['metadata'])

                # Adapt content for platform (translate + smart truncate)
                try:
                    from apps.content_studio.services.content_service import ContentService
                    hashtag_list = [h.strip().lstrip('#') for h in hashtags.split() if h.strip()] if hashtags else []
                    cs = ContentService(request.user)
                    cs.adapt_for_platform(item, platform, hashtags=hashtag_list)
                except Exception as e:
                    logger.warning("currents_batch_action: adaptation failed for platform %s: %s", platform, e)

                from apps.social_accounts.models import SocialAccount, SocialPost

                social_account = SocialAccount.objects.filter(
                    user=request.user,
                    platform=platform,
                    is_active=True,
                ).first()

                if social_account:
                    hashtag_list = [h.strip().lstrip('#') for h in hashtags.split() if h.strip()] if hashtags else []

                    post = SocialPost.objects.create(
                        user=request.user,
                        account=social_account,
                        content_item=item,
                        platform=platform,
                        content=item.body,
                        hashtags=hashtag_list,
                        status=item.status,
                        workspace=workspace,
                    )

                    if action == 'publish':
                        from apps.social_accounts.services import SocialService
                        svc = SocialService(request.user)
                        svc.publish_post(post.id)
                        item.status = 'published'
                        item.save(update_fields=['status'])

                    elif action == 'schedule':
                        if scheduled_at_str:
                            from datetime import datetime
                            try:
                                scheduled_dt = datetime.fromisoformat(scheduled_at_str)
                            except (ValueError, TypeError):
                                scheduled_dt = None
                            if scheduled_dt:
                                post.scheduled_at = scheduled_dt
                                post.save(update_fields=['scheduled_at'])
                                item.status = 'scheduled'
                                item.save(update_fields=['status'])

                processed += 1

            except Exception as e:
                errors.append(str(e))

    return JsonResponse({
        'success': True,
        'processed': processed,
        'errors': errors[:5],
    })


@login_required
@require_POST
def queue_for_publish(request, item_id):
    from core.tenant import get_current_tenant

    feed_item = get_object_or_404(FeedItem, id=item_id, is_duplicate=False)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        body = {}

    scheduled_str = body.get('scheduled_at')
    scheduled_dt = None
    if scheduled_str:
        try:
            scheduled_dt = datetime.fromisoformat(scheduled_str)
        except (ValueError, TypeError):
            pass

    platforms = body.get('platforms', [])
    platform_content = body.get('platform_content', {})

    workspace = get_current_tenant()
    ci_defaults = {
        'scheduled_at': scheduled_dt,
        'status': 'scheduled' if scheduled_dt else 'draft',
        'workspace': workspace,
    }
    ci_filter = {'user': request.user, 'feed_item': feed_item}
    if workspace:
        ci_filter['workspace'] = workspace
    ready, created = CurrentItem.objects.get_or_create(
        defaults=ci_defaults,
        **ci_filter,
    )

    if not created and scheduled_dt:
        ready.scheduled_at = scheduled_dt
        ready.status = 'scheduled'
        ready.save(update_fields=['scheduled_at', 'status'])

    # Store platform data in metadata
    ready.metadata = {
        'platforms': platforms,
        'platform_content': platform_content,
    }
    ready.save(update_fields=['metadata'])

    return JsonResponse({
        'queued': True,
        'ready_id': ready.id,
        'status': ready.status,
        'scheduled_at': ready.scheduled_at.isoformat() if ready.scheduled_at else None,
    })


@login_required
@require_POST
def dequeue_currents(request, item_id):
    from core.tenant import get_current_tenant
    workspace = get_current_tenant()
    ci_filter = {'user': request.user, 'feed_item_id': item_id}
    if workspace:
        ci_filter['workspace'] = workspace
    deleted, _ = CurrentItem.objects.filter(**ci_filter).delete()
    return JsonResponse({'deleted': bool(deleted)})


@login_required
@require_POST
def publish_currents(request, item_id):
    from core.tenant import get_current_tenant

    feed_item = get_object_or_404(FeedItem, id=item_id, is_duplicate=False)
    workspace = get_current_tenant()
    ci_filter = {'user': request.user, 'feed_item': feed_item}
    if workspace:
        ci_filter['workspace'] = workspace
    ready = CurrentItem.objects.filter(**ci_filter).first()

    if not ready:
        return JsonResponse({'error': 'Item not in currents queue'}, status=400)

    meta = ready.metadata or {}
    platform_content = meta.get('platform_content', {})
    platforms = meta.get('platforms', ['linkedin'])

    from apps.content_studio.models import ContentItem

    created_items = []

    for platform in platforms:
        content = platform_content.get(platform, {})
        post_body = content.get('body', '')
        hashtags = content.get('hashtags', '')

        if not post_body:
            # Fallback: regenerate via LLM if no stored content
            try:
                from apps.content_studio.services.content_service import ContentService
                prompt_parts = []
                if feed_item.title:
                    prompt_parts.append(f"Title: {feed_item.title}")
                summary = feed_item.ai_summary or feed_item.content_cleaned or ''
                if summary:
                    prompt_parts.append(f"Summary: {summary[:500]}")
                prompt = '\n\n'.join(prompt_parts)
                cs = ContentService(request.user)
                item = cs.generate_content(
                    'full_post', prompt,
                    platform=platform, tone='professional',
                    target_audience='industry professionals',
                    key_points=feed_item.title[:200],
                )
                if item:
                    item.title = feed_item.title[:255]
                    item.save(update_fields=['title'])
                    created_items.append(item.id)
                    continue
            except Exception:
                pass
            post_body = feed_item.ai_summary or feed_item.content_cleaned or feed_item.content_raw or ''

        item = ContentItem.objects.create(
            user=request.user,
            workspace=get_current_tenant(),
            title=feed_item.title[:255],
            content_type='full_post',
            body=post_body,
            platform=platform,
            status='draft',
            is_auto_generated=True,
            source_prompt=f'Scheduled from Currents: {feed_item.url}',
            tags=hashtags.split() if hashtags else (feed_item.ai_categories or []),
        )
        
        item.metadata.update({
            'source': 'trending',
            'feed_item_id': feed_item.id,
            'source_url': feed_item.url,
            'source_name': feed_item.source.name if feed_item.source else '',
            'platform': platform,
        })
        item.save(update_fields=['metadata'])

        # Adapt content for platform (translate + smart truncate)
        hashtag_list = [h.strip().lstrip('#') for h in hashtags.split() if h.strip()] if hashtags else []
        try:
            from apps.content_studio.services.content_service import ContentService
            cs = ContentService(request.user)
            cs.adapt_for_platform(item, platform, hashtags=hashtag_list)
        except Exception as e:
            logger.warning("publish_currents: adaptation failed for platform %s: %s", platform, e)
        
        # Attach image from feed item
        if feed_item.image_url:
            try:
                import httpx
                from django.core.files.base import ContentFile
                from apps.media_assets.services import MediaService

                resp = httpx.get(feed_item.image_url, timeout=15.0, follow_redirects=True)
                resp.raise_for_status()

                filename = feed_item.image_url.rstrip('/').split('/')[-1].split('?')[0] or 'image.jpg'
                content_file = ContentFile(resp.content, name=filename)

                ms = MediaService(request.user)
                asset = ms.upload(
                    content_file,
                    title=f"Illustration: {feed_item.title[:50]}",
                )
                item.attachments.add(asset)
            except Exception as e:
                logger.warning("publish_currents: failed to attach image for feed item %d: %s", feed_item.id, e)

        # Publish to social platform
        if platform:
            try:
                from apps.social_accounts.models import SocialAccount, SocialPost
                social_account = SocialAccount.objects.filter(
                    user=request.user, platform=platform, is_active=True,
                ).first()
                if social_account:
                    hashtag_list = [h.strip().lstrip('#') for h in hashtags.split() if h.strip()] if hashtags else []
                    post = SocialPost.objects.create(
                        user=request.user,
                        account=social_account,
                        content_item=item,
                        platform=platform,
                        content=item.body,
                        hashtags=hashtag_list,
                        status='published',
                        workspace=workspace,
                    )
                    from apps.social_accounts.services import SocialService
                    svc = SocialService(request.user)
                    svc.publish_post(post.id)
                    item.status = 'published'
                    item.save(update_fields=['status'])
            except Exception as e:
                logger.warning("publish_currents: failed to publish platform %s for feed item %d: %s", platform, feed_item.id, e)

        created_items.append(item.id)

    ready.status = 'published'
    ready.save(update_fields=['status'])

    UserFeedInteraction.objects.get_or_create(
        user=request.user, feed_item=feed_item, interaction_type='saved',
    )

    return JsonResponse({
        'published': True,
        'content_item_ids': created_items,
        'count': len(created_items),
    })


@login_required
@require_POST
def save_automation_rules(request):
    from core.tenant import get_current_tenant

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    rules = body.get('rules', [])
    if not isinstance(rules, list):
        return JsonResponse({'error': 'rules must be a list'}, status=400)

    from .models import TrendingAutomationRule, Topic, UserTopicPreference

    workspace = get_current_tenant()
    saved = []
    for rule in rules:
        topic_id = rule.get('topic_id')
        if not topic_id:
            continue
        topic = Topic.objects.filter(id=topic_id, is_active=True).first()
        if not topic:
            continue

        rule_defaults = {
            'platforms': rule.get('platforms', []),
            'schedule_interval': rule.get('schedule_interval', 'daily'),
            'auto_publish': rule.get('auto_publish', False),
            'is_active': rule.get('is_active', True),
            'workspace': workspace,
        }
        rule_filter = {'user': request.user, 'topic': topic}
        if workspace:
            rule_filter['workspace'] = workspace
        obj, created = TrendingAutomationRule.objects.update_or_create(
            defaults=rule_defaults,
            **rule_filter,
        )
        saved.append({
            'id': obj.id,
            'topic_id': topic.id,
            'topic_name': topic.name,
            'platforms': obj.platforms,
            'schedule_interval': obj.schedule_interval,
            'auto_publish': obj.auto_publish,
            'is_active': obj.is_active,
        })

    # Remove rules for topics no longer in the request
    submitted_topic_ids = [r['topic_id'] for r in rules if r.get('topic_id')]
    delete_rule_filter = {'user': request.user}
    if workspace:
        delete_rule_filter['workspace'] = workspace
    TrendingAutomationRule.objects.filter(
        **delete_rule_filter,
    ).exclude(topic_id__in=submitted_topic_ids).delete()

    # Feed subscriptions (UserTopicPreference) are managed independently via
    # select_categories / toggle_subscription / bulk_subscribe.
    # Automation rules do NOT override feed preferences.

    # Invalidate Currents snapshots so the next load immediately reflects the new rules.
    from .models import CurrentsSnapshot
    delete_snap_filter = {'user': request.user}
    if workspace:
        delete_snap_filter['workspace'] = workspace
    CurrentsSnapshot.objects.filter(**delete_snap_filter).delete()

    return JsonResponse({'rules': saved, 'count': len(saved)})


@login_required
@require_GET
def automation_rules_data(request):
    from .models import TrendingAutomationRule
    from core.tenant import get_current_tenant

    workspace = get_current_tenant()
    rule_filter = {'user': request.user}
    if workspace:
        rule_filter['workspace'] = workspace
    rules = TrendingAutomationRule.objects.filter(**rule_filter).select_related('topic')
    data = []
    for rule in rules:
        data.append({
            'id': rule.id,
            'topic_id': rule.topic_id,
            'topic_name': rule.topic.name,
            'topic_icon': rule.topic.icon,
            'topic_color': rule.topic.color,
            'platforms': rule.platforms,
            'schedule_interval': rule.schedule_interval,
            'auto_publish': rule.auto_publish,
            'is_active': rule.is_active,
        })
    return JsonResponse({'rules': data})


@login_required
@require_POST
def generate_automation_content(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    topic_id = body.get('topic_id')
    platforms = body.get('platforms', [])
    limit = min(body.get('limit', 3), 10)

    if not topic_id or not platforms:
        return JsonResponse({'error': 'topic_id and platforms are required'}, status=400)

    from .models import Topic, FeedItem

    topic = Topic.objects.filter(id=topic_id, is_active=True).first()
    if not topic:
        return JsonResponse({'error': 'Topic not found'}, status=404)

    items = list(FeedItem.objects.filter(
        is_duplicate=False, topic=topic,
    ).order_by('-trending_score')[:limit])

    if not items:
        return JsonResponse({'items': [], 'count': 0})

    content_items = generate_llm_content(request.user, topic, platforms, items)
    created = []
    for ci in content_items:
        created.append({
            'id': ci.id,
            'title': ci.title,
            'platform': ci.platform,
            'body_preview': ci.body[:150],
            'status': ci.status,
            'created_at': ci.created_at.isoformat(),
            'topic_name': topic.name,
            'topic_icon': topic.icon,
        })

    return JsonResponse({'items': created, 'count': len(created)})


@login_required
@require_GET
def list_generated_items(request):
    from apps.content_studio.models import ContentItem

    items = ContentItem.objects.filter(
        user=request.user,
        is_auto_generated=True,
    ).extra(
        where=["metadata->>'source' = 'trending_automation'"]
    ).order_by('-created_at')[:20]

    data = []
    for item in items:
        meta = item.metadata or {}
        data.append({
            'id': item.id,
            'title': item.title,
            'body_preview': item.body[:200],
            'platform': item.platform,
            'status': item.status,
            'created_at': item.created_at.isoformat(),
            'topic_name': meta.get('topic_name', ''),
            'topic_icon': meta.get('topic_icon', ''),
            'source_url': meta.get('source_url', ''),
        })
    return JsonResponse({'items': data})


@login_required
@require_POST
def publish_automation_item(request, content_item_id):
    from apps.content_studio.models import ContentItem
    from apps.social_accounts.models import SocialAccount, SocialPost
    from apps.social_accounts.services import SocialService

    ci = ContentItem.objects.filter(id=content_item_id, user=request.user).first()
    if not ci:
        return JsonResponse({'error': 'Content item not found'}, status=404)

    account = SocialAccount.objects.filter(
        user=request.user, platform=ci.platform, is_active=True
    ).first()
    if not account:
        return JsonResponse({
            'error': 'not_connected',
            'message': f'Connect your {ci.platform.title()} account to publish.',
        }, status=400)

    post = SocialPost.objects.create(
        user=request.user,
        account=account,
        platform=ci.platform,
        content=ci.body,
        hashtags=ci.tags or [],
        status='draft',
        content_item=ci,
    )

    try:
        svc = SocialService(request.user)
        svc.publish_post(post.id)
        post.refresh_from_db()
    except Exception as e:
        post.status = 'failed'
        post.error_message = str(e)
        post.save(update_fields=['status', 'error_message'])
        return JsonResponse({'error': 'publish_failed', 'message': str(e)}, status=500)

    ci.status = 'published'
    ci.save(update_fields=['status'])

    return JsonResponse({
        'published': True,
        'post_id': post.id,
        'status': post.status,
        'platform_post_url': post.platform_post_url,
    })


@login_required
@require_POST
def schedule_automation_item(request, content_item_id):
    import json as _json

    try:
        body = _json.loads(request.body)
    except _json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    scheduled_str = body.get('scheduled_at')
    if not scheduled_str:
        return JsonResponse({'error': 'scheduled_at is required'}, status=400)

    from datetime import datetime
    try:
        scheduled_dt = datetime.fromisoformat(scheduled_str)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid datetime format'}, status=400)

    from apps.content_studio.models import ContentItem
    from apps.social_accounts.models import SocialAccount, SocialPost

    ci = ContentItem.objects.filter(id=content_item_id, user=request.user).first()
    if not ci:
        return JsonResponse({'error': 'Content item not found'}, status=404)

    account = SocialAccount.objects.filter(
        user=request.user, platform=ci.platform, is_active=True
    ).first()
    if not account:
        return JsonResponse({
            'error': 'not_connected',
            'message': f'Connect your {ci.platform.title()} account to schedule.',
        }, status=400)

    post = SocialPost.objects.create(
        user=request.user,
        account=account,
        platform=ci.platform,
        content=ci.body,
        hashtags=ci.tags or [],
        scheduled_at=scheduled_dt,
        status='scheduled',
        content_item=ci,
    )

    ci.status = 'scheduled'
    ci.save(update_fields=['status'])

    return JsonResponse({
        'scheduled': True,
        'post_id': post.id,
        'scheduled_at': scheduled_dt.isoformat(),
        'status': post.status,
    })


@login_required
@require_POST
def refine_feed_top5(request):
    """Called by the frontend after rendering page 1 of the feed.
    Takes the top 5 item IDs, runs LLM refinement, stores as CurrentsSnapshot."""
    from django.db.models import Count
    from django.utils import timezone
    from datetime import timedelta
    from django.core.cache import cache
    from .models import CurrentsSnapshot

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'}, status=400)

    item_ids = body.get('item_ids', [])[:5]
    if not item_ids:
        return JsonResponse({'ok': False, 'error': 'no item_ids'}, status=400)

    try:
        items = list(
            FeedItem.objects.filter(id__in=item_ids, is_duplicate=False)
            .select_related('topic', 'source')
        )
    except OperationalError:
        return JsonResponse({'ok': False, 'error': 'db_error', 'retryable': True}, status=200)
    if not items:
        return JsonResponse({'ok': False, 'error': 'items not found'}, status=404)

    workspace = get_current_tenant()

    # If these exact feed items were already refined in the last 6 hours, reuse the batch
    recent = timezone.now() - timedelta(hours=6)
    matching = CurrentsSnapshot.objects.filter(
        user=request.user,
        feed_item_id__in=item_ids,
        created_at__gte=recent,
    ).values('batch_id').annotate(
        matched=Count('feed_item_id', distinct=True)
    ).filter(matched=len(item_ids))

    if matching.exists():
        return JsonResponse({
            'ok': True,
            'batch_id': matching.order_by('batch_id').first()['batch_id'],
            'llm': True,
            'cached': True,
        })

    ok, result = _run_refine_pipeline(request.user, items, workspace=workspace)

    if ok:
        cache.delete(f'llm_retry_{request.user.id}')
        cache.delete(f'llm_error_{request.user.id}')
        cache.delete(f'needs_platform_{request.user.id}')
        return JsonResponse({'ok': True, 'batch_id': result['batch_id'], 'llm': True})

    error = result.get('error', '')

    if error == 'no_platforms':
        cache.set(f'needs_platform_{request.user.id}', True, timeout=86400)
        return JsonResponse({'ok': False, 'error': 'no_platforms'}, status=200)

    if error == 'llm_failed':
        # Check if a retry is already pending — don't duplicate
        existing = cache.get(f'llm_retry_{request.user.id}')
        if existing and isinstance(existing, dict):
            return JsonResponse({
                'ok': False, 'error': 'llm_retry',
                'attempt': existing.get('attempt', 1),
            })

        from .tasks import retry_refine_feed
        attempt = 1
        delay = min(attempt * 300, 3600)  # 5 min
        retry_info = {'attempt': attempt, 'error': result.get('reason', '')}
        cache.set(f'llm_retry_{request.user.id}', retry_info, timeout=attempt * 3600)
        retry_refine_feed.apply_async(
            args=[request.user.id, item_ids, attempt],
            countdown=delay,
        )
        return JsonResponse({
            'ok': False, 'error': 'llm_retry',
            'attempt': attempt,
            'retry_in': delay,
        })

    return JsonResponse({'ok': False, 'error': error}, status=200)


@login_required
@require_POST
def refresh_feed(request):
    from .tasks import collect_all_sources, recalculate_trending_scores, deduplicate_content
    from django.core.cache import cache

    scheduled_ts = cache.get('trending_scheduled_refresh_ts', 0)
    key = f'trending_manual_count_{request.user.id}'
    manual = cache.get(key, {'count': 0, 'last_reset': 0})

    if manual['last_reset'] < scheduled_ts:
        manual = {'count': 0, 'last_reset': scheduled_ts}

    if manual['count'] >= 10:
        return JsonResponse({
            'status': 'limit_reached',
            'message': 'Manual refresh limit reached (10/10). Wait for the next scheduled refresh to reset.',
        }, status=429)

    manual['count'] += 1
    cache.set(key, manual, timeout=86400)

    collect_all_sources.delay(force=True)
    recalculate_trending_scores.delay()
    deduplicate_content.delay()
    return JsonResponse({'status': 'triggered', 'remaining': 10 - manual['count']})


@login_required
@require_POST
def refresh_profile(request):
    profile = UserActivityProfile.objects.filter(user=request.user).first()

    if profile and profile.last_analyzed_at:
        last = profile.last_analyzed_at
        has_new = False
        try:
            ContentItem = __import__('apps.content_studio.models', fromlist=['ContentItem']).ContentItem
            if ContentItem.objects.filter(user=request.user, created_at__gt=last).exists():
                has_new = True
        except Exception:
            pass
        if not has_new:
            try:
                SocialPost = __import__('apps.social_accounts.models', fromlist=['SocialPost']).SocialPost
                if SocialPost.objects.filter(user=request.user, created_at__gt=last).exists():
                    has_new = True
            except Exception:
                pass
        if not has_new:
            try:
                Campaign = __import__('apps.campaigns.models', fromlist=['Campaign']).Campaign
                if Campaign.objects.filter(
                    Q(owner=request.user) | Q(workspace__members__user=request.user),
                    created_at__gt=last,
                ).exists():
                    has_new = True
            except Exception:
                pass

        if not has_new:
            return JsonResponse({
                'status': 'uptodate',
                'keywords': profile.inferred_keywords,
                'topic_ids': profile.inferred_topic_ids,
                'last_analyzed': profile.last_analyzed_at.isoformat() if profile.last_analyzed_at else None,
            })

    profiler = UserProfiler()
    profile = profiler.analyze(request.user)

    return JsonResponse({
        'status': 'updated',
        'keywords': profile.inferred_keywords,
        'topic_ids': profile.inferred_topic_ids,
        'last_analyzed': profile.last_analyzed_at.isoformat() if profile.last_analyzed_at else None,
    })


@login_required
@require_GET
def pipeline_status(request):
    from .models import ContentSource, FeedItem, TrendingAutomationRule, CurrentsSnapshot
    from core.tenant import get_current_tenant

    sources = ContentSource.objects.filter(is_active=True).count()
    total_items = FeedItem.objects.count()
    scored_items = FeedItem.objects.exclude(trending_score__isnull=True).count()
    workspace = get_current_tenant()
    rule_filter = {'user': request.user, 'is_active': True}
    snap_filter = {'user': request.user}
    if workspace:
        rule_filter['workspace'] = workspace
        snap_filter['workspace'] = workspace
    rules = TrendingAutomationRule.objects.filter(**rule_filter).count()
    snapshots = CurrentsSnapshot.objects.filter(**snap_filter).count()
    return JsonResponse({
        'sources': sources,
        'feed_items': total_items,
        'scored': scored_items,
        'automation_rules': rules,
        'current_snapshots': snapshots,
    })
