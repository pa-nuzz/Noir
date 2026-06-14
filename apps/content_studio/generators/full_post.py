from ..llm.llm_service import generate_llm, refine_llm

from .base import BaseContentGenerator


class FullPostGenerator(BaseContentGenerator):
    def generate(self, prompt, **kwargs):
        result = generate_llm('full_post', prompt, platform=self.platform, tone=self.tone, **kwargs)
        if not result['success']:
            return f"[{result['error'].upper()}] {result['message']}"
        return result['content']

    def refine(self, content, feedback, **kwargs):
        tone = kwargs.get('tone', self.tone)
        result = refine_llm('full_post', content, feedback, platform=self.platform, tone=tone, **kwargs)
        if not result['success']:
            return f"[{result['error'].upper()}] {result['message']}"
        return result['content']
