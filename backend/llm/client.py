"""
Local Ollama LLM Client.
Communicates with locally running Ollama service for Qwen3:8b model inference.
"""

import os
import json
import logging
from typing import Any, Dict, Optional
import httpx

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen3:8b"


class OllamaClient:
    """Client for communicating with local Ollama instance."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 60.0
    ):
        self.base_url = (base_url or os.environ.get("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL).rstrip("/")
        self.model = model or os.environ.get("OLLAMA_MODEL") or DEFAULT_OLLAMA_MODEL
        self.timeout = timeout

    def is_available(self) -> bool:
        """Checks if the Ollama service is reachable."""
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0
    ) -> Dict[str, Any]:
        """
        Sends system and user prompt to Ollama and expects a structured JSON object response.
        """
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "format": "json",
            "stream": False,
            "keep_alive": "24h",
            "options": {
                "temperature": temperature
            }
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload)
                if response.status_code != 200:
                    raise RuntimeError(f"Ollama API returned HTTP {response.status_code}: {response.text}")

                data = response.json()
                raw_response = data.get("response", "{}")
                return self._parse_json_response(raw_response)
        except httpx.ConnectError as e:
            logger.error(f"Cannot connect to Ollama at {self.base_url}: {e}")
            raise ConnectionError(
                "The local query model is currently unavailable. Please make sure Ollama is running."
            ) from e
        except httpx.TimeoutException as e:
            logger.error(f"Ollama inference timed out after {self.timeout}s: {e}")
            raise TimeoutError(
                "Local model inference timed out. Please check system resources."
            ) from e
        except Exception as e:
            logger.error(f"Ollama request error: {e}")
            raise

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """Strips markdown and parses JSON safely."""
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
            # Try regex finding json block
            import re
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    pass
            raise ValueError(f"Model returned invalid JSON: {text}") from e
