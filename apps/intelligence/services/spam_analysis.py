"""Spam analysis service module.

Provides high-level spam analysis functionality wrapping the ML model predictions
with risk level classification.
"""

import logging

from apps.intelligence.ml_model import predict_spam_score

logger = logging.getLogger(__name__)


def get_risk_level(score: float) -> str:
    """Classify spam risk level based on spam score.
    
    Args:
        score (float): Spam probability score (0-100).
    
    Returns:
        str: Risk level classification ('Very Low', 'Low', 'Medium', or 'High').
    """
    if score >= 75:
        return 'High'
    if score >= 45:
        return 'Medium'
    if score >= 20:
        return 'Low'
    return 'Very Low'


def analyze_spam_text(text: str) -> dict:
    """Analyze email text and return spam score with risk classification.
    
    Truncates text to 10000 characters to prevent memory issues with extremely
    long email bodies.
    
    Args:
        text (str): Email content to analyze.
    
    Returns:
        dict: Dictionary with 'spam_score' (0-100) and 'risk_level' (str).
    """
    score = predict_spam_score((text or '')[:10000])
    return {
        'spam_score': score,
        'risk_level': get_risk_level(score),
    }
