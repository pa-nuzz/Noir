import logging
from datetime import datetime, timezone

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(queue='low')
def collect_all_sources():
    from .models import ContentSource
    from .services.content_cleaner import ContentCleaner
    from .services.github_collector import GitHubCollector
    from .services.rss_collector import RSSCollector
    from .services.scorer import Scorer
    from .services.web_scraper import WebScraper

    sources = ContentSource.objects.filter(is_active=True)
    collectors = {
        'rss': RSSCollector(),
        'api': GitHubCollector(),
        'web': WebScraper(),
    }

    total_created = 0
    cleaner = ContentCleaner()
    scorer = Scorer()

    for source in sources:
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
        recalculate_trending_scores.delay()
        deduplicate_content.delay()

    logger.info("collect_all_sources complete: %d new items", total_created)
    return total_created


@shared_task(queue='low')
def recalculate_trending_scores():
    from .models import FeedItem
    from .services.content_cleaner import ContentCleaner
    from .services.scorer import Scorer

    cleaner = ContentCleaner()
    scorer = Scorer()

    items = FeedItem.objects.filter(is_duplicate=False, trending_score=0)[:200]

    updated = 0
    for item in items:
        try:
            item = cleaner.clean(item)
            item = cleaner.classify_topic(item)
            item.trending_score = scorer.score(item)
            item.save(update_fields=['content_cleaned', 'topic', 'trending_score', 'language'])
            updated += 1
        except Exception as e:
            logger.exception("Failed to score item %d: %s", item.id, e)

    logger.info("recalculate_trending_scores: scored %d items", updated)
    return updated


@shared_task(queue='low')
def deduplicate_content():
    from .models import FeedItem

    items = FeedItem.objects.filter(is_duplicate=False).order_by('-fetched_at')
    from .services.content_cleaner import ContentCleaner

    cleaner = ContentCleaner()
    marked = 0

    for item in items:
        try:
            if cleaner.detect_duplicate(item):
                item.is_duplicate = True
                item.save(update_fields=['is_duplicate'])
                marked += 1
        except Exception as e:
            logger.exception("Dedup check failed for item %d: %s", item.id, e)

    logger.info("deduplicate_content: marked %d duplicates", marked)
    return marked


@shared_task(queue='low')
def analyze_user_profiles():
    from django.contrib.auth import get_user_model
    from .services.user_profiler import UserProfiler

    User = get_user_model()
    profiler = UserProfiler()
    processed = 0

    for user in User.objects.filter(is_active=True):
        try:
            profiler.analyze(user)
            processed += 1
        except Exception as e:
            logger.exception("Failed to analyze user %s: %s", user.email, e)

    logger.info("analyze_user_profiles: processed %d users", processed)
    return processed
