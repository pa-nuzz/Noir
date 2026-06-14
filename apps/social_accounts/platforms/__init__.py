from .facebook import FacebookPlatform
from .twitter import TwitterPlatform
from .linkedin import LinkedInPlatform
from .tiktok import TikTokPlatform
from .youtube import YouTubePlatform

PLATFORM_REGISTRY = {
    'facebook': FacebookPlatform,
    'instagram': FacebookPlatform,
    'twitter': TwitterPlatform,
    'linkedin': LinkedInPlatform,
    'tiktok': TikTokPlatform,
    'youtube': YouTubePlatform,
}


def get_platform(platform_name, account=None):
    cls = PLATFORM_REGISTRY.get(platform_name)
    if not cls:
        raise ValueError(f"Unsupported platform: {platform_name}")
    return cls(account)
