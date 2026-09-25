"""
LLM Model Manager — Singleton Lifecycle & GPU VRAM Management
Manages local LLM (Qwen3:8b via Ollama) loading, warm-up, thread-safe access,
and permanent in-memory / VRAM reuse.
"""

import os
import json
import time
import logging
import threading
from typing import Any, Dict, Optional
import httpx

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "qwen3:8b"


class LLMModelManager:
    """
    Centralized, thread-safe Singleton LLM Model Manager.
    Ensures model is loaded ONCE at application startup and kept alive in GPU VRAM.
    """

    _instance: Optional["LLMModelManager"] = None
    _lock = threading.Lock()

    def __init__(self, base_url: Optional[str] = None, model_name: Optional[str] = None):
        if LLMModelManager._instance is not None:
            raise RuntimeError("LLMModelManager is a singleton. Use get_instance() instead.")

        self.base_url = (base_url or os.environ.get("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL).rstrip("/")
        self.model_name = model_name or os.environ.get("OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL
        self.is_loaded = False
        self.device = "unknown"
        self.vram_usage_mb = 0.0
        self.init_time_ms = 0.0
        self.gpu_name = "NVIDIA GeForce RTX 3050 (6GB)"
        self.initialization_lock = threading.Lock()

        # Reusable HTTP client for connection pooling & ultra-low request latency
        self._http_client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(60.0, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
        )

    @classmethod
    def get_instance(cls) -> "LLMModelManager":
        """Returns the global thread-safe singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def is_available(self) -> bool:
        """Checks if Ollama service is reachable."""
        try:
            resp = self._http_client.get("/api/tags")
            return resp.status_code == 200
        except Exception:
            return False

    def initialize(self, force_warmup: bool = True) -> Dict[str, Any]:
        """
        Thread-safe startup initialization.
        Loads model into VRAM once and keeps it alive.
        """
        if self.is_loaded and not force_warmup:
            logger.info(f"[LLM] MODEL REUSE | model_loaded=true | device={self.device}")
            return self._get_status_dict()

        with self.initialization_lock:
            if self.is_loaded and not force_warmup:
                logger.info(f"[LLM] MODEL REUSE | model_loaded=true | device={self.device}")
                return self._get_status_dict()

            t0 = time.perf_counter()
            logger.info(f"[LLM] MODEL LOAD START | model={self.model_name} | base_url={self.base_url}")

            if not self.is_available():
                logger.warning(f"[LLM] Ollama service not reachable at {self.base_url}. Model pre-loading deferred.")
                self.is_loaded = False
                self.device = "unavailable"
                return self._get_status_dict()

            # Warm-up inference call to trigger model load into VRAM & set 24h keep_alive
            try:
                warmup_payload = {
                    "model": self.model_name,
                    "prompt": "ping",
                    "system": "Respond with OK",
                    "format": "json",
                    "stream": False,
                    "keep_alive": "24h",
                    "think": False,
                    "options": {"temperature": 0.0}
                }
                resp = self._http_client.post("/api/generate", json=warmup_payload)
                if resp.status_code != 200:
                    logger.warning(f"[LLM] Warmup response status: {resp.status_code}")
            except Exception as e:
                logger.warning(f"[LLM] Warmup generation failed: {e}")

            # Query Ollama memory status (/api/ps) for exact VRAM and device info
            self.device = "cpu"
            self.vram_usage_mb = 0.0
            try:
                ps_resp = self._http_client.get("/api/ps")
                if ps_resp.status_code == 200:
                    models_running = ps_resp.json().get("models", [])
                    for m in models_running:
                        if m.get("name") == self.model_name or m.get("model") == self.model_name:
                            vram_bytes = m.get("size_vram", 0)
                            self.vram_usage_mb = round(vram_bytes / (1024 * 1024), 2)
                            if vram_bytes > 0:
                                self.device = "cuda"
                            break
            except Exception as e:
                logger.debug(f"[LLM] Failed to fetch /api/ps info: {e}")

            t_init = (time.perf_counter() - t0) * 1000
            self.init_time_ms = round(t_init, 2)
            self.is_loaded = True

            logger.info(
                f"[LLM] MODEL LOAD COMPLETE | "
                f"device={self.device} | "
                f"model_loaded=true | "
                f"gpu={self.gpu_name} ({self.vram_usage_mb:.1f} MB VRAM) | "
                f"initialization_time={self.init_time_ms:.1f}ms"
            )

            return self._get_status_dict()

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        think: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Executes LLM inference reusing the already-loaded model instance.
        Logs model reuse and detailed per-query timing.
        """
        if not self.is_loaded:
            self.initialize(force_warmup=False)

        logger.info(f"[LLM] MODEL REUSE | model_loaded=true | device={self.device}")

        t_start = time.perf_counter()

        payload = {
            "model": self.model_name,
            "system": system_prompt,
            "prompt": user_prompt,
            "format": "json",
            "stream": False,
            "keep_alive": "24h",
            "options": {
                "temperature": temperature
            }
        }
        if think is not None:
            payload["think"] = think

        t_prep_ms = round((time.perf_counter() - t_start) * 1000, 2)

        t_gen0 = time.perf_counter()
        try:
            response = self._http_client.post("/api/generate", json=payload)
            if response.status_code != 200:
                raise RuntimeError(f"Ollama API returned HTTP {response.status_code}: {response.text}")

            data = response.json()
            raw_response = data.get("response", "{}")
        except httpx.ConnectError as e:
            logger.error(f"Cannot connect to Ollama at {self.base_url}: {e}")
            raise ConnectionError("The local query model is currently unavailable. Please make sure Ollama is running.") from e
        except httpx.TimeoutException as e:
            logger.error(f"Ollama inference timed out after 60s: {e}")
            raise TimeoutError("Local model inference timed out. Please check system resources.") from e
        except Exception as e:
            logger.error(f"Ollama request error: {e}")
            raise

        t_gen_ms = round((time.perf_counter() - t_gen0) * 1000, 2)

        t_parse0 = time.perf_counter()
        parsed_json = self._parse_json_response(raw_response)
        t_parse_ms = round((time.perf_counter() - t_parse0) * 1000, 2)

        t_total_ms = round((time.perf_counter() - t_start) * 1000, 2)

        logger.info(
            f"[LLM] tokenization: {t_prep_ms:.1f}ms | "
            f"generation: {t_gen_ms:.1f}ms | "
            f"json_parse: {t_parse_ms:.1f}ms | "
            f"total: {t_total_ms:.1f}ms"
        )

        return parsed_json

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """Strips markdown formatting and parses JSON safely."""
        clean = text.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        elif clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()

        try:
            return json.loads(clean)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Ollama output as JSON: '{text}'. Error: {e}")
            import re
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    pass
            raise ValueError(f"Model returned invalid JSON: {text}") from e

    def _get_status_dict(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "device": self.device,
            "gpu": self.gpu_name,
            "model_loaded": self.is_loaded,
            "vram_usage_mb": self.vram_usage_mb,
            "initialization_time_ms": self.init_time_ms
        }


def get_llm_model_manager() -> LLMModelManager:
    """Helper function to obtain the singleton LLMModelManager."""
    return LLMModelManager.get_instance()
