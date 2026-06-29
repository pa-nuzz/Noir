from celery import shared_task
from django.db import close_old_connections
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def async_generate_content(self, prompt, model="auto", modality="image",
                           image_b64="", image_url="", size="1024x1024"):
    close_old_connections()

    from apps.intelligence.services.generation import get_generation_engine

    engine = get_generation_engine()
    result = engine.generate(
        prompt=prompt,
        model=model,
        modality=modality,
        image_b64=image_b64,
        image_url=image_url,
        size=size,
    )

    return result
