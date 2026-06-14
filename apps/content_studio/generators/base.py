import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseContentGenerator(ABC):
    def __init__(self, platform=None, tone=None, brand_voice=None):
        self.platform = platform
        self.tone = tone or 'professional'
        self.brand_voice = brand_voice or ''

    @abstractmethod
    def generate(self, prompt, **kwargs):
        raise NotImplementedError

    @abstractmethod
    def refine(self, content, feedback, **kwargs):
        raise NotImplementedError
