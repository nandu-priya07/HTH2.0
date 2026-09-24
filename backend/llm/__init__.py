"""
LLM package for local Ollama inference.
"""

from .client import OllamaClient
from .prompts import SYSTEM_PROMPT, build_dataset_context, build_user_prompt

__all__ = [
    "OllamaClient",
    "SYSTEM_PROMPT",
    "build_dataset_context",
    "build_user_prompt"
]
