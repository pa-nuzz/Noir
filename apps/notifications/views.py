import json
import logging
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from .models import Notification

logger = logging.getLogger(__name__)


@login_required
@require_GET
def notification_list(request):
    """Get user's notifications with pagination."""
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 20))
    
    notifications = Notification.objects.filter(user=request.user)
    total = notifications.count()
    
    start = (page - 1) * page_size
    end = start + page_size
    
    notifications_page = notifications[start:end]
    
    data = {
        'notifications': [
            {
                'id': n.id,
                'type': n.type,
                'title': n.title,
                'message': n.message,
                'action_url': n.action_url,
                'read': n.read,
                'created_at': n.created_at.isoformat(),
            }
            for n in notifications_page
        ],
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': (total + page_size - 1) // page_size,
        'unread_count': Notification.get_unread_count(request.user),
    }
    
    return JsonResponse(data)


@login_required
@require_POST
def mark_read(request):
    """Mark notification(s) as read."""
    try:
        data = json.loads(request.body)
        notification_ids = data.get('notification_ids', [])
        
        if not notification_ids:
            return JsonResponse({'success': False, 'error': 'No notification IDs provided'}, status=400)
        
        updated = Notification.objects.filter(
            id__in=notification_ids,
            user=request.user
        ).update(read=True)
        
        return JsonResponse({
            'success': True,
            'updated': updated
        })
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error marking notifications read: {e}")
        return JsonResponse({'success': False, 'error': 'Internal error'}, status=500)


@login_required
@require_POST
def mark_all_read(request):
    """Mark all notifications as read."""
    try:
        updated = Notification.objects.filter(
            user=request.user,
            read=False
        ).update(read=True)
        
        return JsonResponse({
            'success': True,
            'updated': updated
        })
    except Exception as e:
        logger.error(f"Error marking all notifications read: {e}")
        return JsonResponse({'success': False, 'error': 'Internal error'}, status=500)


@login_required
@require_GET
def unread_count(request):
    """Get unread notification count."""
    count = Notification.get_unread_count(request.user)
    return JsonResponse({'unread_count': count})