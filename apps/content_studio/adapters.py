import logging
import re

import langdetect

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r'https?://\S+')
_MENTION_RE = re.compile(r'@\w+')
_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+')

# Confidence threshold for trusting langdetect result
LANG_CONFIDENCE_THRESHOLD = 0.8


class PlatformAdapter:
    PLATFORM_CONSTRAINTS = {
        'instagram': {
            'max_caption_length': 2200,
            'max_hashtags': 30,
            'allowed_formats': ['image', 'video', 'carousel', 'reel'],
        },
        'facebook': {
            'max_caption_length': 63206,
            'max_hashtags': 30,
            'allowed_formats': ['image', 'video', 'link', 'status'],
        },
        'twitter': {
            'max_caption_length': 280,
            'max_hashtags': 10,
            'allowed_formats': ['text', 'image', 'video'],
        },
        'linkedin': {
            'max_caption_length': 3000,
            'max_hashtags': 30,
            'allowed_formats': ['text', 'image', 'link', 'article'],
        },
        'tiktok': {
            'max_caption_length': 150,
            'max_hashtags': 10,
            'allowed_formats': ['video'],
        },
        'youtube': {
            'max_caption_length': 5000,
            'max_hashtags': 15,
            'allowed_formats': ['video'],
        },
    }

    def __init__(self, platform):
        self.platform = platform
        self.constraints = self.PLATFORM_CONSTRAINTS.get(platform, {})

    # ── token protection (prevent URLs/@mentions from being split) ──

    @staticmethod
    def _protect_tokens(text):
        urls = []
        mentions = []
        def _save_url(m):
            urls.append(m.group(0))
            return f'__URL_{len(urls) - 1}__'
        def _save_mention(m):
            mentions.append(m.group(0))
            return f'__MENTION_{len(mentions) - 1}__'
        text = _URL_RE.sub(_save_url, text)
        text = _MENTION_RE.sub(_save_mention, text)
        return text, urls, mentions

    @staticmethod
    def _restore_tokens(text, urls, mentions):
        for i, u in enumerate(urls):
            text = text.replace(f'__URL_{i}__', u)
        for i, m in enumerate(mentions):
            text = text.replace(f'__MENTION_{i}__', m)
        return text

    # ── language detection ──

    @staticmethod
    def detect_language(text):
        if not text or len(text.strip()) < 5:
            return 'en', 0.0
        try:
            result = langdetect.detect_langs(text)
            if not result:
                return 'en', 0.0
            top = result[0]
            return top.lang, top.prob
        except langdetect.lang_detect_exception.LangDetectException:
            return 'en', 0.0

    # ── LLM-based translation ──

    def translate_if_needed(self, text, source_lang, confidence):
        if source_lang == 'en' or confidence < LANG_CONFIDENCE_THRESHOLD:
            return text
        try:
            from .llm.llm_service import _call_llm_fatal, SYSTEM_PROMPTS
            system = SYSTEM_PROMPTS['translator']
            return _call_llm_fatal('translator', system, text)
        except Exception as e:
            logger.warning("Translation failed for %s (lang=%s, conf=%.2f): %s",
                           self.platform, source_lang, confidence, e)
            return text

    # ── smart truncation (tier 1: sentence-boundary, tier 2: LLM compress) ──

    def _tier1_truncate(self, text, max_len):
        if len(text) <= max_len:
            return text
        protected, urls, mentions = self._protect_tokens(text)
        sentences = _SENTENCE_RE.split(protected.strip())
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            return text[:max_len]
        accumulated = []
        for s in sentences:
            candidate = ' '.join(accumulated + [s]) if accumulated else s
            if len(candidate) <= max_len:
                accumulated.append(s)
            else:
                break
        if not accumulated:
            return None
        result = ' '.join(accumulated)
        result = self._restore_tokens(result, urls, mentions)
        return result

    def _tier2_compress(self, text, max_len):
        if len(text) <= max_len:
            return text
        try:
            from .llm.llm_service import _call_llm_fatal, SYSTEM_PROMPTS
            system = SYSTEM_PROMPTS['caption_compressor']
            prompt = f"Compress to {max_len} characters:\n\n{text}"
            return _call_llm_fatal('caption_compressor', system, prompt)
        except Exception as e:
            logger.warning("LLM compression failed for %s: %s", self.platform, e)
            return text[:max_len - 3] + '...'

    def smart_truncate(self, text, max_body_len):
        result = self._tier1_truncate(text, max_body_len)
        if result is not None:
            return result
        return self._tier2_compress(text, max_body_len)

    # ── hashtag budget computation ──

    @staticmethod
    def format_hashtags(tags):
        if not tags:
            return ''
        cleaned = []
        for h in tags:
            h = h.strip().lstrip('#')
            if h:
                cleaned.append(f'#{h}')
        return ' '.join(cleaned)

    def compute_hashtag_budget(self, tags):
        formatted = self.format_hashtags(tags)
        if not formatted:
            return 0, ''
        return 2 + len(formatted), formatted

    # ── full adaptation orchestration ──

    def adapt_content(self, text, hashtags=None):
        source_lang, confidence = self.detect_language(text)
        metadata = {
            'adapted': False,
            'source_lang': source_lang,
            'original_length': len(text),
        }
        adapted = self.translate_if_needed(text, source_lang, confidence)
        if adapted != text:
            metadata['translated'] = True
        budget, formatted_tags = self.compute_hashtag_budget(hashtags or [])
        max_len = self.constraints.get('max_caption_length', 280)
        max_body_len = max_len - budget
        if max_body_len < 1:
            logger.warning("Hashtags alone exceed platform limit for %s", self.platform)
            adapted = ''
        else:
            adapted = self.smart_truncate(adapted, max_body_len)
        metadata['adapted'] = True
        metadata['adapted_length'] = len(adapted)
        metadata['hashtag_budget'] = budget
        return adapted, metadata

    # ── keep existing methods ──

    def adapt_caption(self, text):
        max_len = self.constraints.get('max_caption_length', 280)
        if len(text) > max_len:
            return text[:max_len - 3] + '...'
        return text

    def adapt_hashtags(self, tags):
        max_tags = self.constraints.get('max_hashtags', 10)
        return tags[:max_tags]

    def validate_content(self, content_type, text, media_count=0):
        issues = []
        max_len = self.constraints.get('max_caption_length', float('inf'))
        if len(text) > max_len:
            issues.append(f"Text exceeds {max_len} characters ({len(text)}).")
        return issues
