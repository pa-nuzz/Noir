import logging
from datetime import timedelta
from datetime import datetime, timezone

from celery import shared_task
from django.utils import timezone as tz

logger = logging.getLogger(__name__)


@shared_task(queue='low')
def collect_all_sources(force=False):
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
        recalculate_trending_scores.delay()
        deduplicate_content.delay()

    logger.info("collect_all_sources complete: %d new items", total_created)
    return total_created


@shared_task(queue='low')
def recalculate_trending_scores():
    from django.db import close_old_connections
    close_old_connections()

    from django.db.models import Q
    from .models import FeedItem, Topic
    from .services.categorizer import Categorizer
    from .services.content_cleaner import ContentCleaner
    from .services.scorer import Scorer

    cleaner = ContentCleaner()
    categorizer = Categorizer()
    scorer = Scorer()

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


@shared_task(queue='low')
def deduplicate_content():
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


@shared_task(queue='low')
def analyze_user_profiles():
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


@shared_task(queue='low')
def run_automation():
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


@shared_task(queue='low')
def generate_currents_snapshots():
    import json
    import re
    import uuid
    from django.db import close_old_connections
    from django.contrib.auth import get_user_model
    from django.utils import timezone
    from .models import TrendingAutomationRule, FeedItem, CurrentsSnapshot

    close_old_connections()
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

        # Per-user freshness guard — skip if snapshot is less than 1 hour old
        last_snap = CurrentsSnapshot.objects.filter(user=user).order_by('-created_at').first()
        if last_snap and (timezone.now() - last_snap.created_at) < timedelta(hours=1):
            logger.info("Skipping user %s — snapshot fresh enough", uid)
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
            from apps.content_studio.llm.llm_service import _call_llm_fatal, LLMPipelineError
            from apps.content_studio.llm.critique_prompts import build_batch_critic_prompt, build_batch_refiner_prompt

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
                    f"Please completely rewrite the entire JSON array, fixing all issues raised."
                )
                refined = _call_llm_fatal('refiner', refiner_sys, refiner_user)
                result_content = refined
            except LLMPipelineError as e:
                logger.error("3-agent pipeline failed for user %s: %s", uid, e)
                raise

            gen_map = {}
            if result_content:
                text = result_content.strip()
                json_match = re.search(r'\[.*\]', text, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group())
                    gen_map = {entry['id']: entry for entry in parsed if 'id' in entry}

            close_old_connections()

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
                close_old_connections()
                CurrentsSnapshot.objects.bulk_create(snapshots)

                # Prune old batches — keep only the 2 most recent per user
                from django.db.models import Max
                stale = CurrentsSnapshot.objects.filter(
                    user=user
                ).values('batch_id').annotate(
                    last_created=Max('created_at')
                ).order_by('-last_created')[2:]
                stale_ids = [b['batch_id'] for b in stale]
                if stale_ids:
                    CurrentsSnapshot.objects.filter(
                        user=user, batch_id__in=stale_ids
                    ).delete()

            users_processed += 1

        except Exception as e:
            logger.exception("generate_currents_snapshots failed for user %s: %s", uid, e)
            continue

    logger.info(
        "generate_currents_snapshots complete: batch_id=%s, users=%d",
        batch_id, users_processed,
    )
    return batch_id
