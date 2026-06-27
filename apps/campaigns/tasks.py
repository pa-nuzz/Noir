import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

from core.tenant import tenant_context
from apps.workspaces.models import Workspace

logger = logging.getLogger(__name__)

STUCK_SENDING_THRESHOLD_MINUTES = 30


@shared_task
def recover_stuck_sending_campaigns():
    from django.db import close_old_connections
    from apps.campaigns.models import Campaign

    close_old_connections()
    threshold = timezone.now() - timedelta(minutes=STUCK_SENDING_THRESHOLD_MINUTES)
    stuck = Campaign.objects.filter(
        status='sending',
        updated_at__lt=threshold,
    )
    count = 0
    for campaign in stuck:
        campaign.status = 'failed'
        campaign.save(update_fields=['status', 'updated_at'])
        logger.warning(
            f"[Recovery] Campaign '{campaign.name}' (id={campaign.id}) was stuck in 'sending' "
            f"since {campaign.updated_at} — marked as 'failed'."
        )
        count += 1
    if count:
        logger.info(f"[Recovery] Recovered {count} stuck campaign(s).")
    return count


@shared_task
def run_scheduled_campaigns_task():
    from .services import run_scheduled_campaigns
    from apps.workspaces.models import Workspace

    for workspace in Workspace.objects.all():
        with tenant_context(workspace):
            run_scheduled_campaigns()

    from django.db import close_old_connections
    close_old_connections()
    from apps.campaigns.models import Campaign
    from core.tenant import get_current_tenant

    saved_tenant = get_current_tenant()
    try:
        from core.tenant import set_current_tenant
        set_current_tenant(None)
        personal_campaigns = Campaign.objects.filter(
            status='scheduled',
            scheduled_at__isnull=False,
            scheduled_at__lte=__import__('django').utils.timezone.now(),
            workspace__isnull=True,
        ).select_related('sender', 'user')
        for campaign in personal_campaigns:
            try:
                campaign.status = 'sending'
                campaign.save(update_fields=['status', 'updated_at'])
                from .services.delivery import send_campaign_with_smtp
                base_url = __import__('django').conf.settings.TRACKING_BASE_URL or ''
                sent, failed, err = send_campaign_with_smtp(campaign, base_url)
                campaign.refresh_from_db()
                campaign.sent_count = (campaign.sent_count or 0) + sent
                campaign.bounce_count = (campaign.bounce_count or 0) + failed
                campaign.status = 'sent' if sent > 0 else 'failed'
                campaign.save(update_fields=['sent_count', 'bounce_count', 'status', 'updated_at'])
            except Exception as e:
                logger.error(f"Error sending personal campaign {campaign.id}: {e}")
                campaign.status = 'failed'
                campaign.save(update_fields=['status', 'updated_at'])
    finally:
        from core.tenant import set_current_tenant
        set_current_tenant(saved_tenant)


@shared_task(bind=True, max_retries=3)
def evaluate_ab_test_winner(self, campaign_id: int, workspace_id: int = None):
    """
    Evaluate A/B test variants after the test window expires.
    Picks the winner based on open rate, marks the campaign as completed,
    and stores the winning variant reference on the campaign.
    """
    try:
        from apps.campaigns.models import Campaign

        if workspace_id:
            try:
                workspace = Workspace.objects.get(pk=workspace_id)
            except Workspace.DoesNotExist:
                logger.error(f"[A/B Test] Workspace {workspace_id} not found — aborting.")
                return
        else:
            workspace = None

        with tenant_context(workspace):
            try:
                campaign = Campaign.objects.get(pk=campaign_id)
            except Campaign.DoesNotExist:
                logger.error(f"[A/B Test] Campaign {campaign_id} not found — aborting.")
                return

            if campaign.ab_test_status != 'running':
                logger.info(f"[A/B Test] Campaign {campaign_id} is not in running state ({campaign.ab_test_status}) — skipping.")
                return

            variants = list(campaign.variants.all().order_by('label'))
            if len(variants) < 2:
                logger.warning(f"[A/B Test] Campaign {campaign_id} has fewer than 2 variants — cannot evaluate.")
                return

            best_variant = max(variants, key=lambda v: v.open_rate)

            campaign.winner_variant = best_variant
            campaign.ab_test_status = 'completed'
            campaign.save(update_fields=['winner_variant', 'ab_test_status', 'updated_at'])

            logger.info(
                f"[A/B Test] Campaign {campaign_id}: Winner is Variant {best_variant.label} "
                f"with {best_variant.open_rate}% open rate (sent: {best_variant.sent_count}, opens: {best_variant.open_count})."
            )

    except Exception as exc:
        logger.error(f"[A/B Test] Error evaluating winner for campaign {campaign_id}: {exc}")
        raise self.retry(exc=exc, countdown=60)


def run_send_campaign(campaign_id: int, base_url: str, recipients_override: list = None):
    """Synchronous send - used by both Celery task and view fallback."""
    from django.db import close_old_connections
    from apps.campaigns.models import Campaign
    from .services.delivery import send_campaign_with_smtp

    close_old_connections()

    try:
        campaign = Campaign.objects.get(pk=campaign_id)
    except Campaign.DoesNotExist:
        return 0, 0, "Campaign not found"

    workspace = campaign.workspace
    with tenant_context(workspace):
        logger.info(f"[Send] Starting campaign '{campaign.name}' (id={campaign_id})")

        try:
            campaign.status = 'sending'
            campaign.save(update_fields=['status', 'updated_at'])
            
            sent_count, failed_count, last_error = send_campaign_with_smtp(
                campaign, base_url, recipients_override=recipients_override,
            )

            campaign.refresh_from_db()
            campaign.sent_count = (campaign.sent_count or 0) + sent_count
            campaign.bounce_count = (campaign.bounce_count or 0) + failed_count
            campaign.status = 'sent' if sent_count > 0 else 'failed'
            campaign.save(update_fields=['sent_count', 'bounce_count', 'status', 'updated_at'])

            # Trigger outbound webhooks
            from django.utils import timezone
            from apps.webhooks.utils import dispatch_webhook_event
            workspace_id = campaign.workspace_id
            if workspace_id:
                dispatch_webhook_event(
                    workspace_id=workspace_id,
                    event_type='campaign.sent',
                    payload={
                        'campaign_id': campaign.id,
                        'campaign_name': campaign.name,
                        'workspace_id': workspace_id,
                        'sent_count': sent_count,
                        'failed_count': failed_count,
                        'status': campaign.status,
                        'sent_at': timezone.now().isoformat(),
                    }
                )
                if failed_count > 0:
                    dispatch_webhook_event(
                        workspace_id=workspace_id,
                        event_type='campaign.bounced',
                        payload={
                            'campaign_id': campaign.id,
                            'campaign_name': campaign.name,
                            'workspace_id': workspace_id,
                            'failed_count': failed_count,
                            'bounce_rate': campaign.bounce_rate,
                            'bounced_at': timezone.now().isoformat(),
                        }
                    )

            if failed_count > 0:
                logger.warning(
                    f"[Send] Campaign '{campaign.name}': sent={sent_count}, failed={failed_count}. "
                    f"{last_error or ''}"
                )
            else:
                logger.info(f"[Send] Campaign '{campaign.name}' sent successfully to {sent_count} recipients.")
            return sent_count, failed_count, last_error

        except Exception as exc:
            logger.error(f"[Send] Campaign '{campaign.name}' failed: {exc}")
            campaign.refresh_from_db()
            campaign.status = 'failed'
            campaign.save(update_fields=['status', 'updated_at'])
            return 0, 0, str(exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def async_send_campaign(self, campaign_id: int, base_url: str, recipients_override: list = None, workspace_id: int = None):
    """Send a campaign in the background with rate limiting and retry logic.

    Called by views to move bulk sending off the HTTP request thread.
    Updates campaign status to 'sent' when all recipients are processed.
    """
    try:
        from django.db import close_old_connections
        close_old_connections()
        sent, failed, error = run_send_campaign(campaign_id, base_url, recipients_override)
        logger.info(f"[AsyncSend] Campaign {campaign_id} completed: sent={sent}, failed={failed}")
        return {'sent': sent, 'failed': failed, 'error': error}
    except Exception as exc:
        logger.error(f"[AsyncSend] Campaign {campaign_id} failed: {exc}")
        try:
            raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))
        except Exception:
            logger.error(f"[AsyncSend] Campaign {campaign_id} exhausted all retries.")
            from apps.campaigns.models import Campaign
            try:
                campaign = Campaign.objects.get(pk=campaign_id)
                campaign.status = 'failed'
                campaign.save(update_fields=['status', 'updated_at'])
            except Campaign.DoesNotExist:
                logger.error(f"[AsyncSend] Campaign {campaign_id} no longer exists — skipping status update.")
            return {'sent': 0, 'failed': 0, 'error': str(exc)}
