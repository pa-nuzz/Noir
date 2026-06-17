"""
Management command to backfill existing records with audit field values.

For models that previously had created_at/updated_at, this copies:
  - created_at → postdatead
  - created_at time → posttime
  - updated_at → modifydatead
  - updated_at time → modifytime

Also backfills postdatebs / modifydatebs from the AD dates.
"""
import logging

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import models
from django.utils import timezone

from core.utils.nepali_calendar import ad_to_bs

logger = logging.getLogger(__name__)

# Models that inherit from AuditMixin and their existing date field names
# Format: ('app_label', 'ModelName', 'created_at', 'updated_at')
MODEL_DATE_FIELDS = [
    # Models with both created_at and updated_at
    ('api_keys', 'WorkspaceAPIKey', 'created_at', 'updated_at'),
    ('automations', 'Workflow', 'created_at', 'updated_at'),
    ('automations', 'WorkflowNode', 'created_at', 'updated_at'),
    ('automations', 'WorkflowEnrollment', 'created_at', 'updated_at'),
    ('billing', 'StoragePlan', 'created_at', 'updated_at'),
    ('billing', 'WorkspaceBilling', 'created_at', 'updated_at'),
    ('billing', 'Plan', 'created_at', 'updated_at'),
    ('billing', 'Subscription', 'created_at', 'updated_at'),
    ('campaigns', 'Campaign', 'created_at', 'updated_at'),
    ('campaigns', 'CampaignVariant', 'created_at', 'updated_at'),
    ('contacts', 'ContactList', 'created_at', 'updated_at'),
    ('contacts', 'ContactSegment', 'created_at', 'updated_at'),
    ('contacts', 'Contact', 'created_at', 'updated_at'),
    ('content', 'ContentGeneration', 'created_at', 'updated_at'),
    ('content_studio', 'ContentItem', 'created_at', 'updated_at'),
    ('creative', 'CreativeContext', 'created_at', 'updated_at'),
    ('creative', 'CreativeStrategy', 'created_at', 'updated_at'),
    ('inbox', 'EmailInbox', 'created_at', 'updated_at'),
    ('inbox', 'EmailThread', 'created_at', 'updated_at'),
    ('inbox', 'EmailDraft', 'created_at', 'updated_at'),
    ('media', 'MediaFolder', 'created_at', 'updated_at'),
    ('media', 'MediaAsset', 'created_at', 'updated_at'),
    ('media_assets', 'MediaFolder', 'created_at', 'updated_at'),
    ('media_assets', 'MediaAsset', 'created_at', 'updated_at'),
    ('notifications', 'Notification', 'created_at', 'updated_at'),
    ('social', 'SocialAccount', 'created_at', 'updated_at'),
    ('social', 'SocialPost', 'created_at', 'updated_at'),
    ('social_accounts', 'SocialAccount', 'created_at', 'updated_at'),
    ('social_accounts', 'SocialPost', 'created_at', 'updated_at'),
    ('trending', 'UserActivityProfile', 'created_at', 'updated_at'),
    ('trending', 'CurrentItem', 'created_at', 'updated_at'),
    ('webhooks', 'WebhookEndpoint', 'created_at', 'updated_at'),
    ('workspaces', 'Workspace', 'created_at', 'updated_at'),
    ('workspaces', 'WorkspaceMembership', 'created_at', 'updated_at'),
    ('workspaces', 'WorkspacePermission', 'created_at', 'updated_at'),
    ('workspaces', 'WorkspaceStorageConfig', 'created_at', 'updated_at'),
    ('workspaces', 'WorkspaceOnboarding', 'created_at', 'updated_at'),

    # Models with only created_at
    ('accounts', 'User', 'created_at', None),
    ('automations', 'WorkflowEdge', 'created_at', None),
    ('campaigns', 'CampaignAttachment', 'uploaded_at', None),
    ('campaigns', 'EmailEngagement', 'sent_at', None),
    ('campaigns', 'EmailClickEvent', 'clicked_at', None),
    ('campaigns', 'EmailUnsubscribe', 'created_at', None),
    ('campaigns', 'EmailTemplate', 'created_at', None),
    ('campaigns', 'TemplateImage', 'uploaded_at', None),
    ('contacts', 'ContactTag', 'created_at', None),
    ('contacts', 'ContactCustomField', 'created_at', None),
    ('contacts', 'ContactCustomFieldValue', None, None),
    ('content', 'ContentVersion', 'created_at', None),
    ('content_studio', 'ContentVersion', 'created_at', None),
    ('content_studio', 'ContentApproval', 'created_at', None),
    ('content_studio', 'ExcelSheetImport', 'created_at', None),
    ('content_studio', 'ExcelSheetRowLog', 'created_at', None),
    ('content_studio', 'UserGoogleSheetsToken', 'created_at', None),
    ('content_studio', 'UserGoogleSheet', 'created_at', None),
    ('content_studio', 'DeletedDriveSheet', 'created_at', None),
    ('creative', 'CreativeStrategyAsset', 'created_at', None),
    ('dashboard', 'Notification', 'created_at', None),
    ('inbox', 'EmailMessage', 'received_at', None),
    ('locks', 'EditLock', 'locked_at', None),
    ('media_assets', 'MediaTag', 'created_at', None),
    ('senders', 'Sender', 'created_at', None),
    ('social', 'SocialMediaAnalytics', 'fetched_at', None),
    ('social_accounts', 'SocialAnalytics', 'fetched_at', None),
    ('trending', 'Topic', 'created_at', None),
    ('trending', 'ContentSource', 'created_at', None),
    ('trending', 'FeedItem', 'fetched_at', None),
    ('trending', 'UserTopicPreference', 'subscribed_at', None),
    ('trending', 'UserFeedInteraction', 'created_at', None),
    ('webhooks', 'WebhookDelivery', 'created_at', None),
    ('workspaces', 'TeamInvitation', 'created_at', None),
    ('workspaces', 'AuditLog', 'created_at', None),
    ('workspaces', 'WorkspaceSocialAccount', 'created_at', None),
    ('workspaces', 'WorkspaceQuota', 'updated_at', None),
]


class Command(BaseCommand):
    help = 'Backfill AuditMixin fields (postdatead, posttime, postdatebs, modify*) from existing date fields'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without saving',
        )
        parser.add_argument(
            '--app',
            type=str,
            default='',
            help='Only backfill models in this app (e.g. --app=campaigns)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        app_filter = options['app']

        total_updated = 0
        total_skipped = 0

        for app_label, model_name, created_field, updated_field in MODEL_DATE_FIELDS:
            if app_filter and app_label != app_filter:
                continue

            try:
                model = apps.get_model(app_label, model_name)
            except LookupError:
                self.stdout.write(f'Skipping {app_label}.{model_name}: model not found')
                continue

            if model is None:
                continue

            if not hasattr(model, 'postdatead'):
                self.stdout.write(f'Skipping {app_label}.{model_name}: no AuditMixin fields')
                continue

            qs = model.objects.all()
            batch_updated = 0

            for obj in qs.iterator(chunk_size=200):
                changed = False

                if created_field and hasattr(obj, created_field):
                    val = getattr(obj, created_field)
                    if val and not obj.postdatead:
                        if isinstance(val, str):
                            continue
                        obj.postdatead = val
                        obj.posttime = val.time() if hasattr(val, 'time') else val
                        obj.postdatebs = ad_to_bs(val)
                        changed = True

                if updated_field and hasattr(obj, updated_field):
                    val = getattr(obj, updated_field)
                    if val and not obj.modifydatead:
                        if isinstance(val, str):
                            continue
                        obj.modifydatead = val
                        obj.modifytime = val.time() if hasattr(val, 'time') else val
                        obj.modifydatebs = ad_to_bs(val)
                        changed = True

                if changed:
                    if not dry_run:
                        obj.save(update_fields=[
                            'postdatead', 'posttime', 'postdatebs',
                            'modifydatead', 'modifytime', 'modifydatebs',
                        ])
                    batch_updated += 1

            if batch_updated:
                self.stdout.write(f'{app_label}.{model_name}: backfilled {batch_updated} records')
            total_updated += batch_updated
            total_skipped += qs.count() - batch_updated

        self.stdout.write(self.style.SUCCESS(
            f'Done. {total_updated} records updated, {total_skipped} already had values.'
        ))
