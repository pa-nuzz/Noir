"""Intelligence app views for spam analysis.

Provides API endpoints for analyzing email content and calculating spam risk scores.
"""

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth.decorators import login_required
import json
import logging

from django.conf import settings
from .services import analyze_spam_text
from apps.workspaces.decorators import require_workspace_permission

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
@require_workspace_permission('workspace', 'read')
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

