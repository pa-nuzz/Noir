import logging
from datetime import datetime, timezone

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(queue='low')
def collect_all_sources():
    from .models import ContentSource
    from .services.github_collector import GitHubCollector
    from .services.rss_collector import RSSCollector
    from .services.web_scraper import WebScraper

    sources = ContentSource.objects.filter(is_active=True)
    collectors = {
        'rss': RSSCollector(),
        'api': GitHubCollector(),
        'web': WebScraper(),
    }

    total_created = 0

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
    from .services.categorizer import Categorizer
    from .services.content_cleaner import ContentCleaner
    from .services.scorer import Scorer
    from .services.summarizer import Summarizer

    cleaner = ContentCleaner()
    categorizer = Categorizer()
    summarizer = Summarizer()
    scorer = Scorer()

    items = FeedItem.objects.filter(is_duplicate=False, trending_score=0)[:200]

    updated = 0
    for item in items:
        try:
            item = cleaner.clean(item)
            item = categorizer.categorize(item)
            item = summarizer.summarize(item)
            item.trending_score = scorer.score(item)
            item.save(update_fields=[
                'content_cleaned', 'topic', 'trending_score', 'language',
                'ai_summary', 'ai_categories',
            ])
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


@shared_task(queue='low')
def run_automation():
    from datetime import timedelta
    from django.utils import timezone
    from .models import TrendingAutomationRule, FeedItem
    from .views import _generate_llm_content

    rules = TrendingAutomationRule.objects.filter(is_active=True).select_related('user', 'topic')
    processed = 0

    for rule in rules:
        try:
            interval_hours = {
                'hourly': 1,
                'every_6h': 6,
                'daily': 24,
                'weekly': 168,
            }.get(rule.schedule_interval, 24)

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

            content_items = _generate_llm_content(rule.user, rule.topic, platforms, items, rule.id)

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

        except Exception as e:
            logger.exception(
                "Automation rule failed for user %s topic %s: %s",
                rule.user.email, rule.topic.name, e,
            )

    logger.info("run_automation: processed %d items from %d rules", processed, rules.count())
    return processed


@shared_task(queue='low')
def generate_currents_snapshots():
    import re
    import uuid
    from django.contrib.auth import get_user_model
    from django.utils import timezone
    from .models import TrendingAutomationRule, FeedItem, CurrentsSnapshot

    User = get_user_model()
    user_ids = set(
        TrendingAutomationRule.objects.filter(is_active=True)
        .exclude(platforms=[])
        .values_list('user', flat=True)
    )

    if not user_ids:
        logger.info("generate_currents_snapshots: no active rules found")
        return

    batch_id = uuid.uuid4().hex[:32]
    users_processed = 0

    for uid in user_ids:
        try:
            user = User.objects.get(id=uid)
        except User.DoesNotExist:
            continue

        try:
            rules = TrendingAutomationRule.objects.filter(
                user=user, is_active=True,
            ).exclude(platforms=[]).select_related('topic')

            topic_platforms = {r.topic_id: r.platforms for r in rules}
            all_active_platforms = sorted(set(
                p for plats in topic_platforms.values() for p in plats
            ))

            # Top 5 per category → overall top 5
            from itertools import chain
            candidates = list(chain.from_iterable(
                FeedItem.objects.filter(
                    is_duplicate=False, topic_id=tid,
                ).select_related('topic', 'source').order_by('-trending_score')[:5]
                for tid in topic_platforms
            ))
            candidates.sort(key=lambda x: x.trending_score, reverse=True)
            items = candidates[:5]
            if not items:
                continue

            # Batched LLM call
            from apps.content_studio.llm.llm_service import _call_llm

            prompt_parts = []
            for item in items:
                title = item.title or ''
                summary = item.ai_summary or item.content_cleaned or ''
                prompt_parts.append(f"ITEM {item.id}:\nTitle: {title}\nSummary: {summary[:500]}\n")

            platform_reqs = {
                'linkedin': '- linkedin: Professional, thought-leadership, 1300-2000 chars, 3-5 hashtags',
                'twitter': '- twitter: Concise, under 280 chars, 1-2 hashtags',
                'instagram': '- instagram: Visual-first, 150-220 chars before \'more\', 5-8 hashtags',
                'facebook': '- facebook: Conversational, 150-500 chars, 2-4 hashtags',
                'tiktok': '- tiktok: Casual and punchy, under 100 chars, 1-3 hashtags',
            }
            req_lines = [platform_reqs[p] for p in all_active_platforms if p in platform_reqs]
            if not req_lines:
                req_lines = [f'- {p}: Standard social media post' for p in all_active_platforms]

            platform_entries = '\n'.join(
                f'      "{p}": {{"body": "...", "hashtags": "#tag1 #tag2"}},' for p in all_active_platforms
            )

            system_prompt = (
                "You are a social media content strategist. For each news item below, generate "
                "a platform-optimized post with relevant hashtags for each applicable platform.\n\n"
                "Platforms and their requirements:\n" + "\n".join(req_lines) + "\n\n"
                "For each item, follow this structure:\n"
                "- HOOK: bold statement or question (under 15 words)\n"
                "- BODY: deliver the core message in the platform's style\n"
                "- CTA: End with an engaging question or action\n\n"
                "Return ONLY a valid JSON array:\n"
                "[\n"
                "  {\n"
                '    "id": <item_id>,\n'
                '    "platforms": {\n'
                + platform_entries +
                "\n    }\n"
                "  },\n"
                "  ...\n"
                "]\n\n"
                "Do NOT include markdown code fences, backticks, or any text outside the JSON array."
            )

            user_prompt = "\n---\n".join(prompt_parts)
            result = _call_llm(system_prompt, user_prompt)

            gen_map = {}
            if result['success'] and result['content']:
                text = result['content'].strip()
                json_match = re.search(r'\[.*\]', text, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    gen_map = {entry['id']: entry for entry in parsed if 'id' in entry}

            snapshots = []
            for item in items:
                entry = gen_map.get(item.id, {})
                platforms_data = {}
                active = topic_platforms.get(item.topic_id, all_active_platforms)

                if isinstance(entry, dict) and isinstance(entry.get('platforms'), dict):
                    for p, info in entry['platforms'].items():
                        if p in active and isinstance(info, dict):
                            platforms_data[p] = {
                                'body': info.get('body', ''),
                                'hashtags': info.get('hashtags', ''),
                            }

                snapshots.append(CurrentsSnapshot(
                    user=user,
                    feed_item=item,
                    topic=item.topic,
                    platforms_data=platforms_data,
                    batch_id=batch_id,
                ))

            if snapshots:
                CurrentsSnapshot.objects.bulk_create(snapshots)

            users_processed += 1

        except Exception as e:
            logger.exception("generate_currents_snapshots failed for user %s: %s", uid, e)
            continue

    logger.info(
        "generate_currents_snapshots complete: batch_id=%s, users=%d",
        batch_id, users_processed,
    )
    return batch_id
