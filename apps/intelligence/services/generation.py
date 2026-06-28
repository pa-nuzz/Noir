import base64
import logging
import time
from urllib.parse import urljoin

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class GenerationEngine:
    TASK_IMAGE = "image_generation"
    TASK_IMAGE_EDIT = "image_editing"
    TASK_TEXT = "text_generation"
    TASK_VISION_EDIT = "vision_edit"

    VALID_DIMS = [768, 832, 896, 960, 1024, 1088, 1152, 1216, 1280, 1344]

    SUPPORTED_SIZES = {
        "1024x1024": (1024, 1024),
        "768x1344": (768, 1344),
        "1344x768": (1344, 768),
        "896x1152": (896, 1152),
        "1152x896": (1152, 896),
        "832x1216": (832, 1216),
        "1216x832": (1216, 832),
    }

    def __init__(self):
        self.api_key = getattr(settings, "NVIDIA_API_KEY", "")
        self.nim_base = "https://ai.api.nvidia.com/v1"
        self.integrate_base = getattr(settings, "NVIDIA_INTEGRATE_URL", "https://integrate.api.nvidia.com/v1")
        self.nvcf_base = "https://api.nvcf.nvidia.com/v2/nvcf/assets"
        self.models = getattr(settings, "NVIDIA_MODELS", {})
        self.timeout = 180.0
        self.max_retries = 3

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def is_available(self, model: str) -> bool:
        return self.models.get(model, {}).get("available", False)

    def get_modality(self, model: str) -> str:
        return self.models.get(model, {}).get("modality", "image")

    def _classify_task(self, modality: str) -> str:
        return {
            "image": self.TASK_IMAGE,
            "image_edit": self.TASK_IMAGE_EDIT,
            "vision_edit": self.TASK_VISION_EDIT,
            "text": self.TASK_TEXT,
        }.get(modality, self.TASK_IMAGE)

    def _parse_size(self, size: str):
        size = (size or "1024x1024").strip().lower()
        if size in self.SUPPORTED_SIZES:
            return self.SUPPORTED_SIZES[size]
        try:
            w, h = int(size.split("x")[0]), int(size.split("x")[1])
            w = min(self.VALID_DIMS, key=lambda d: abs(d - w))
            h = min(self.VALID_DIMS, key=lambda d: abs(d - h))
            return w, h
        except (ValueError, IndexError):
            return 1024, 1024

    def generate(self, prompt: str = "", model: str = "", modality: str = "",
                 task_type: str = "", image_b64: str = "", image_url: str = "",
                 **kwargs) -> dict:
        if not self.is_configured():
            return {"success": False, "error": "NVIDIA API key not configured"}

        if not model:
            return {"success": False, "error": "Model is required"}

        cfg = self.models.get(model, {})
        if not cfg:
            return {"success": False, "error": f"Unknown model: {model}"}

        if not self.is_available(model):
            return {
                "success": False,
                "error": f"{model} is not available",
                "available": False,
            }

        modality = modality or cfg.get("modality", "image")
        task_type = task_type or self._classify_task(modality)
        prompt = prompt.strip()

        api_type = cfg.get("api_type", "nim")

        if task_type == self.TASK_VISION_EDIT:
            return self._generate_vision_edit(prompt, model, cfg, image_b64, **kwargs)
        elif api_type == "openai_compat":
            return self._generate_text(prompt, model, cfg, task_type, **kwargs)
        else:
            return self._generate_image(prompt, model, cfg, task_type, image_b64, image_url, **kwargs)

    def _generate_image(self, prompt: str, model: str, cfg: dict, task_type: str,
                        image_b64: str, image_url: str, **kwargs) -> dict:
        payload = {"prompt": prompt}
        default_params = cfg.get("params", {})

        if image_b64:
            payload["image"] = f"data:image/png;base64,{image_b64}"
        elif image_url:
            payload["image"] = image_url

        w, h = self._parse_size(kwargs.get("size"))
        payload["width"] = w
        payload["height"] = h

        cfg_val = kwargs.get("cfg_scale", default_params.get("cfg_scale"))
        if cfg_val is not None:
            payload["cfg_scale"] = cfg_val

        steps = kwargs.get("steps") or default_params.get("steps")
        if steps is not None:
            payload["steps"] = steps

        if "seed" in kwargs and kwargs["seed"] is not None:
            payload["seed"] = kwargs["seed"]

        endpoint = cfg["endpoint"]
        url = urljoin(f"{self.nim_base}/", endpoint.lstrip("/"))
        return self._call_api(url, payload, task_type=task_type, model=model)

    def _generate_vision_edit(self, prompt: str, model: str, cfg: dict,
                               image_b64: str, **kwargs) -> dict:
        """Re-imagine an image based on edit instructions.
        Since the NVIDIA API doesn't support img2img in base mode, we use
        Flux Dev to generate a new image using the edit instruction as prompt guidance.
        The source image is stored for user reference but not sent to the model.
        """
        if not image_b64:
            return {"success": False, "error": "Image is required for editing"}

        self._upload_to_nvcf(image_b64)

        edit_prompt = (
            f"Re-imagine this image with the following changes: {prompt}. "
            "Maintain the same subject and composition, apply the requested changes. "
            "Photorealistic, high detail, 8k quality."
        )

        flux_cfg = self.models.get("ida-vision-dev", {})
        result = self._generate_image(
            prompt=edit_prompt,
            model="ida-vision-dev",
            cfg=flux_cfg,
            task_type=self.TASK_IMAGE,
            image_b64="",
            image_url="",
            **kwargs,
        )
        logger.info("vision_edit result: success=%s images=%s error=%s",
                    result.get("success"), len(result.get("images", [])), result.get("error", ""))
        return result

    def _upload_to_nvcf(self, image_b64: str) -> str | None:
        """Upload a base64 image to NVCF and return the assetId."""
        try:
            create_resp = httpx.post(
                self.nvcf_base,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "contentType": "image/png",
                    "description": "image-edit-source",
                },
                timeout=15.0,
            )
            create_resp.raise_for_status()
            data = create_resp.json()
            asset_id = data.get("assetId")
            upload_url = data.get("uploadUrl")

            if not asset_id or not upload_url:
                return None

            img_bytes = base64.b64decode(image_b64)
            upload_resp = httpx.put(
                upload_url,
                headers={
                    "Content-Type": "image/png",
                    "x-amz-meta-nvcf-asset-description": "image-edit-source",
                },
                content=img_bytes,
                timeout=30.0,
            )
            upload_resp.raise_for_status()

            return asset_id

        except Exception as exc:
            logger.error("NVCF upload failed: %s", exc)
            return None

    def _generate_text(self, prompt: str, model: str, cfg: dict, task_type: str, **kwargs) -> dict:
        payload = {
            "model": cfg["model_name"],
            "messages": [{"role": "user", "content": prompt}],
        }
        default_params = cfg.get("params", {})
        payload["max_tokens"] = kwargs.get("max_tokens", default_params.get("max_tokens", 1024))
        temperature = kwargs.get("temperature", default_params.get("temperature"))
        if temperature is not None:
            payload["temperature"] = temperature

        url = urljoin(f"{self.integrate_base}/", cfg["endpoint"].lstrip("/"))
        return self._call_api(url, payload, task_type=task_type, model=model, api_type="openai_compat")

    def _call_api(self, url: str, payload: dict, task_type: str = "", model: str = "",
                  api_type: str = "nim") -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        for attempt in range(self.max_retries):
            try:
                resp = httpx.post(url, json=payload, headers=headers, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
                result = self._parse_response(data, api_type=api_type)
                result["model"] = model
                result["task_type"] = task_type
                return result

            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                body = exc.response.text[:500]
                if status in (429, 500, 502, 503) and attempt < self.max_retries - 1:
                    wait = 2 ** attempt + 1
                    logger.warning("NVIDIA API %s, retry %ss", status, wait)
                    time.sleep(wait)
                    continue
                logger.error("NVIDIA API error %s: %s", status, body)
                return {"success": False, "error": f"API error {status}: {body[:200]}"}

            except httpx.RequestError as exc:
                if attempt < self.max_retries - 1:
                    wait = 2 ** attempt + 1
                    logger.warning("NVIDIA request error, retry %ss: %s", wait, exc)
                    time.sleep(wait)
                    continue
                logger.error("NVIDIA request failed after %s attempts", attempt + 1)
                return {"success": False, "error": "Request failed"}

            except Exception as exc:
                logger.exception("Unexpected error: %s", exc)
                return {"success": False, "error": "Unexpected error"}

        return {"success": False, "error": "Max retries exceeded"}

    def _parse_response(self, data: dict, api_type: str = "nim") -> dict:
        if api_type == "openai_compat":
            try:
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    return {"success": True, "text": content, "images": []}
                reasoning = data.get("choices", [{}])[0].get("message", {}).get("reasoning", "")
                if reasoning:
                    return {"success": True, "text": reasoning, "images": [], "reasoning": reasoning}
                return {"success": False, "error": "No content in response", "raw": str(data)[:200]}
            except (IndexError, AttributeError):
                return {"success": False, "error": "Failed to parse response", "raw": str(data)[:200]}

        images = []
        for artifact in data.get("artifacts", []):
            if artifact.get("base64"):
                images.append({"type": "base64", "data": artifact["base64"]})

        for item in data.get("data", []):
            if item.get("b64_json"):
                images.append({"type": "base64", "data": item["b64_json"]})
            elif item.get("url"):
                images.append({"type": "url", "data": item["url"]})

        if images:
            return {"success": True, "images": images, "text": ""}

        return {"success": False, "error": "No content in response", "raw": str(data)[:200]}


_engine = None


def get_generation_engine() -> GenerationEngine:
    global _engine
    if _engine is None:
        _engine = GenerationEngine()
    return _engine