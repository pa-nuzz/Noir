from celery import shared_task
from django.db import close_old_connections
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def async_generate_content(self, prompt, model="", task_type="",
                           image_b64="", image_url="", user_id=None, workspace_id=None,
                           **kwargs):
    close_old_connections()

    from apps.intelligence.services.generation import get_generation_engine

    engine = get_generation_engine()
    result = engine.generate(
        prompt=prompt,
        model=model,
        task_type=task_type,
        image_b64=image_b64,
        image_url=image_url,
        **kwargs,
    )

    result["prompt"] = prompt
    result["user_id"] = user_id
    result["workspace_id"] = workspace_id

    logger.info(
        "Generation complete: model=%s type=%s success=%s user=%s ws=%s",
        result.get("model"), result.get("task_type"), result.get("success"),
        user_id, workspace_id,
    )

    return result
