import logging
import re
from collections import Counter

from django.contrib.auth import get_user_model
from django.db.models import F, Q

from ..models import Topic, UserActivityProfile

logger = logging.getLogger(__name__)

User = get_user_model()

STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'by', 'with', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
    'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
    'can', 'could', 'should', 'may', 'might', 'shall', 'this', 'that',
    'these', 'those', 'it', 'its', 'you', 'your', 'we', 'our', 'they',
    'their', 'not', 'no', 'nor', 'so', 'if', 'as', 'all', 'each', 'every',
    'some', 'any', 'both', 'more', 'most', 'other', 'such', 'only', 'own',
    'about', 'into', 'over', 'after', 'before', 'between', 'under',
    'just', 'also', 'very', 'too', 'how', 'what', 'when', 'where', 'which',
    'who', 'whom', 'why',
}


class UserProfiler:
    def analyze(self, user) -> UserActivityProfile:
        profile, _ = UserActivityProfile.objects.get_or_create(user=user)
        keywords = self._extract_keywords(user)
        matched_topic_ids = self._match_topics(keywords)

        profile.inferred_keywords = keywords[:30]
        profile.inferred_topic_ids = [t for t in matched_topic_ids if t is not None]
        profile.last_analyzed_at = __import__('django').utils.timezone.now()
        profile.save()

        self._auto_subscribe(user, profile.inferred_topic_ids)

        return profile

    def _extract_keywords(self, user) -> list:
        texts = []

        try:
            ContentItem = __import__('apps.content_studio.models', fromlist=['ContentItem']).ContentItem
            for item in ContentItem.objects.filter(user=user).values_list('title', 'body', 'tags'):
                texts.append(item[0] or '')
                texts.append(item[1] or '')
                if isinstance(item[2], list):
                    texts.extend(str(t) for t in item[2])
        except Exception as e:
            logger.debug("Could not read ContentItems: %s", e)

        try:
            SocialPost = __import__('apps.social_accounts.models', fromlist=['SocialPost']).SocialPost
            for post in SocialPost.objects.filter(user=user).values_list('content', 'hashtags'):
                texts.append(post[0] or '')
                if isinstance(post[1], list):
                    texts.extend(str(h) for h in post[1])
        except Exception as e:
            logger.debug("Could not read SocialPosts: %s", e)

        try:
            Campaign = __import__('apps.campaigns.models', fromlist=['Campaign']).Campaign
            for c in Campaign.objects.filter(
                Q(owner=user) | Q(workspace__members__user=user)
            ).values_list('name', flat=True)[:20]:
                texts.append(c or '')
        except Exception as e:
            logger.debug("Could not read Campaigns: %s", e)

        text = ' '.join(texts).lower()
        words = re.findall(r'[a-zA-Z][a-zA-Z0-9#+]{2,}', text)
        words = [w for w in words if w.lower() not in STOP_WORDS and len(w) > 2]

        counter = Counter(words)
        return [word for word, _ in counter.most_common(50)]

    def _match_topics(self, keywords: list) -> list:
        keyword_set = set(k.lower() for k in keywords)
        matched_ids = []

        for topic in Topic.objects.filter(is_active=True):
            topic_kws = set(k.lower() for k in (topic.keywords or []))
            if keyword_set & topic_kws:
                matched_ids.append(topic.id)

        return matched_ids

    def _auto_subscribe(self, user, topic_ids: list):
        if not topic_ids:
            return

        from ..models import UserTopicPreference

        existing = set(
            UserTopicPreference.objects.filter(
                user=user, is_auto_detected=True
            ).values_list('topic_id', flat=True)
        )

        to_create = []
        for tid in topic_ids:
            if tid not in existing:
                to_create.append(UserTopicPreference(
                    user=user,
                    topic_id=tid,
                    is_auto_detected=True,
                ))

        if to_create:
            UserTopicPreference.objects.bulk_create(to_create, ignore_conflicts=True)
            Topic.objects.filter(id__in=topic_ids).update(
                subscriber_count=F('subscriber_count') + 1
            )

        stale = existing - set(topic_ids)
        if stale:
            UserTopicPreference.objects.filter(
                user=user, topic_id__in=stale, is_auto_detected=True
            ).delete()
