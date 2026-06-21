import logging
from datetime import datetime

from django.utils import timezone

from .models import SocialAccount, SocialAnalytics, SocialPost
from .platforms import get_platform, PLATFORM_REGISTRY
from .rate_limiter import rate_limiter

logger = logging.getLogger(__name__)


class SocialService:
    def __init__(self, user):
        self.user = user

    def get_available_platforms(self):
        return [{'key': k, 'name': v.label if hasattr(v, 'label') else k.title()} for k, v in PLATFORM_REGISTRY.items()]

    def connect_account(self, platform, access_token, account_data, refresh_token='', token_expires_at=None, workspace=None):
        account, created = SocialAccount.objects.update_or_create(
            user=self.user,
            platform=platform,
            account_id=account_data.get('account_id', ''),
            defaults={
                'account_name': account_data.get('account_name', ''),
                'avatar_url': account_data.get('avatar_url', ''),
                'profile_url': account_data.get('profile_url', ''),
                'access_token': access_token,
                'refresh_token': refresh_token,
                'token_expires_at': token_expires_at,
                'is_active': True,
            },
        )
        if workspace:
            from apps.workspaces.models import WorkspaceSocialAccount
            WorkspaceSocialAccount.objects.get_or_create(
                workspace=workspace,
                account=account,
                defaults={'added_by': self.user},
            )
        return account, created

    def disconnect_account(self, account_id):
        account = SocialAccount.objects.get(id=account_id, user=self.user)
        account.delete()

    def get_accounts(self, platform=None):
        qs = SocialAccount.objects.filter(user=self.user)
        if platform:
            qs = qs.filter(platform=platform)
        return qs

    def create_post(self, account_id, content, media_urls=None, link_url=None, hashtags=None, scheduled_at=None, workspace=None, content_item=None):
        account = SocialAccount.objects.get(id=account_id, user=self.user)
        post = SocialPost.objects.create(
            user=self.user,
            account=account,
            platform=account.platform,
            content=content,
            media_urls=media_urls or [],
            link_url=link_url or '',
            hashtags=hashtags or [],
            scheduled_at=scheduled_at,
            status='scheduled' if scheduled_at else 'draft',
            workspace=workspace,
            content_item=content_item,
        )
        return post

    def create_bulk_posts(self, account_ids, content, media_urls=None, link_url=None, hashtags=None, scheduled_at=None, workspace=None, content_item=None):
        accounts = SocialAccount.objects.filter(id__in=account_ids, user=self.user)
        posts = []
        for account in accounts:
            post = SocialPost.objects.create(
                user=self.user,
                account=account,
                platform=account.platform,
                content=content,
                media_urls=media_urls or [],
                link_url=link_url or '',
                hashtags=hashtags or [],
                scheduled_at=scheduled_at,
                status='scheduled' if scheduled_at else 'draft',
                workspace=workspace,
                content_item=content_item,
            )
            posts.append(post)
        return posts

    def publish_post(self, post_id):
        post = SocialPost.objects.get(id=post_id, user=self.user)
        platform = get_platform(post.platform, post.account)

        if post.status == 'published':
            return None

        post.status = 'publishing'
        post.save(update_fields=['status'])

        if not rate_limiter.check(post.platform):
            logger.warning(f"Rate limit hit for {post.platform}")
            post.status = 'failed'
            post.error_message = 'Rate limit exceeded. Try again later.'
            post.save(update_fields=['status', 'error_message'])
            
            # Trigger social_post.failed webhook
            from apps.webhooks.utils import dispatch_webhook_event
            workspace_id = post.workspace_id
            if workspace_id:
                dispatch_webhook_event(
                    workspace_id=workspace_id,
                    event_type='social_post.failed',
                    payload={
                        'post_id': post.id,
                        'platform': post.platform,
                        'workspace_id': workspace_id,
                        'error_message': post.error_message,
                        'failed_at': timezone.now().isoformat(),
                    }
                )
            return None

        try:
            content = post.content
            if post.hashtags:
                hashtag_text = ' '.join(f'#{h.lstrip("#")}' for h in post.hashtags)
                content = f"{content}\n\n{hashtag_text}" if content else hashtag_text
            result = platform.publish_post(
                content=content,
                media_urls=post.media_urls,
                link_url=post.link_url or None,
                scheduled_at=post.scheduled_at,
            )
            if result:
                post.status = 'published'
                post.published_at = timezone.now()
                post.platform_post_id = result.get('post_id', '')
                post.platform_post_url = result.get('url', '')
                post.save(update_fields=['status', 'published_at', 'platform_post_id', 'platform_post_url'])
                rate_limiter.consume(post.platform)
                
                # Trigger social_post.published webhook
                from apps.webhooks.utils import dispatch_webhook_event
                workspace_id = post.workspace_id
                if workspace_id:
                    dispatch_webhook_event(
                        workspace_id=workspace_id,
                        event_type='social_post.published',
                        payload={
                            'post_id': post.id,
                            'platform': post.platform,
                            'workspace_id': workspace_id,
                            'platform_post_id': post.platform_post_id,
                            'platform_post_url': post.platform_post_url,
                            'published_at': post.published_at.isoformat() if post.published_at else None,
                        }
                    )
                return result
            else:
                post.status = 'failed'
                post.error_message = 'Platform returned empty result'
                post.save(update_fields=['status', 'error_message'])
                
                # Trigger social_post.failed webhook
                from apps.webhooks.utils import dispatch_webhook_event
                workspace_id = post.workspace_id
                if workspace_id:
                    dispatch_webhook_event(
                        workspace_id=workspace_id,
                        event_type='social_post.failed',
                        payload={
                            'post_id': post.id,
                            'platform': post.platform,
                            'workspace_id': workspace_id,
                            'error_message': post.error_message,
                            'failed_at': timezone.now().isoformat(),
                        }
                    )
        except Exception as e:
            logger.exception(f"Publish failed for post {post_id}")
            post.status = 'failed'
            post.error_message = str(e)
            post.save(update_fields=['status', 'error_message'])
            
            # Trigger social_post.failed webhook
            from apps.webhooks.utils import dispatch_webhook_event
            workspace_id = post.workspace_id
            if workspace_id:
                dispatch_webhook_event(
                    workspace_id=workspace_id,
                    event_type='social_post.failed',
                    payload={
                        'post_id': post.id,
                        'platform': post.platform,
                        'workspace_id': workspace_id,
                        'error_message': post.error_message,
                        'failed_at': timezone.now().isoformat(),
                    }
                )
        return None

    def publish_bulk_posts(self, post_ids):
        results = []
        for post_id in post_ids:
            result = self.publish_post(post_id)
            results.append({'post_id': post_id, 'success': result is not None})
        return results

    def update_post(self, post_id, content, media_urls=None, link_url=None, hashtags=None, scheduled_at=None):
        post = SocialPost.objects.get(id=post_id, user=self.user)
        if post.status not in ('draft', 'scheduled'):
            raise ValueError('Only draft or scheduled posts can be edited.')
        post.content = content
        post.media_urls = media_urls or []
        post.link_url = link_url or ''
        post.hashtags = hashtags or []
        post.scheduled_at = scheduled_at
        if scheduled_at and post.status == 'draft':
            post.status = 'scheduled'
        elif not scheduled_at and post.status == 'scheduled':
            post.status = 'draft'
        post.save(update_fields=['content', 'media_urls', 'link_url', 'hashtags', 'scheduled_at', 'status'])
        return post

    def schedule_post(self, post_id, scheduled_at):
        post = SocialPost.objects.get(id=post_id, user=self.user)
        post.scheduled_at = scheduled_at
        post.status = 'scheduled'
        post.save(update_fields=['scheduled_at', 'status'])
        return post

    def fetch_analytics(self, post_id):
        post = SocialPost.objects.get(id=post_id, user=self.user)
        platform = get_platform(post.platform, post.account)
        data = platform.get_post_analytics(post.platform_post_id)
        if data:
            return SocialAnalytics.objects.create(
                post=post,
                impressions=data.get('impressions', 0) or data.get('view_count', 0) or data.get('impressions', 0),
                reach=data.get('reach', 0),
                likes=data.get('likes', 0) or data.get('like_count', 0),
                shares=data.get('shares', 0) or data.get('share_count', 0),
                comments=data.get('comments', 0) or data.get('comment_count', 0),
                clicks=data.get('clicks', 0),
                saves=data.get('saves', 0),
                engagement_rate=data.get('engagement_rate', 0.0),
                raw_data=data,
            )
        return None

    def get_connected_platforms_summary(self):
        accounts = SocialAccount.objects.filter(user=self.user)
        return {
            'total': accounts.count(),
            'active': accounts.filter(is_active=True).count(),
            'by_platform': {
                p: accounts.filter(platform=p).count()
                for p, _ in SocialAccount.PLATFORM_CHOICES
            },
        }
