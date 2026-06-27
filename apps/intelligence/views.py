"""Intelligence app views for spam analysis and auto-reply settings.

Provides API endpoints for analyzing email content and calculating spam risk scores.
"""

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
import json
import logging

from django.conf import settings
from .services import analyze_spam_text
from apps.workspaces.decorators import require_workspace_permission
from .models import AutoReplySettings, Rule, Action, ActivityLog
from apps.inbox.models import EmailMessage, EmailDraft, EmailInbox
from apps.workspaces.query_helpers import filter_by_context

logger = logging.getLogger(__name__)


@login_required
@csrf_protect
@require_POST
@require_workspace_permission('workspace', 'read')
def analyze_spam(request):
    """Analyze email text for spam indicators via AJAX.
    
    Accepts POST request with email content and returns spam score (0-100)
    and risk level (Very Low, Low, Medium, High).
    
    Args:
        request: HTTP request with JSON body containing 'text' or 'content' field.
    
    Returns:
        JsonResponse: JSON with success status, spam_score, and risk_level.
    """
    try:
        data = json.loads(request.body)
        text = data.get('text') or data.get('content') or ''
        result = analyze_spam_text(text)
        
        return JsonResponse({
            'success': True,
            **result,
        })
    except Exception as e:
        logger.error(f"Spam analysis error: {str(e)}")
        return JsonResponse({'success': False, 'error': 'An error occurred during analysis.'}, status=400)


@login_required
@csrf_protect
@require_POST
def generate_copilot_content(request):
    """Generate email copy using Gemini AI Co-Pilot and analyze for spam triggers via AJAX.
    
    Accepts POST request with a prompt and desired tone, calls the copilot service,
    and analyzes the result.
    
    Args:
        request: HTTP request with JSON body containing 'prompt' and 'tone'.
    
    Returns:
        JsonResponse: JSON containing generated subject, body, spam_score, and risk_level.
    """
    try:
        data = json.loads(request.body)
        prompt = (data.get('prompt') or '').strip()
        tone = (data.get('tone') or 'professional').strip()
        
        if not prompt:
            return JsonResponse({'success': False, 'error': 'Prompt is required.'}, status=400)
            
        from .services.copilot import generate_ai_copy
        content = generate_ai_copy(prompt, tone)

        # If the generation reported an error state, surface it to the UI as failure
        if content.get('mode') == 'error' or content.get('subject', '').lower().startswith('error'):
            return JsonResponse({'success': False, 'error': content.get('body', 'AI generation failed.')} , status=502)

        # Analyze generated copy to give user instantaneous deliverability feedback
        combined_text = f"{content.get('subject', '')} {content.get('body', '')}"
        spam_result = analyze_spam_text(combined_text)

        return JsonResponse({
            'success': True,
            'subject': content.get('subject', ''),
            'body': content.get('body', ''),
            'spam_score': spam_result.get('spam_score', 0.0),
            'risk_level': spam_result.get('risk_level', 'Very Low'),
            'mode': content.get('mode', getattr(settings, 'LLM_MODEL', 'gpt-4o'))
        })
    except Exception as e:
        logger.error(f"Content generation error: {str(e)}")
        return JsonResponse({'success': False, 'error': 'An error occurred during content generation.'}, status=500)


@login_required
@require_workspace_permission('workspace', 'read')
def auto_reply_settings(request):
    """User auto-reply settings page."""
    ws_id = request.session.get('active_workspace_id')
    settings_obj = None
    if ws_id:
        settings_obj = AutoReplySettings.objects.filter(
            user=request.user, workspace_id=ws_id
        ).first()
    if not settings_obj:
        settings_obj, created = AutoReplySettings.objects.get_or_create(
            user=request.user,
            workspace_id=ws_id,
            defaults={
                'enable_auto_reply': False,
                'confidence_threshold': 80,
                'spam_risk_threshold': 'Medium',
                'default_tone': 'professional',
            }
        )

    if request.method == 'POST':
        settings_obj.enable_auto_reply = request.POST.get('enable_auto_reply') == 'on'
        try:
            settings_obj.confidence_threshold = int(request.POST.get('confidence_threshold', 80))
        except ValueError:
            settings_obj.confidence_threshold = 80
        settings_obj.spam_risk_threshold = request.POST.get('spam_risk_threshold', 'Medium')
        settings_obj.default_tone = request.POST.get('default_tone', 'professional')
        settings_obj.save()
        messages.success(request, 'Auto-reply settings saved successfully.')
        return redirect('intelligence:auto_reply_settings')

    context = {
        'settings': settings_obj,
    }
    return render(request, 'intelligence/auto_reply_settings.html', context)


@login_required
@require_POST
def api_auto_reply_rules(request):
    """API endpoint to list/create auto-reply rules."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            ws_id = request.session.get('active_workspace_id')
            rule = Rule.objects.create(
                user=request.user,
                workspace_id=ws_id,
                name=data.get('name'),
                intent=data.get('intent'),
                min_confidence=int(data.get('min_confidence', 80)),
                is_active=data.get('is_active', True),
                priority=int(data.get('priority', 0)),
            )
            actions_data = data.get('actions', [])
            for action_data in actions_data:
                Action.objects.create(
                    rule=rule,
                    action_type=action_data.get('action_type'),
                    label=action_data.get('label', ''),
                    tone_override=action_data.get('tone_override', ''),
                )
            return JsonResponse({
                'success': True,
                'rule_id': rule.id,
                'message': 'Rule created successfully',
            })
        except Exception as e:
            logger.error(f"Failed to create rule: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
    return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)


@login_required
@require_POST
def api_auto_reply_rule_detail(request, rule_id):
    """API endpoint to update/delete a specific rule."""
    ws_id = request.session.get('active_workspace_id')
    rule = get_object_or_404(Rule, id=rule_id, user=request.user, workspace_id=ws_id)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            action = data.get('action')
            
            if action == 'delete':
                rule.delete()
                return JsonResponse({'success': True, 'message': 'Rule deleted'})
            
            elif action == 'update':
                rule.name = data.get('name', rule.name)
                rule.intent = data.get('intent', rule.intent)
                rule.min_confidence = int(data.get('min_confidence', rule.min_confidence))
                rule.is_active = data.get('is_active', rule.is_active)
                rule.priority = int(data.get('priority', rule.priority))
                rule.save()
                
                if 'actions' in data:
                    rule.actions.all().delete()
                    for action_data in data['actions']:
                        Action.objects.create(
                            rule=rule,
                            action_type=action_data.get('action_type'),
                            label=action_data.get('label', ''),
                            tone_override=action_data.get('tone_override', ''),
                        )
                
                return JsonResponse({'success': True, 'rule_id': rule.id})
            
            return JsonResponse({'success': False, 'error': 'Invalid action'}, status=400)
        except Exception as e:
            logger.error(f"Failed to update rule: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
    return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)


@login_required
@require_POST
def api_trigger_auto_reply(request, message_id):
    """Manually trigger auto-reply analysis for a specific message."""
    msg = get_object_or_404(
        EmailMessage,
        id=message_id,
        thread__inbox__in=filter_by_context(request, EmailInbox.objects.all())
    )
    
    try:
        from .services.auto_reply import process_auto_reply
        result = process_auto_reply(msg.id)
        return JsonResponse({
            'success': True,
            'result': result,
        })
    except Exception as e:
        logger.error(f"Manual auto-reply trigger failed: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
