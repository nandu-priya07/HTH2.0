"""
Local Ollama LLM Client.
Delegates to LLMModelManager singleton for permanent VRAM model reuse and fast inference.
"""

import logging
from typing import Any, Dict, Optional
from .manager import get_llm_model_manager

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "qwen3:8b"


class OllamaClient:
    """Client wrapper for communicating with Ollama via LLMModelManager singleton."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 60.0
    ):
        self.manager = get_llm_model_manager()
        if base_url and base_url.rstrip("/") != self.manager.base_url:
            self.manager.base_url = base_url.rstrip("/")
        if model and model != self.manager.model_name:
            self.manager.model_name = model

    def is_available(self) -> bool:
        """Checks if the local LLM service is available."""
        return self.manager.is_available()

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        think: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Sends system and user prompt to LLMModelManager for fast JSON inference.
        """
        return self.manager.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            think=think
        )
