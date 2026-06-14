from datetime import datetime

from django.urls import reverse
from django.utils import timezone

from apps.campaigns.models import Campaign
from apps.senders.models import Sender
from apps.workspaces.models import TeamInvitation


def _build_notifications(user, dismissed_at):
    notifications = []
    now = timezone.now()

    senders_qs = Sender.objects.filter(user=user)
    campaigns_qs = Campaign.objects.filter(user=user)

    active_senders_count = senders_qs.filter(is_active=True).count()
    latest_sender = senders_qs.order_by('-created_at').first()

    if active_senders_count == 0:
        notifications.append(
            {
                'title': 'No active sender connected',
                'message': 'Add and verify an SMTP sender before launching campaigns.',
                'tone': 'warning',
                'url': reverse('dashboard:settings'),
                'created_at': latest_sender.created_at if latest_sender else user.date_joined,
            }
        )
    else:
        notifications.append(
            {
                'title': f"{active_senders_count} active sender{'' if active_senders_count == 1 else 's'} ready",
                'message': 'Your SMTP configuration is available for outgoing campaigns.',
                'tone': 'success',
                'url': reverse('dashboard:settings'),
                'created_at': latest_sender.created_at if latest_sender else user.date_joined,
            }
        )

    failed_count = campaigns_qs.filter(status='failed').count()
    latest_failed = campaigns_qs.filter(status='failed').order_by('-updated_at').first()
    if failed_count:
        notifications.append(
            {
                'title': f"{failed_count} campaign{'' if failed_count == 1 else 's'} failed",
                'message': 'Review sender credentials and retry the affected campaign.',
                'tone': 'danger',
                'url': reverse('campaigns:campaign_list'),
                'created_at': latest_failed.updated_at if latest_failed else now,
            }
        )

    scheduled_count = campaigns_qs.filter(status='scheduled').count()
    latest_scheduled = campaigns_qs.filter(status='scheduled').order_by('-updated_at').first()
    if scheduled_count:
        notifications.append(
            {
                'title': f"{scheduled_count} campaign{'' if scheduled_count == 1 else 's'} scheduled",
                'message': 'Scheduled campaigns are queued and waiting for send time.',
                'tone': 'info',
                'url': reverse('campaigns:campaign_list'),
                'created_at': latest_scheduled.updated_at if latest_scheduled else now,
            }
        )

    draft_count = campaigns_qs.filter(status='draft').count()
    latest_draft = campaigns_qs.filter(status='draft').order_by('-updated_at').first()
    if draft_count:
        notifications.append(
            {
                'title': f"{draft_count} draft campaign{'' if draft_count == 1 else 's'} pending",
                'message': 'Complete subject/content checks and send when ready.',
                'tone': 'info',
                'url': reverse('campaigns:campaign_list'),
                'created_at': latest_draft.updated_at if latest_draft else now,
            }
        )

    sent_today = campaigns_qs.filter(status='sent', updated_at__date=now.date()).count()
    latest_sent_today = campaigns_qs.filter(status='sent', updated_at__date=now.date()).order_by('-updated_at').first()
    if sent_today:
        notifications.append(
            {
                'title': f"{sent_today} campaign{'' if sent_today == 1 else 's'} sent today",
                'message': 'Delivery run completed successfully today.',
                'tone': 'success',
                'url': reverse('campaigns:campaign_list'),
                'created_at': latest_sent_today.updated_at if latest_sent_today else now,
            }
        )

    high_risk_count = campaigns_qs.filter(spam_risk='high').count()
    latest_high_risk = campaigns_qs.filter(spam_risk='high').order_by('-updated_at').first()
    if high_risk_count:
        notifications.append(
            {
                'title': f"{high_risk_count} high-risk campaign{'' if high_risk_count == 1 else 's'} detected",
                'message': 'Run AI spam check before sending to improve inbox placement.',
                'tone': 'warning',
                'url': reverse('campaigns:campaign_list'),
                'created_at': latest_high_risk.updated_at if latest_high_risk else now,
            }
        )

    pending_invites = TeamInvitation.objects.filter(email=user.email, status='pending').count()
    if pending_invites:
        notifications.append(
            {
                'title': f"{pending_invites} pending invitation{'' if pending_invites == 1 else 's'}",
                'message': 'You have workspace invitations waiting for your response.',
                'tone': 'info',
                'url': reverse('workspaces:my_invitations'),
                'created_at': now,
            }
        )

    if dismissed_at:
        notifications = [item for item in notifications if item['created_at'] > dismissed_at]

    notifications.sort(key=lambda item: item['created_at'], reverse=True)
    return notifications


def dashboard_notifications(request):
    if not request.user.is_authenticated:
        return {}

    dismissed_raw = request.session.get('dashboard_notifications_dismissed_at')
    dismissed_at = None
    if dismissed_raw:
        try:
            dismissed_at = datetime.fromisoformat(dismissed_raw)
            if timezone.is_naive(dismissed_at):
                dismissed_at = timezone.make_aware(dismissed_at, timezone.get_current_timezone())
        except (TypeError, ValueError):
            dismissed_at = None

    notifications = _build_notifications(request.user, dismissed_at)
    return {
        'dashboard_notifications': notifications,
        'dashboard_notification_count': len(notifications),
    }
