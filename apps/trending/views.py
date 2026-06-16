import json

from django.contrib.auth.decorators import login_required
from django.db.models import F, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from .models import ContentSource, FeedItem, Topic, UserActivityProfile, UserFeedInteraction, UserTopicPreference
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
        from apps.content_studio.models import ContentItem
    except ImportError:
        return JsonResponse({'error': 'Content Studio unavailable'}, status=500)

    from core.tenant import tenant_context
    with tenant_context(None):
        content_item = ContentItem.objects.create(
            user=request.user,
            title=feed_item.title[:255],
            content_type='full_post',
            body=feed_item.ai_summary or feed_item.content_cleaned or feed_item.content_raw or '',
            status='draft',
            is_auto_generated=True,
            source_prompt=f'Imported from Trending Topics: {feed_item.url}',
            tags=feed_item.ai_categories or [],
            metadata={
                'source': 'trending',
                'feed_item_id': feed_item.id,
                'source_url': feed_item.url,
                'source_name': feed_item.source.name if feed_item.source else '',
            },
        )

    from .models import UserActivityProfile
    from django.utils import timezone
    profile, _ = UserActivityProfile.objects.get_or_create(user=request.user)
    profile.last_analyzed_at = timezone.now()
    profile.save(update_fields=['last_analyzed_at'])

    UserFeedInteraction.objects.get_or_create(
        user=request.user,
        feed_item=feed_item,
        interaction_type='saved',
    )

    return JsonResponse({
        'content_item_id': content_item.id,
        'redirect_url': f'/content-studio/{content_item.id}/',
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
