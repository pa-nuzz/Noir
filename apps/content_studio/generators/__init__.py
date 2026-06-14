from .caption import CaptionGenerator
from .carousel import CarouselGenerator
from .cta import CTAGenerator
from .full_post import FullPostGenerator
from .hashtag import HashtagGenerator
from .prompt import ImagePromptGenerator
from .script import ScriptGenerator

GENERATOR_REGISTRY = {
    'caption': CaptionGenerator,
    'carousel': CarouselGenerator,
    'cta': CTAGenerator,
    'full_post': FullPostGenerator,
    'hashtag_set': HashtagGenerator,
    'image_prompt': ImagePromptGenerator,
    'script': ScriptGenerator,
}


def get_generator(content_type, platform=None, tone=None, brand_voice=None):
    cls = GENERATOR_REGISTRY.get(content_type)
    if not cls:
        return None
    return cls(platform=platform, tone=tone, brand_voice=brand_voice)
