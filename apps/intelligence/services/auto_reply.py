import logging
import re
from typing import Tuple
from .llm_client import get_llm_client

logger = logging.getLogger(__name__)

NO_REPLY_PATTERNS = [
    r'no-?reply', r'noreply', r'do-?not-?reply', r'donotreply',
    r'mailer-?daemon', r'postmaster', r'notification', r'alerts?@',
    r'newsletter', r'marketing', r'bulk@', r'mailman', r' automated',
    r'robot', r'bot@',
]

SKIP_DOMAINS = [
    'facebookmail.com', 'twitter.com', 'linkedin.com', 'instagram.com',
    'github.com', 'gitlab.com', 'slack.com', 'zoom.us', 'calendly.com',
    'notion.com', 'atlassian.com', 'eventbrite.com', 'meetup.com',
    'mailchimp.com', 'sendgrid.com', 'hubspot.com', 'salesforce.com',
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

    if subject_lower.startswith('unread') or subject_lower.startswith('you have'):
        return False

    return True


def classify_importance(subject: str, body_text: str) -> Tuple[str, str]:
    """Classify email importance and intent using AI.
    
    Returns:
        Tuple of (importance, intent)
    """
    llm = get_llm_client()
    
    system_prompt = (
        "You are an email triage assistant. Analyze emails and classify them.\n"
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
    tone: str = "professional"
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
    """Process single message for auto-reply.
    
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

    importance, intent = classify_importance(
        msg.subject or '',
        msg.body_text or '',
    )

    if importance not in ('medium', 'high', 'urgent'):
        logger.info(f"Auto-reply skipped: importance={importance} for message {message_id}")
        return False

    thread_summary = msg.thread.ai_summary or ''
    
    tone = "urgent" if importance == "urgent" else "professional"

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
        original_message=msg,
        ai_generated_body=draft_body,
        status='pending_review',
    )

    logger.info(
        f"Auto-reply draft created for message {message_id} "
        f"({msg.from_email}, importance={importance}, intent={intent}, tone={tone})"
    )
    return True
