import logging
from datetime import datetime, timedelta

from django.core.cache import cache

logger = logging.getLogger(__name__)

EMAIL_SENT_COUNTER = 'metrics:email:sent'
EMAIL_FAILED_COUNTER = 'metrics:email:failed'
EMAIL_BOUNCE_COUNTER = 'metrics:email:bounce'


def record_email_sent(sender_id=None, campaign_id=None):
    """Increment send counters for monitoring."""
    try:
        cache.incr(EMAIL_SENT_COUNTER)
        if sender_id:
            cache.incr(f'{EMAIL_SENT_COUNTER}:sender:{sender_id}')
        if campaign_id:
            cache.incr(f'{EMAIL_SENT_COUNTER}:campaign:{campaign_id}')
    except Exception:
        logger.debug("Cache unavailable for metrics incr")


def record_email_failed(sender_id=None, error_type='unknown'):
    """Increment failure counters."""
    try:
        cache.incr(EMAIL_FAILED_COUNTER)
        if sender_id:
            cache.incr(f'{EMAIL_FAILED_COUNTER}:sender:{sender_id}:{error_type}')
    except Exception:
        logger.debug("Cache unavailable for metrics incr")


def record_email_bounce(sender_id=None, bounce_type='hard'):
    """Increment bounce counters."""
    try:
        cache.incr(EMAIL_BOUNCE_COUNTER)
        if sender_id:
            cache.incr(f'{EMAIL_BOUNCE_COUNTER}:sender:{sender_id}:{bounce_type}')
    except Exception:
        logger.debug("Cache unavailable for metrics incr")


def get_delivery_stats(hours=24):
    """Get aggregate delivery stats for the last N hours."""
    try:
        sent = cache.get(EMAIL_SENT_COUNTER, 0) or 0
        failed = cache.get(EMAIL_FAILED_COUNTER, 0) or 0
        bounced = cache.get(EMAIL_BOUNCE_COUNTER, 0) or 0
        total = sent + failed
        success_rate = round((sent / total * 100), 1) if total > 0 else 0
        return {
            'sent': sent,
            'failed': failed,
            'bounced': bounced,
            'total': total,
            'success_rate': success_rate,
        }
    except Exception:
        return {'sent': 0, 'failed': 0, 'bounced': 0, 'total': 0, 'success_rate': 0}
