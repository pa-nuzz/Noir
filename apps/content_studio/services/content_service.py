import logging

from django.utils import timezone

from apps.social_accounts.services import SocialService

from ..generators import get_generator
from ..models import ContentApproval, ContentItem, ContentVersion

logger = logging.getLogger(__name__)


class ContentService:
    def __init__(self, user):
        self.user = user

    def generate_content(self, content_type, prompt, platform=None, tone=None, **kwargs):
        generator = get_generator(content_type, platform=platform, tone=tone)
        if not generator:
            return None

        if platform == 'all':
            from ..llm.llm_service import generate_llm_multi
            result = generate_llm_multi(content_type, prompt, tone=tone, **kwargs)
            if not result['success']:
                return None
            body = result['content']
            platform_data = result['platform_data']
            first_active = result.get('first_active')
        else:
            body = generator.generate(prompt, **kwargs)
            platform_data = {}
            first_active = None

        title = f"{dict(ContentItem.CONTENT_TYPES).get(content_type, 'Content')}: {prompt[:50]}"

        item = ContentItem.objects.create(
            user=self.user,
            title=title,
            content_type=content_type,
            body=body,
            platform=platform or '',
            platform_data=platform_data,
            is_auto_generated=True,
            source_prompt=prompt,
            metadata={'prompt': prompt, 'params': kwargs},
        )
        ContentVersion.objects.create(
            content_item=item,
            version_number=1,
            body=body,
            created_by=self.user,
            notes='Auto-generated',
        )
        return item

    def refine_content(self, item_id, feedback, **kwargs):
        item = ContentItem.objects.get(id=item_id, user=self.user)
        generator = get_generator(item.content_type, platform=item.platform)
        if not generator:
            item.body = f"[ERROR] Cannot refine unknown content type: {item.content_type}"
            item.save(update_fields=['body', 'updated_at'])
            return item
        new_body = generator.refine(item.body, feedback, **kwargs)

        item.body = new_body
        item.save(update_fields=['body', 'updated_at'])

        last_version = item.versions.first()
        version_num = (last_version.version_number + 1) if last_version else 1
        ContentVersion.objects.create(
            content_item=item,
            version_number=version_num,
            body=new_body,
            created_by=self.user,
            notes=f"Refined: {feedback[:100]}",
        )
        return item

    def approve_content(self, item_id, reviewer, decision, comment=''):
        item = ContentItem.objects.get(id=item_id)
        approval = ContentApproval.objects.create(
            content_item=item,
            reviewer=reviewer,
            decision=decision,
            comment=comment,
        )
        if decision == 'approved':
            item.status = 'approved'
            item.save(update_fields=['status'])
        elif decision == 'changes_requested':
            item.status = 'pending_review'
            item.save(update_fields=['status'])
        elif decision == 'rejected':
            item.status = 'draft'
            item.save(update_fields=['status'])
        return approval

    def get_available_generators(self):
        from ..generators import GENERATOR_REGISTRY
        type_map = dict(ContentItem.CONTENT_TYPES)
        return [{'key': k, 'name': type_map.get(k, k.replace('_', ' ').title())} for k in GENERATOR_REGISTRY]

    def list_content(self, content_type=None, status=None):
        qs = ContentItem.objects.filter(user=self.user)
        if content_type:
            qs = qs.filter(content_type=content_type)
        if status:
            qs = qs.filter(status=status)
        return qs

    def save_as_draft(self, item_id, account_ids):
        item = ContentItem.objects.get(id=item_id, user=self.user)
        social_service = SocialService(self.user)

        content = item.body
        hashtags = []
        if item.content_type == 'hashtag_set':
            hashtags = [t.lstrip('#').strip() for t in item.body.split() if t.strip()]

        media_urls = [asset.file.url for asset in item.attachments.all()]

        drafts = []
        for account_id in account_ids:
            post = social_service.create_post(
                account_id=account_id,
                content=content,
                media_urls=media_urls,
                link_url='',
                hashtags=hashtags,
                scheduled_at=None,
                content_item=item,
            )
            drafts.append(post)
        return drafts
