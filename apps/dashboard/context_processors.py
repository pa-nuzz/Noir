from datetime import datetime

from django.urls import reverse
from django.utils import timezone

from apps.campaigns.models import Campaign
from apps.dashboard.models import Notification
from apps.senders.models import Sender
from apps.workspaces.models import TeamInvitation


def _build_notifications(user, dismissed_at):
    notifications = []
    now = timezone.now()

    senders_qs = Sender.objects.filter(user=user)
    campaigns_qs = Campaign.objects.filter(user=user)

    active_senders_count = senders_qs.filter(is_active=True).count()
    total_senders = senders_qs.count()
    latest_sender = senders_qs.order_by('-created_at').first()
    sentinel = latest_sender.created_at if latest_sender else user.date_joined

    if active_senders_count > 0:
        notifications.append(
            {
                'id': 'sender-active',
                'title': f"{active_senders_count} active sender{'' if active_senders_count == 1 else 's'} ready",
                'message': 'Your SMTP configuration is available for outgoing campaigns.',
                'tone': 'success',
                'url': reverse('dashboard:settings'),
                'created_at': sentinel,
            }
        )
    elif total_senders > 0 and latest_sender:
        notifications.append(
            {
                'id': f'sender-inactive-{latest_sender.id}',
                'title': f'Sender "{latest_sender.display_name}" is inactive',
                'message': f'Go to Settings and set {latest_sender.from_email} as active.',
                'tone': 'warning',
                'url': reverse('dashboard:settings'),
                'created_at': sentinel,
            }
        )
    else:
        notifications.append(
            {
                'id': 'sender-missing',
                'title': 'No SMTP sender configured',
                'message': 'Add and verify an SMTP sender before launching campaigns.',
                'tone': 'warning',
                'url': reverse('dashboard:settings'),
                'created_at': sentinel,
            }
        )

    failed_count = campaigns_qs.filter(status='failed').count()
    latest_failed = campaigns_qs.filter(status='failed').order_by('-updated_at').first()
    if failed_count:
        notifications.append(
            {
                'id': 'campaigns-failed',
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
                'id': 'campaigns-scheduled',
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
                'id': 'campaigns-draft',
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
                'id': 'campaigns-sent-today',
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
                'id': 'campaigns-high-risk',
                'title': f"{high_risk_count} high-risk campaign{'' if high_risk_count == 1 else 's'} detected",
                'message': 'Run AI spam check before sending to improve inbox placement.',
                'tone': 'warning',
                'url': reverse('campaigns:campaign_list'),
                'created_at': latest_high_risk.updated_at if latest_high_risk else now,
            }
        )

    pending_invites_qs = TeamInvitation.objects.filter(email=user.email, status='pending')
    pending_invites = pending_invites_qs.count()
    if pending_invites:
        latest_invite = pending_invites_qs.order_by('-created_at').first()
        notifications.append(
            {
                'id': 'workspace-pending-invites',
                'title': f"{pending_invites} pending invitation{'' if pending_invites == 1 else 's'}",
                'message': 'You have workspace invitations waiting for your response.',
                'tone': 'info',
                'url': reverse('workspaces:my_invitations'),
                'created_at': latest_invite.created_at if latest_invite else now,
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
    persistent_notifications = Notification.objects.filter(
        user=request.user,
        is_read=False,
    ).order_by('-created_at')[:10]
    notifications.extend([
        {
            'id': f'db-{item.id}',
            'title': item.title,
            'message': item.message,
            'tone': item.tone,
            'url': item.url or '#',
            'created_at': item.created_at,
        }
        for item in persistent_notifications
    ])
    notifications.sort(key=lambda item: item['created_at'], reverse=True)
    return {
        'dashboard_notifications': notifications,
        'dashboard_notification_count': len(notifications),
    }
