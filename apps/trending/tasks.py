import logging
from datetime import timedelta
from datetime import datetime, timezone

from celery import shared_task
from django.db.utils import OperationalError
from django.utils import timezone as tz

logger = logging.getLogger(__name__)


@shared_task(queue='low', bind=True, autoretry_for=(OperationalError,), max_retries=3, default_retry_delay=60)
def collect_all_sources(self, force=False):
    from django.db import close_old_connections
    close_old_connections()

    from .models import ContentSource
    from .services.github_collector import GitHubCollector
    from .services.rss_collector import RSSCollector
    from .services.web_scraper import WebScraper

    sources = ContentSource.objects.filter(is_active=True)

    if force:
        due_sources = list(sources)
    else:
        now = tz.now()
        due_sources = []
        for source in sources:
            if source.last_fetched is None:
                due_sources.append(source)
            else:
                elapsed = (now - source.last_fetched).total_seconds() / 3600
                if elapsed >= source.poll_interval_hours:
                    due_sources.append(source)

    collectors = {
        'rss': RSSCollector(),
        'api': GitHubCollector(),
        'web': WebScraper(),
    }

    total_created = 0

    for source in due_sources:
        collector = collectors.get(source.source_type)
        if not collector:
            logger.warning("No collector for source type: %s", source.source_type)
            continue

        try:
            created = collector.collect(source)
            total_created += created
        except Exception as e:
            logger.exception("Collector failed for %s: %s", source.name, e)
            continue

        source.last_fetched = datetime.now(timezone.utc)
        source.save(update_fields=['last_fetched'])

    if total_created > 0:
        if force:
            recalculate_trending_scores()
            deduplicate_content()
        else:
            recalculate_trending_scores.delay()
            deduplicate_content.delay()

    if not force:
        from django.core.cache import cache
        import time as _time
        cache.set('trending_scheduled_refresh_ts', _time.time(), timeout=86400)

    logger.info("collect_all_sources complete: %d new items", total_created)
    return total_created


@shared_task(queue='low', bind=True, autoretry_for=(OperationalError,), max_retries=3, default_retry_delay=60)
def recalculate_trending_scores(self):
    from django.db import close_old_connections
    close_old_connections()

    from django.db.models import Q
    from .models import FeedItem, Topic
    from .services.categorizer import Categorizer
    from .services.content_cleaner import ContentCleaner
    from .services.scorer import Scorer
    from .services.summarizer import Summarizer

    cleaner = ContentCleaner()
    categorizer = Categorizer()
    scorer = Scorer()
    summarizer = Summarizer()

    all_topics = list(Topic.objects.filter(is_active=True))

    cutoff = tz.now() - timedelta(hours=72)
    items = FeedItem.objects.filter(
        is_duplicate=False,
    ).filter(
        Q(published_at__gte=cutoff) | Q(fetched_at__gte=cutoff)
    ).order_by('-fetched_at')[:500]

    updated = 0
    for item in items:
        close_old_connections()
        try:
            item = cleaner.clean(item)
            item = summarizer.summarize(item)
            item_before_topic = item.topic
            item = categorizer.categorize(item, topics=all_topics)
            if item.topic is None:
                item.topic = item_before_topic
            item.trending_score = scorer.score(item)
            save_fields = ['content_cleaned', 'trending_score', 'language']
            if item.topic is not None:
                save_fields.append('topic')
            if item.ai_categories:
                save_fields.append('ai_categories')
            item.save(update_fields=save_fields)
            updated += 1
        except Exception as e:
            logger.exception("Failed to score item %d: %s", item.id, e)

    logger.info("recalculate_trending_scores: scored %d items", updated)
    return updated


@shared_task(queue='low', bind=True, autoretry_for=(OperationalError,), max_retries=3, default_retry_delay=60)
def deduplicate_content(self):
    from django.db import close_old_connections
    close_old_connections()

    from .models import FeedItem

    items = FeedItem.objects.filter(is_duplicate=False).order_by('fetched_at')
    from .services.content_cleaner import ContentCleaner

    cleaner = ContentCleaner()
    marked = 0

    for item in items:
        close_old_connections()
        try:
            if cleaner.detect_duplicate(item):
                item.is_duplicate = True
                item.save(update_fields=['is_duplicate'])
                marked += 1
        except Exception as e:
            logger.exception("Dedup check failed for item %d: %s", item.id, e)

    logger.info("deduplicate_content: marked %d duplicates", marked)
    return marked


@shared_task(queue='low', bind=True, autoretry_for=(OperationalError,), max_retries=3, default_retry_delay=60)
def analyze_user_profiles(self):
    from django.db import close_old_connections
    close_old_connections()

    from django.contrib.auth import get_user_model
    from .services.user_profiler import UserProfiler

    User = get_user_model()
    profiler = UserProfiler()
    processed = 0

    for user in User.objects.filter(is_active=True):
        close_old_connections()
        try:
            profiler.analyze(user)
            processed += 1
        except Exception as e:
            logger.exception("Failed to analyze user %s: %s", user.email, e)

    logger.info("analyze_user_profiles: processed %d users", processed)
    return processed


@shared_task(queue='low', bind=True, autoretry_for=(OperationalError,), max_retries=3, default_retry_delay=60)
def run_automation(self):
    from datetime import timedelta
    from django.db import close_old_connections
    from django.utils import timezone
    from .models import TrendingAutomationRule, FeedItem
    from .services.content_generator import generate_llm_content

    close_old_connections()

    rules = TrendingAutomationRule.objects.filter(is_active=True).select_related('user', 'topic')
    processed = 0

    for rule in rules:
        close_old_connections()
        try:
            interval_hours = {
                'hourly': 1,
                'every_6h': 6,
                'daily': 24,
                'weekly': 168,
            }.get(rule.schedule_interval, 24)

            if rule.last_run_at:
                elapsed = (timezone.now() - rule.last_run_at).total_seconds() / 3600
                if elapsed < interval_hours:
                    continue

            cutoff = timezone.now() - timedelta(hours=interval_hours)
            items = list(FeedItem.objects.filter(
                is_duplicate=False,
                topic=rule.topic,
                fetched_at__gte=cutoff,
            ).order_by('-trending_score')[:5])

            if not items:
                continue

            platforms = rule.platforms
            if not platforms:
                continue

            content_items = generate_llm_content(rule.user, rule.topic, platforms, items, rule.id)

            if rule.auto_publish:
                for ci in content_items:
                    try:
                        from apps.social_accounts.models import SocialAccount, SocialPost

                        account = SocialAccount.objects.filter(
                            user=rule.user, platform=ci.platform, is_active=True
                        ).first()
                        if account:
                            SocialPost.objects.create(
                                user=rule.user,
                                account=account,
                                platform=ci.platform,
                                content=ci.body,
                                hashtags=ci.tags or [],
                                status='scheduled',
                                scheduled_at=timezone.now(),
                                content_item=ci,
                            )
                    except Exception:
                        logger.exception(
                            "Failed to create SocialPost for user %s, platform %s",
                            rule.user.email, ci.platform,
                        )

            processed += len(content_items)

            rule.last_run_at = timezone.now()
            rule.save(update_fields=['last_run_at'])

        except Exception as e:
            logger.exception(
                "Automation rule failed for user %s topic %s: %s",
                rule.user.email, rule.topic.name, e,
            )

    logger.info("run_automation: processed %d items from %d rules", processed, rules.count())
    return processed


@shared_task(queue='low', max_retries=1)  # manual scheduling, not Celery retry
def retry_refine_feed(user_id, item_ids, attempt=1):
    """Background retry for refine_feed_top5 when LLM API was rate limited."""
    from django.core.cache import cache
    from django.contrib.auth import get_user_model
    from django.db import close_old_connections
    from django.db.utils import OperationalError
    from .models import FeedItem
    from .views import _run_refine_pipeline

    close_old_connections()

    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error("retry_refine_feed: user %s not found", user_id)
        return
    except OperationalError:
        close_old_connections()
        raise

    try:
        items = list(
            FeedItem.objects.filter(id__in=item_ids, is_duplicate=False)
            .select_related('topic', 'source')
        )
    except OperationalError:
        close_old_connections()
        raise
    if not items:
        logger.warning("retry_refine_feed: items not found for user %s", user_id)
        return

    try:
        ok, result = _run_refine_pipeline(user, items)
    except Exception as e:
        logger.exception("retry_refine_feed: unexpected error for user %s: %s", user_id, e)
        from django.core.cache import cache
        if attempt < 3:
            next_attempt = attempt + 1
            delay = min(next_attempt * 300, 3600)
            cache.set(f'llm_retry_{user_id}', {
                'attempt': next_attempt, 'error': str(e),
            }, timeout=next_attempt * 3600)
            retry_refine_feed.apply_async(
                args=[user_id, item_ids, next_attempt],
                countdown=delay,
            )
        else:
            cache.set(f'llm_error_{user_id}', str(e), timeout=3600)
            cache.delete(f'llm_retry_{user_id}')
        return

    if ok:
        cache.delete(f'llm_retry_{user_id}')
        cache.delete(f'llm_error_{user_id}')
        logger.info("retry_refine_feed: success for user %s (attempt %d)", user_id, attempt)
        return

    error = result.get('error', '')
    logger.warning("retry_refine_feed: %s for user %s (attempt %d)", error, user_id, attempt)

    if error == 'no_platforms':
        cache.set(f'needs_platform_{user_id}', True, timeout=86400)
        cache.delete(f'llm_retry_{user_id}')
        return

    if error == 'llm_failed':
        if attempt < 3:
            next_attempt = attempt + 1
            delay = min(next_attempt * 300, 3600)
            cache.set(f'llm_retry_{user_id}', {
                'attempt': next_attempt,
                'error': result.get('reason', ''),
            }, timeout=next_attempt * 3600)
            retry_refine_feed.apply_async(
                args=[user_id, item_ids, next_attempt],
                countdown=delay,
            )
            logger.info("retry_refine_feed: scheduled attempt %d in %ds for user %s",
                        next_attempt, delay, user_id)
        else:
            reason = result.get('reason', 'Max retries exceeded')
            cache.set(f'llm_error_{user_id}', reason, timeout=3600)
            cache.delete(f'llm_retry_{user_id}')
            logger.error("retry_refine_feed: all attempts exhausted for user %s: %s",
                         user_id, reason)


