import json
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.db.models import F, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from .models import ContentSource, FeedItem, CurrentItem, Topic, UserActivityProfile, UserFeedInteraction, UserTopicPreference
from .services.personalizer import Personalizer
from .services.user_profiler import UserProfiler


@login_required
@require_GET
def feed_data(request):
    topic_id = request.GET.get('topic_id')

    items = FeedItem.objects.filter(
        is_duplicate=False,
    ).select_related('topic', 'source').order_by('-trending_score')

    if topic_id:
        items = items.filter(topic_id=topic_id)

    if request.GET.get('subscribed'):
        subscribed_ids = list(
            UserTopicPreference.objects.filter(
                user=request.user
            ).values_list('topic_id', flat=True)
        )
        if subscribed_ids:
            items = items.filter(topic_id__in=subscribed_ids)

    items = items[:100]

    personalizer = Personalizer()
    ranked = personalizer.personalize(request.user, list(items))

    bookmarked_ids = set(
        UserFeedInteraction.objects.filter(
            user=request.user,
            interaction_type='bookmarked',
            feed_item_id__in=[f.id for f in ranked],
        ).values_list('feed_item_id', flat=True)
    )

    data = []
    for item in ranked:
        data.append({
            'id': item.id,
            'title': item.title,
            'url': item.url,
            'author': item.author,
            'summary': item.ai_summary or (item.content_cleaned or '')[:300],
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

    return JsonResponse({'items': data, 'total': len(data)})


@login_required
@require_GET
def topic_list(request):
    topics = Topic.objects.filter(is_active=True).order_by('-subscriber_count')

    subscribed_ids = set(
        UserTopicPreference.objects.filter(
            user=request.user,
        ).values_list('topic_id', flat=True)
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
            'is_subscribed': topic.id in subscribed_ids,
        })

    return JsonResponse({'topics': data})


@login_required
@require_POST
def toggle_subscription(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    topic_id = body.get('topic_id')
    subscribe = body.get('subscribe', True)

    if not topic_id:
        return JsonResponse({'error': 'topic_id is required'}, status=400)

    topic = get_object_or_404(Topic, id=topic_id, is_active=True)

    if subscribe:
        _, created = UserTopicPreference.objects.get_or_create(
            user=request.user,
            topic=topic,
            defaults={'is_auto_detected': False},
        )
        if created:
            Topic.objects.filter(id=topic.id).update(
                subscriber_count=F('subscriber_count') + 1
            )
    else:
        deleted, _ = UserTopicPreference.objects.filter(
            user=request.user,
            topic=topic,
            is_auto_detected=False,
        ).delete()
        if deleted:
            Topic.objects.filter(id=topic.id).update(
                subscriber_count=F('subscriber_count') - 1
            )

    return JsonResponse({'subscribed': subscribe})


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
            title=feed_item.title[:255],
            content_type='full_post',
            body=post_body,
            platform=platform,
            status='draft',
            is_auto_generated=True,
            source_prompt=f'Imported from Currents: {feed_item.url}',
            tags=[hashtags] if hashtags else (feed_item.ai_categories or []),
        )

        item.metadata.update({
            'source': 'trending',
            'feed_item_id': feed_item.id,
            'source_url': feed_item.url,
            'source_name': feed_item.source.name if feed_item.source else '',
            'platform': platform,
        })
        item.save(update_fields=['metadata'])

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
            except Exception:
                pass

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
def manage_categories(request):
    topics = Topic.objects.filter(is_active=True).order_by('name')
    subscribed_ids = set(
        UserTopicPreference.objects.filter(user=request.user).values_list('topic_id', flat=True)
    )
    return render(request, 'trending/select_categories.html', {
        'topics': topics,
        'subscribed_ids': subscribed_ids,
    })


@login_required
@require_POST
def bulk_subscribe(request):
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    topic_ids = body.get('topic_ids', [])
    if not isinstance(topic_ids, list):
        return JsonResponse({'error': 'topic_ids must be a list'}, status=400)

    current_ids = set(
        UserTopicPreference.objects.filter(user=request.user).values_list('topic_id', flat=True)
    )
    new_ids = set(topic_ids)
    to_add = new_ids - current_ids
    to_remove = current_ids - new_ids

    topics = {t.id: t for t in Topic.objects.filter(id__in=to_add | to_remove, is_active=True)}

    for tid in to_add:
        topic = topics.get(tid)
        if not topic:
            continue
        UserTopicPreference.objects.get_or_create(
            user=request.user, topic=topic, defaults={'is_auto_detected': False},
        )
        Topic.objects.filter(id=tid).update(subscriber_count=F('subscriber_count') + 1)

    UserTopicPreference.objects.filter(
        user=request.user, topic_id__in=to_remove, is_auto_detected=False,
    ).delete()
    for tid in to_remove:
        Topic.objects.filter(id=tid).update(subscriber_count=F('subscriber_count') - 1)

    return JsonResponse({'subscribed_ids': list(new_ids)})


@login_required
@require_GET
def currents_data(request):
    import random as _random
    from collections import defaultdict

    subscribed_ids = list(
        UserTopicPreference.objects.filter(user=request.user).values_list('topic_id', flat=True)
    )

    if not subscribed_ids:
        return JsonResponse({'items': [], 'total': 0, 'needs_categories': True})

    all_items = list(FeedItem.objects.filter(
        is_duplicate=False,
        topic_id__in=subscribed_ids,
    ).select_related('topic', 'source').order_by('-trending_score')[:50])

    ready_ids = set(
        CurrentItem.objects.filter(user=request.user).values_list('feed_item_id', flat=True)
    )

    # Group by topic with image boost (+15 for items with image)
    topic_groups = defaultdict(list)
    for item in all_items:
        adjusted = item.trending_score + (15 if item.image_url else 0)
        topic_groups[item.topic_id].append((adjusted, item))

    for tid in topic_groups:
        topic_groups[tid].sort(key=lambda x: x[0], reverse=True)

    # Round-robin to pick 5 diverse items across topics
    topic_order = list(topic_groups.keys())
    _random.shuffle(topic_order)
    selected = []
    while len(selected) < 5 and topic_order:
        for tid in list(topic_order):
            if topic_groups[tid]:
                _, item = topic_groups[tid].pop(0)
                selected.append(item)
            if len(selected) >= 5:
                break
        topic_order = [t for t in topic_order if topic_groups[t]]

    items = selected[:5]

    data = []
    for item in items:
        data.append({
            'id': item.id,
            'title': item.title,
            'url': item.url,
            'author': item.author,
            'summary': item.ai_summary or (item.content_cleaned or '')[:300],
            'topic': {
                'id': item.topic.id,
                'name': item.topic.name,
                'icon': item.topic.icon,
                'color': item.topic.color,
            } if item.topic else None,
            'source': item.source.name if item.source else 'Unknown',
            'score': item.trending_score,
            'is_queued': item.id in ready_ids,
            'published_at': item.published_at.isoformat() if item.published_at else None,
            'image_url': item.image_url or '',
            'generated_content': None,
        })

    # Multi-platform batched LLM generation for all items
    try:
        from apps.content_studio.llm.llm_service import _call_llm

        prompt_parts = []
        for item in items:
            title = item.title or ''
            summary = item.ai_summary or item.content_cleaned or ''
            prompt_parts.append(f"ITEM {item.id}:\nTitle: {title}\nSummary: {summary[:500]}\n")

        system_prompt = (
            "You are a social media content strategist. For each news item below, generate "
            "a platform-optimized post with relevant hashtags for each applicable platform.\n\n"
            "Platforms and their requirements:\n"
            "- linkedin: Professional, thought-leadership, 1300-2000 chars, 3-5 hashtags\n"
            "- twitter: Concise, under 280 chars, 1-2 hashtags\n"
            "- instagram: Visual-first, 150-220 chars before 'more', 5-8 hashtags\n"
            "- facebook: Conversational, 150-500 chars, 2-4 hashtags\n"
            "- tiktok: Casual and punchy, under 100 chars, 1-3 hashtags\n\n"
            "For each item, follow this structure:\n"
            "- HOOK: bold statement or question (under 15 words)\n"
            "- BODY: deliver the core message in the platform's style\n"
            "- CTA: End with an engaging question or action\n\n"
            "Return ONLY a valid JSON array:\n"
            "[\n"
            "  {\n"
            '    "id": <item_id>,\n'
            '    "platforms": {\n'
            '      "linkedin": {"body": "...", "hashtags": "#tag1 #tag2 #tag3"},\n'
            '      "twitter": {"body": "...", "hashtags": "#tag1 #tag2"},\n'
            '      "instagram": {"body": "...", "hashtags": "#tag1 #tag2 #tag3"},\n'
            '      "facebook": {"body": "...", "hashtags": "#tag1 #tag2"},\n'
            '      "tiktok": {"body": "...", "hashtags": "#tag1 #tag2 #tag3"}\n'
            "    }\n"
            "  },\n"
            "  ...\n"
            "]\n\n"
            "Do NOT include markdown code fences, backticks, or any text outside the JSON array."
        )

        user_prompt = "\n---\n".join(prompt_parts)
        result = _call_llm(system_prompt, user_prompt)

        if result['success'] and result['content']:
            import re as _re
            text = result['content'].strip()
            json_match = _re.search(r'\[.*\]', text, _re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                gen_map = {entry['id']: entry for entry in parsed if 'id' in entry}
                for d in data:
                    entry = gen_map.get(d['id'])
                    if entry and isinstance(entry.get('platforms'), dict):
                        d['generated_content'] = {}
                        for p, info in entry['platforms'].items():
                            if isinstance(info, dict):
                                d['generated_content'][p] = {
                                    'body': info.get('body', ''),
                                    'hashtags': info.get('hashtags', ''),
                                }
    except Exception:
        pass  # LLM unavailable — fall back to raw content

    return JsonResponse({'items': data, 'total': len(data)})


@login_required
@require_POST
def queue_for_publish(request, item_id):
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

    ready, created = CurrentItem.objects.get_or_create(
        user=request.user,
        feed_item=feed_item,
        defaults={
            'scheduled_at': scheduled_dt,
            'status': 'scheduled' if scheduled_dt else 'draft',
        },
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
    deleted, _ = CurrentItem.objects.filter(
        user=request.user, feed_item_id=item_id,
    ).delete()
    return JsonResponse({'deleted': bool(deleted)})


@login_required
@require_POST
def publish_currents(request, item_id):
    feed_item = get_object_or_404(FeedItem, id=item_id, is_duplicate=False)
    ready = CurrentItem.objects.filter(user=request.user, feed_item=feed_item).first()

    if not ready:
        return JsonResponse({'error': 'Item not in currents queue'}, status=400)

    try:
        from apps.content_studio.services.content_service import ContentService
    except ImportError:
        return JsonResponse({'error': 'Content Studio unavailable'}, status=500)

    # Build prompt from feed item
    prompt_parts = []
    if feed_item.title:
        prompt_parts.append(f"Title: {feed_item.title}")
    summary = feed_item.ai_summary or feed_item.content_cleaned or ''
    if summary:
        prompt_parts.append(f"Summary: {summary[:500]}")
    prompt = '\n\n'.join(prompt_parts)

    # Generate a full post via LLM
    cs = ContentService(request.user)
    item = cs.generate_content(
        'full_post', prompt,
        platform='linkedin', tone='professional',
        target_audience='industry professionals',
        key_points=feed_item.title[:200],
    )

    # Fallback if LLM unavailable
    if not item:
        from apps.content_studio.models import ContentItem
        item = ContentItem.objects.create(
            user=request.user,
            title=feed_item.title[:255],
            content_type='full_post',
            body=feed_item.ai_summary or feed_item.content_cleaned or feed_item.content_raw or '',
            status='draft',
            is_auto_generated=True,
            source_prompt=f'Scheduled from Trending Topics: {feed_item.url}',
            tags=feed_item.ai_categories or [],
        )

    # Update metadata with trending source info
    item.metadata.update({
        'source': 'trending',
        'feed_item_id': feed_item.id,
        'source_url': feed_item.url,
        'source_name': feed_item.source.name if feed_item.source else '',
    })
    item.save(update_fields=['metadata'])
    item.title = feed_item.title[:255]
    item.save(update_fields=['title'])

    # Generate hashtags
    try:
        from apps.content_studio.llm.llm_service import generate_llm
        hashtag_result = generate_llm('hashtag_set', prompt, platform='linkedin')
        if hashtag_result['success']:
            existing = list(item.tags) if item.tags else []
            existing.append(hashtag_result['content'])
            item.tags = existing
            item.save(update_fields=['tags'])
    except Exception:
        pass

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
        except Exception:
            pass  # Non-critical

    ready.status = 'published'
    ready.save(update_fields=['status'])

    UserFeedInteraction.objects.get_or_create(
        user=request.user, feed_item=feed_item, interaction_type='saved',
    )

    return JsonResponse({
        'published': True,
        'content_item_id': item.id,
        'redirect_url': f'/content-studio/{item.id}/',
    })


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
