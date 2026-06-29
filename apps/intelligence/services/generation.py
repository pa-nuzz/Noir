import base64
import logging
import time
from urllib.parse import quote, urljoin

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class GenerationEngine:

    def __init__(self):
        self.nvidia_key = getattr(settings, "NVIDIA_API_KEY", "")
        self.pollinations_key = getattr(settings, "POLLINATIONS_API_KEY", "")
        self.openrouter_key = getattr(settings, "OPENROUTER_API_KEY", "")
        self.deepai_key = getattr(settings, "DEEPAI_API_KEY", "")
        self.gemini_key = getattr(settings, "GEMINI_API_KEY", "")
        self.models = getattr(settings, "IDA_MODELS", {}) or getattr(settings, "NVIDIA_MODELS", {})
        self.timeout = 30.0

    def is_configured(self) -> bool:
        return bool(self.nvidia_key or self.pollinations_key or self.openrouter_key or self.deepai_key or self.gemini_key)

    def _rank_candidates(self, modality: str) -> list[tuple[str, dict]]:
        fallback_map = {
            "image": ["nvidia", "pollinations", "deepai"],
            "text": ["nvidia", "gemini", "openrouter"],
        }
        allowed = fallback_map.get(modality, [])
        candidates = []
        for key, cfg in self.models.items():
            if not cfg.get("available"):
                continue
            if cfg.get("modality") != modality:
                continue
            prov = cfg.get("provider", "")
            if prov not in allowed:
                continue
            if not self._has_key(prov):
                continue
            score = {"nvidia": 0, "pollinations": 2, "gemini": 1, "openrouter": 2}.get(prov, 99)
            # Within nvidia, prefer fast models (fewer steps)
            if prov == "nvidia":
                steps = cfg.get("params", {}).get("steps", 30)
                if steps <= 4:
                    score += 0  # fast
                else:
                    score += 1  # slower
            candidates.append((score, key, cfg))
        candidates.sort()
        return [(k, c) for _, k, c in candidates]

    def _has_key(self, provider: str) -> bool:
        return bool(getattr(self, f"{provider}_key", ""))

    def generate(self, prompt: str = "", model: str = "auto", modality: str = "image",
                 size: str = "", **kwargs) -> dict:
        if not self.is_configured():
            return {"success": False, "error": "Generation service not configured"}
        prompt = prompt.strip()
        if not prompt:
            return {"success": False, "error": "Prompt is required"}

        is_auto = model in ("", "auto")

        if is_auto:
            candidates = self._rank_candidates(modality)
            if not candidates:
                return {"success": False, "error": "No available model"}
            for model_key, cfg in candidates:
                result = self._call(cfg, prompt, modality, size, **kwargs)
                result["model"] = cfg.get("label", model_key)
                if result.get("success"):
                    return result
            return {"success": False, "error": "All models failed"}
        else:
            cfg = self.models.get(model)
            if not cfg:
                return {"success": False, "error": "Unknown model"}
            if not cfg.get("available"):
                return {"success": False, "error": "Model unavailable"}
            if not self._has_key(cfg.get("provider", "")):
                return {"success": False, "error": "Provider not configured"}
            result = self._call(cfg, prompt, modality, size, **kwargs)
            result["model"] = cfg.get("label", model)
            if result.get("success"):
                return result
            return result

    def _call(self, cfg: dict, prompt: str, modality: str, size: str, **kwargs) -> dict:
        provider = cfg.get("provider", "")
        if provider == "nvidia" and modality == "text":
            return self._nvidia_text(prompt, cfg)
        elif provider == "nvidia" and modality == "image":
            return self._nvidia_image(prompt, cfg, size)
        elif provider == "pollinations":
            return self._pollinations(prompt, cfg, size)
        elif provider == "openrouter":
            return self._openrouter(prompt, cfg)
        elif provider == "gemini":
            return self._gemini(prompt, cfg)
        return {"success": False, "error": "Unknown provider"}

    def _post(self, url: str, payload: dict, headers: dict) -> dict:
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            return {"success": True, "data": resp.json()}
        except httpx.TimeoutException:
            return {"success": False, "error": "Timed out"}
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                return {"success": False, "error": "Rate limited"}
            return {"success": False, "error": "Service error"}
        except Exception as exc:
            logger.warning("Request failed: %s", exc)
            return {"success": False, "error": "Request failed"}

    # ── NVIDIA Text ──────────────────────────────────────────────────────────

    def _nvidia_text(self, prompt: str, cfg: dict) -> dict:
        payload = {
            "model": cfg.get("model_name", "meta/llama-3.1-8b-instruct"),
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": cfg.get("params", {}).get("max_tokens", 2048),
        }
        temperature = cfg.get("params", {}).get("temperature")
        if temperature is not None:
            payload["temperature"] = temperature
        endpoint = cfg.get("endpoint", "/chat/completions")
        url = urljoin("https://integrate.api.nvidia.com/v1/", endpoint.lstrip("/"))
        headers = {"Authorization": f"Bearer {self.nvidia_key}", "Content-Type": "application/json"}
        result = self._post(url, payload, headers)
        if result.get("success"):
            return self._parse_openai(result["data"])
        return result

    # ── NVIDIA Image ──────────────────────────────────────────────────────────

    def _nvidia_image(self, prompt: str, cfg: dict, size: str) -> dict:
        w, h = self._parse_size(size or "1024x1024")
        payload = {"prompt": prompt, "width": w, "height": h}
        params = cfg.get("params", {})
        if params.get("steps"):
            payload["steps"] = params["steps"]
        if params.get("cfg_scale") is not None:
            payload["cfg_scale"] = params["cfg_scale"]
        endpoint = cfg.get("endpoint", "")
        url = urljoin("https://ai.api.nvidia.com/v1/", endpoint.lstrip("/"))
        headers = {"Authorization": f"Bearer {self.nvidia_key}", "Content-Type": "application/json", "Accept": "application/json"}
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            for artifact in data.get("artifacts", []):
                b64 = artifact.get("base64")
                if b64:
                    decoded = base64.b64decode(b64)
                    if len(decoded) >= 10000:
                        return {"success": True, "images": [{"type": "base64", "data": b64}]}
            return {"success": False, "error": "No valid image"}
        except httpx.TimeoutException:
            return {"success": False, "error": "Timed out"}
        except Exception as exc:
            logger.warning("NVIDIA image error: %s", exc)
            return {"success": False, "error": "Image service error"}

    # ── Pollinations ─────────────────────────────────────────────────────────

    def _pollinations(self, prompt: str, cfg: dict, size: str) -> dict:
        w, h = self._parse_size(size or "1024x1024")
        url = f"https://image.pollinations.ai/prompt/{quote(prompt, safe='')}"
        url += f"?width={w}&height={h}&model=flux&nologo=true&enhance=true"
        try:
            resp = httpx.get(url, timeout=self.timeout)
            if resp.status_code != 200 or "image" not in resp.headers.get("content-type", ""):
                return {"success": False, "error": "Image service error"}
            img = resp.content
            if len(img) < 10000:
                return {"success": False, "error": "Rate limited"}
            b64 = base64.b64encode(img).decode("utf-8")
            return {"success": True, "images": [{"type": "base64", "data": b64}]}
        except httpx.TimeoutException:
            return {"success": False, "error": "Timed out"}
        except Exception as exc:
            logger.warning("Pollinations error: %s", exc)
            return {"success": False, "error": "Image service error"}

    # ── OpenRouter ───────────────────────────────────────────────────────────

    def _openrouter(self, prompt: str, cfg: dict) -> dict:
        payload = {
            "model": cfg.get("model_name", "google/gemini-2.5-flash"),
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": cfg.get("params", {}).get("max_tokens", 4096),
        }
        temperature = cfg.get("params", {}).get("temperature")
        if temperature is not None:
            payload["temperature"] = temperature
        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://ida.app",
        }
        result = self._post("https://openrouter.ai/api/v1/chat/completions", payload, headers)
        if result.get("success"):
            return self._parse_openai(result["data"])
        return result

    # ── Gemini ───────────────────────────────────────────────────────────────

    def _gemini(self, prompt: str, cfg: dict) -> dict:
        model_name = cfg.get("model_name", "gemini-2.5-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.gemini_key}"
        gen_config = {
            "maxOutputTokens": cfg.get("params", {}).get("max_tokens", 8192),
            "temperature": cfg.get("params", {}).get("temperature", 0.7),
        }
        payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gen_config}
        try:
            resp = httpx.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return {"success": False, "error": "Empty response"}
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "\n".join(p.get("text", "") for p in parts if "text" in p)
            if text:
                return {"success": True, "text": text}
            return {"success": False, "error": "Empty response"}
        except httpx.TimeoutException:
            return {"success": False, "error": "Timed out"}
        except httpx.HTTPStatusError as exc:
            return {"success": False, "error": "Rate limited" if exc.response.status_code == 429 else "Service error"}
        except Exception as exc:
            logger.warning("Gemini error: %s", exc)
            return {"success": False, "error": "Service error"}

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _parse_openai(self, data: dict) -> dict:
        try:
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if content:
                return {"success": True, "text": content}
        except (IndexError, AttributeError):
            pass
        return {"success": False, "error": "Empty response"}

    def _parse_size(self, size: str) -> tuple[int, int]:
        SIZES = {
            "1024x1024": (1024, 1024), "768x1344": (768, 1344), "1344x768": (1344, 768),
            "896x1152": (896, 1152), "1152x896": (1152, 896), "832x1216": (832, 1216),
            "1216x832": (1216, 832),
        }
        size = (size or "1024x1024").strip().lower()
        if size in SIZES:
            return SIZES[size]
        try:
            w, h = int(size.split("x")[0]), int(size.split("x")[1])
            return w, h
        except (ValueError, IndexError):
            return 1024, 1024


_engine = None


def get_generation_engine() -> GenerationEngine:
    global _engine
    if _engine is None:
        _engine = GenerationEngine()
    return _engine
