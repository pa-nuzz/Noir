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
