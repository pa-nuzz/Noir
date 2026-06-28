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
        self.timeout = 240.0
        self.max_retries = 3

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def is_available(self, model: str) -> bool:
        return self.models.get(model, {}).get("available", False)

    def get_modality(self, model: str) -> str:
        return self.models.get(model, {}).get("modality", "image")

    def _select_auto_model(self, modality: str, task_type: str) -> tuple[str, dict]:
        """Auto-select the best available model for the given modality.
        Priority: premium > fast (for image), fast > premium (for text).
        Returns (model_key, model_cfg).
        """
        candidates = []
        for key, cfg in self.models.items():
            if not cfg.get("available", False):
                continue
            cfg_modality = cfg.get("modality", "image")
            if modality == "image" and cfg_modality == "image":
                candidates.append((key, cfg, cfg.get("tier") == "premium", 1))
            elif modality == "text" and cfg_modality == "text":
                candidates.append((key, cfg, cfg.get("tier") == "fast", 1))
        if not candidates:
            for key, cfg in self.models.items():
                if cfg.get("available") and cfg.get("modality") == modality:
                    candidates.append((key, cfg, cfg.get("tier") == "premium", 2))
        if not candidates:
            raise ValueError(f"No available model for modality: {modality}")
        candidates.sort(key=lambda x: (x[2], x[3]), reverse=True)
        return candidates[0][0], candidates[0][1]

    REPHRASE_PROMPTS = [
        "Photorealistic, ultra detailed, 8k: {}",
        "Masterpiece, best quality, hyperrealistic: {}",
        "Professional photography, cinematic: {}",
        "{} detailed, high resolution",
    ]

    def _rephrase_prompt(self, prompt: str, attempt: int) -> str:
        """Enhance prompt to get better generation results."""
        rephrase = self.REPHRASE_PROMPTS[attempt % len(self.REPHRASE_PROMPTS)]
        return rephrase.format(prompt)

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

        prompt = prompt.strip()
        if not prompt:
            return {"success": False, "error": "Prompt is required"}

        actual_model = model
        cfg = None

        if not model or model == "auto":
            try:
                actual_modality = modality or "image"
                actual_model, cfg = self._select_auto_model(actual_modality, task_type)
                logger.info("Auto-selected model: %s for modality: %s", actual_model, actual_modality)
            except ValueError as e:
                return {"success": False, "error": str(e)}
        else:
            cfg = self.models.get(actual_model, {})
            if not cfg:
                return {"success": False, "error": f"Unknown model: {actual_model}"}
            if not self.is_available(actual_model):
                return {"success": False, "error": f"{actual_model} is not available", "available": False}

        actual_modality = modality or cfg.get("modality", "image")
        actual_task_type = task_type or self._classify_task(actual_modality)

        api_type = cfg.get("api_type", "nim")

        attempts_info = []
        last_error = None

        for retry_round in range(self.max_retries):
            current_prompt = self._rephrase_prompt(prompt, retry_round) if retry_round > 0 else prompt

            if actual_task_type == self.TASK_VISION_EDIT:
                result = self._generate_vision_edit(current_prompt, actual_model, cfg, image_b64, **kwargs)
            elif api_type == "openai_compat":
                result = self._generate_text(current_prompt, actual_model, cfg, actual_task_type, **kwargs)
            else:
                result = self._generate_image(current_prompt, actual_model, cfg, actual_task_type, image_b64, image_url, **kwargs)

            attempts_info.append({
                "attempt": retry_round + 1,
                "prompt": current_prompt,
                "model": actual_model,
                "success": result.get("success", False),
                "error": result.get("error", ""),
            })

            if result.get("success") and result.get("images") and len(result.get("images", [])) > 0:
                result["model_used"] = actual_model
                result["model_label"] = cfg.get("label", actual_model)
                result["attempts"] = attempts_info
                result["rephrased"] = retry_round > 0
                return result

            last_error = result.get("error", "Generation failed")

            if result.get("error") and "rate" in result.get("error", "").lower():
                wait = 5 + retry_round * 5
                logger.warning("Rate limit hit, waiting %ss before retry", wait)
                time.sleep(wait)
            elif result.get("error") and any(x in result.get("error", "") for x in ["429", "500", "502", "503"]):
                wait = 3 + retry_round * 3
                logger.warning("Transient error, waiting %ss before retry", wait)
                time.sleep(wait)
            else:
                if retry_round < self.max_retries - 1:
                    logger.info("Retrying with rephrased prompt (attempt %s)", retry_round + 2)
                    time.sleep(2)

        return {
            "success": False,
            "error": f"Failed after {self.max_retries} attempts: {last_error}",
            "model_used": actual_model,
            "model_label": cfg.get("label", actual_model) if cfg else actual_model,
            "attempts": attempts_info,
        }

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
            b64 = artifact.get("base64")
            if b64:
                decoded = base64.b64decode(b64)
                if len(decoded) < 10000:
                    continue
                images.append({"type": "base64", "data": b64})

        for item in data.get("data", []):
            b64_json = item.get("b64_json")
            if b64_json:
                decoded = base64.b64decode(b64_json)
                if len(decoded) < 10000:
                    continue
                images.append({"type": "base64", "data": b64_json})
            elif item.get("url"):
                images.append({"type": "url", "data": item["url"]})

        if images:
            return {"success": True, "images": images, "text": ""}

        return {"success": False, "error": "No valid image in response", "raw": str(data)[:200]}


_engine = None


def get_generation_engine() -> GenerationEngine:
    global _engine
    if _engine is None:
        _engine = GenerationEngine()
    return _engine