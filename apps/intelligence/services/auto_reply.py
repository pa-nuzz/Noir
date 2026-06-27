import logging
import re
from typing import Tuple, Optional
from .llm_client import get_llm_client
from .spam_analysis import analyze_spam_text
from ..models import AutoReplySettings

logger = logging.getLogger(__name__)

NO_REPLY_PATTERNS = [
    r'no-?reply', r'\.noreply', r'^noreply', r'do-?not-?reply', r'donotreply',
    r'mailer-?daemon', r'postmaster', r'^notification', r'^alerts?@',
    r'newsletter', r'marketing', r'bulk@', r'mailman', r' automated',
    r'robot', r'bot@', r'^nobody@', r'^non-?reply',
    r'^auto-', r'^auto@', r'reply-?to-?nobody', r'^info@', r'^support@.*auto',
    r'^admin@', r'^webmaster@', r'^hostmaster@', r'^abuse@',
    r'alert@', r'^donotreply', r'^no\.reply', r'^do\.not\.reply',
    r'undeliver', r'mail-?delivery', r'bounce', r'spam@',
    r'^noreplyl', r'^notification@', r'^updates@', r'^notify@',
]

SKIP_DOMAINS = [
    'facebookmail.com', 'twitter.com', 'linkedin.com', 'instagram.com',
    'github.com', 'gitlab.com', 'slack.com', 'zoom.us', 'calendly.com',
    'notion.com', 'atlassian.com', 'eventbrite.com', 'meetup.com',
    'mailchimp.com', 'sendgrid.com', 'hubspot.com', 'salesforce.com',
    'amazonses.com', 'awsapps.com', 'stripe.com', 'paypal.com', 'shopify.com',
    'medium.com', 'quora.com', 'reddit.com', 'discord.com',
    'trello.com', 'asana.com', 'dropbox.com', 'box.com',
    'dropboxmail.com', 'postmarkapp.com', 'mailgun.org',
    'jira.com', 'zendesk.com', 'intercom.com', 'google.com',
]

SKIP_SUBJECT_PATTERNS = [
    r'^unread', r'^you have', r'^new message from', r'^someone (liked|commented|followed)',
    r'^your (order|receipt|invoice|subscription|payment)', r'^weekly digest',
    r'^monthly report', r'^daily summary', r'^verification code',
    r'^confirm your', r'^verify your', r'^security alert', r'^password reset',
    r'^account (verification|activation|created|updated|suspended)',
    r'^welcome to', r'^thank you for (subscribing|signing up|joining|registering|your purchase)',
    r'^your (trial|subscription|membership)', r'^automatic reply',
    r'^out of (office|town)', r'^vacation', r'^auto.?reply', r'^auto.?response',
]


def is_human_email(from_email: str, from_name: str, subject: str) -> bool:
    """Detect if email is from a human (not automated)."""
    if not from_email:
        return False
    email_lower = from_email.lower()
    name_lower = (from_name or '').lower()
    subject_lower = (subject or '').lower()

    for pattern in NO_REPLY_PATTERNS:
        if re.search(pattern, email_lower) or re.search(pattern, name_lower):
            return False

    for domain in SKIP_DOMAINS:
        if email_lower.endswith('@' + domain) or email_lower.endswith('.' + domain):
            return False

    for pattern in SKIP_SUBJECT_PATTERNS:
        if re.search(pattern, subject_lower):
            return False

    return True


def classify_importance(subject: str, body_text: str) -> Tuple[str, str]:
    """Classify email importance and intent using AI.
    
    Returns:
        Tuple of (importance, intent)
    """
    llm = get_llm_client()
    
    system_prompt = (
        "You are an email triage assistant for a business professional. Analyze emails and decide if they need a response.\n"
        "\n"
        "RULES FOR CLASSIFICATION:\n"
        "- If the email is a newsletter, marketing promo, notification, receipt, autoresponder, or automated update → importance=low\n"
        "- If the email asks a direct question, requests a meeting, reports a problem, or needs a decision → importance=medium or higher\n"
        "- If the email is from a customer, partner, or colleague with a time-sensitive request → importance=high or urgent\n"
        "- If the email is an out-of-office reply, delivery failure, or system notification → importance=low\n"
        "- When in doubt, classify as low (it's better to miss a reply than to auto-reply to spam)\n"
        "\n"
        "Respond with EXACTLY two lines:\n"
        "Line 1: importance (one of: low, medium, high, urgent)\n"
        "Line 2: intent (one of: question, complaint, support, sales, feedback, introduction, meeting_request, other)"
    )

    body_snippet = (body_text or '')[:2000]
    user_prompt = (
        f"Subject: {subject}\n\nBody:\n{body_snippet}\n\nClassify this email:"
    )

    result = llm.generate(system_prompt, user_prompt, temperature=0.1, max_tokens=100)
    
    if not result:
        return 'medium', 'other'

    lines = [l.strip() for l in result.split('\n') if l.strip()]
    importance = 'medium'
    intent = 'other'

    valid_importance = {'low', 'medium', 'high', 'urgent'}
    valid_intent = {'question', 'complaint', 'support', 'sales', 'feedback', 'introduction', 'meeting_request', 'other'}

    if lines:
        imp = lines[0].lower().strip()
        if imp in valid_importance:
            importance = imp
    if len(lines) > 1:
        intt = lines[1].lower().strip()
        if intt in valid_intent:
            intent = intt

    return importance, intent


def generate_auto_reply(
    subject: str,
    body_text: str,
    thread_summary: str,
    importance: str,
    intent: str,
    from_name: str,
    tone: str = "professional",
    thread_history: str = ""
) -> str:
    """Generate intelligent auto-reply based on context.
    
    Args:
        subject: Email subject
        body_text: Email body
        thread_summary: Thread context
        importance: Email importance level
        intent: Detected intent
        from_name: Sender name
        tone: Reply tone
        
    Returns:
        Professional reply draft
    """
    from .inbox_ai import generate_draft_reply
    
    context = (
        f"Importance: {importance}\n"
        f"Intent: {intent}\n"
        f"From: {from_name}\n"
        f"Thread Summary: {thread_summary or 'No summary available'}"
    )
    
    return generate_draft_reply(
        subject=subject,
        summary=context,
        latest_body=body_text,
        tone=tone
    )


def process_auto_reply(message_id: int) -> bool:
    """Process single message for auto-reply with spam filtering and confidence threshold.

    Args:
        message_id: EmailMessage ID

    Returns:
        True if draft created, False otherwise
    """
    from apps.inbox.models import EmailMessage, EmailDraft

    try:
        msg = EmailMessage.objects.select_related('thread__inbox').get(id=message_id)
    except EmailMessage.DoesNotExist:
        logger.warning(f"Auto-reply: message {message_id} not found")
        return False

    if not msg.is_incoming:
        return False

    if not is_human_email(msg.from_email, msg.from_name, msg.subject):
        logger.info(f"Auto-reply skipped: non-human sender {msg.from_email}")
        return False

    existing_draft = EmailDraft.objects.filter(
        thread=msg.thread,
        user=msg.thread.inbox.user,
        status__in=['pending_review', 'edited', 'approved'],
    ).exists()
    if existing_draft:
        logger.info(f"Auto-reply skipped: existing draft for thread {msg.thread.id}")
        return False

    # Classify importance and intent
    importance, intent = classify_importance(
        msg.subject or '',
        msg.body_text or '',
    )
    
    # Populate intent and urgency on the message
    msg.intent = intent
    msg.urgency = importance
    msg.save(update_fields=['intent', 'urgency'])

    # Intents that warrant an AI draft reply
    REPLY_WORTHY_INTENTS = {'question', 'support', 'complaint', 'meeting_request'}

    # Skip if intent doesn't warrant a reply (other, newsletter-ish, automated content)
    if intent not in REPLY_WORTHY_INTENTS:
        logger.info(f"Auto-reply skipped: intent={intent} not reply-worthy for message {message_id}")
        return False

    # Intents that warrant an AI draft reply
    REPLY_WORTHY_INTENTS = {'question', 'support', 'complaint', 'meeting_request'}

    # Skip if intent doesn't warrant a reply (other, sales, feedback, introduction, automated)
    if intent not in REPLY_WORTHY_INTENTS:
        logger.info(f"Auto-reply skipped: intent={intent} not reply-worthy for message {message_id}")
        return False

    # Skip low importance emails
    if importance == 'low':
        logger.info(f"Auto-reply skipped: importance=low for message {message_id}")
        return False

    # Get user's auto-reply settings
    user = msg.thread.inbox.user
    settings_obj, _ = AutoReplySettings.objects.get_or_create(
        user=user,
        defaults={
            'enable_auto_reply': True,
            'confidence_threshold': 80,
            'spam_risk_threshold': 'Medium',
            'default_tone': 'professional',
        }
    )
    
    if not settings_obj.enable_auto_reply:
        logger.info(f"Auto-reply skipped: disabled by user settings for {user.email}")
        return False

    # Perform spam analysis to compute confidence
    combined_text = f"{msg.subject or ''}\n{msg.body_text or ''}"
    spam_result = analyze_spam_text(combined_text)
    spam_score = spam_result.get('spam_score', 0)
    risk_level = spam_result.get('risk_level', 'Low')
    
    # Map risk levels to numeric values for comparison
    risk_order = {
        'Very Low': 0,
        'Low': 1,
        'Medium': 2,
        'High': 3,
    }
    user_risk_level = settings_obj.spam_risk_threshold
    user_risk_value = risk_order.get(user_risk_level, 2)  # default Medium
    current_risk_value = risk_order.get(risk_level, 2)
    
    # Calculate confidence (inverse of spam score)
    confidence = 100 - spam_score
    
    # Check confidence threshold and spam risk
    if confidence < settings_obj.confidence_threshold:
        logger.info(
            f"Auto-reply skipped: confidence {confidence} below threshold {settings_obj.confidence_threshold} "
            f"for message {message_id}"
        )
        return False
        
    if current_risk_value > user_risk_value:
        logger.info(
            f"Auto-reply skipped: risk level {risk_level} exceeds threshold {user_risk_level} "
            f"for message {message_id}"
        )
        return False

    thread_summary = msg.thread.ai_summary or ''
    
    tone = "urgent" if importance == "urgent" else settings_obj.default_tone

    draft_body = generate_auto_reply(
        subject=msg.subject or '',
        body_text=msg.body_text or '',
        thread_summary=thread_summary,
        importance=importance,
        intent=intent,
        from_name=msg.from_name or '',
        tone=tone
    )

    if not draft_body:
        logger.warning(f"Auto-reply: empty draft for message {message_id}")
        return False

    EmailDraft.objects.create(
        thread=msg.thread,
        user=msg.thread.inbox.user,
        workspace=msg.thread.inbox.workspace,
        original_message=msg,
        ai_generated_body=draft_body,
        edited_body=draft_body,
        status='pending_review',
        final_body='',
        ai_generated=True,
    )

    logger.info(
        f"Auto-reply draft created for message {message_id} "
        f"({msg.from_email}, importance={importance}, intent={intent}, tone={tone}, "
        f"confidence={confidence}, spam_score={spam_score}, risk={risk_level})"
    )
    return True
