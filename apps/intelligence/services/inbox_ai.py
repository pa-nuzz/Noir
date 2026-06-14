import logging
from typing import Optional
from .llm_client import get_llm_client

logger = logging.getLogger(__name__)


def summarize_thread(body: str, subject: str, thread_context: Optional[str] = None) -> str:
    """Generate concise summary of email thread.
    
    Args:
        body: Email body content
        subject: Email subject
        thread_context: Optional additional context from thread history
        
    Returns:
        Concise summary (2-3 sentences)
    """
    body_snippet = (body or '')[:8000]
    context_section = f"\n\nThread Context:\n{thread_context}" if thread_context else ""
    
    system_prompt = (
        "You are an expert email assistant. Summarize email threads professionally and concisely.\n"
        "Rules:\n"
        "- Identify key participants and their roles\n"
        "- Extract main topics and action items\n"
        "- Keep it under 3 sentences\n"
        "- Be specific and actionable\n"
        "- Use professional tone"
    )
    
    user_prompt = (
        f"Subject: {subject}\n"
        f"Email Content:\n{body_snippet}{context_section}\n\n"
        "Provide a concise, professional summary:"
    )
    
    llm = get_llm_client()
    result = llm.generate(system_prompt, user_prompt, temperature=0.2, max_tokens=512)
    
    if result:
        return result
    
    # Fallback summary
    return (
        f"Email thread: '{subject}'\n"
        f"Key topics and action items identified for review."
    )


def generate_draft_reply(
    subject: str,
    summary: str,
    latest_body: str,
    tone: str = "professional",
    thread_history: Optional[str] = None,
    user_signature: Optional[str] = None
) -> str:
    """Generate intelligent draft reply with tone customization.
    
    Args:
        subject: Email subject
        summary: Thread summary
        latest_body: Latest message body
        tone: Reply tone ('professional', 'friendly', 'urgent', 'casual')
        thread_history: Optional full thread history
        user_signature: Optional user signature to append
        
    Returns:
        Professional draft reply
    """
    body_snippet = (latest_body or '')[:3000]
    history_section = f"\n\nFull Thread History:\n{thread_history}" if thread_history else ""
    signature_instruction = (
        f"\n\nSign off with: {user_signature}" if user_signature
        else "\n\nSign off professionally (no placeholder names)"
    )
    
    tone_guidance = {
        "professional": (
            "Maintain formal, polished language. Use complete sentences. "
            "Be courteous and business-appropriate."
        ),
        "friendly": (
            "Use warm, conversational tone. Show empathy and enthusiasm. "
            "Still professional but more approachable."
        ),
        "urgent": (
            "Be direct and action-oriented. Emphasize time-sensitivity. "
            "Use strong, clear language."
        ),
        "casual": (
            "Use relaxed, conversational language. Friendly and approachable. "
            "Still respectful but less formal."
        )
    }
    
    system_prompt = (
        "You are an expert email assistant. Draft professional, intelligent replies.\n"
        f"{tone_guidance.get(tone, tone_guidance['professional'])}\n"
        "Rules:\n"
        "- Address all key points from the incoming email\n"
        "- Be concise (under 150 words unless complex)\n"
        "- Show empathy and understanding\n"
        "- Offer clear next steps or solutions\n"
        "- Do NOT use placeholders like [Your Name]\n"
        f"{signature_instruction}"
    )
    
    user_prompt = (
        f"Subject: {subject}\n"
        f"Thread Summary: {summary}\n"
        f"Latest Message:\n{body_snippet}{history_section}\n\n"
        "Draft a thoughtful, professional reply:"
    )
    
    llm = get_llm_client()
    result = llm.generate(
        system_prompt, 
        user_prompt, 
        temperature=0.4 if tone == "casual" else 0.3,
        max_tokens=800
    )
    
    if result:
        if user_signature and user_signature.strip():
            result = f"{result}\n\n{user_signature}"
        return result
    
    # Smart fallback based on tone
    fallback_templates = {
        "professional": (
            f"Thank you for your email regarding '{subject}'.\n\n"
            f"I've reviewed the information and appreciate the detailed context. "
            f"Let me address the key points raised.\n\n"
            f"Please let me know if you need any additional information.\n\n"
            f"Best regards"
        ),
        "friendly": (
            f"Hi there,\n\n"
            f"Thanks so much for reaching out about '{subject}'! "
            f"I really appreciate you sharing this with me.\n\n"
            f"Let me dive into the details and get back to you promptly.\n\n"
            f"Best wishes"
        ),
        "urgent": (
            f"Re: {subject}\n\n"
            f"Thank you for bringing this to my attention. "
            f"I'm addressing this immediately and will provide updates shortly.\n\n"
            f"Best regards"
        ),
        "casual": (
            f"Hey,\n\n"
            f"Thanks for the email! Got your message about '{subject}' and I'm on it.\n\n"
            f"Will circle back soon with more details.\n\n"
            f"Cheers"
        )
    }
    
    return fallback_templates.get(tone, fallback_templates["professional"])


def generate_multiple_variations(
    subject: str,
    summary: str,
    latest_body: str,
    base_tone: str = "professional"
) -> dict:
    """Generate 3 reply variations with different tones.
    
    Args:
        subject: Email subject
        summary: Thread summary
        latest_body: Latest message body
        base_tone: Base tone to vary from
        
    Returns:
        Dict with 'conservative', 'balanced', 'enthusiastic' variations
    """
    variations = {}
    tone_map = {
        "conservative": "professional",
        "balanced": "friendly", 
        "enthusiastic": "casual"
    }
    
    for label, tone in tone_map.items():
        variations[label] = generate_draft_reply(
            subject, summary, latest_body, tone=tone
        )
    
    return variations
