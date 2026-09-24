"""
LLM package for local Ollama inference.
"""

from .client import OllamaClient
from .prompts import (
    SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    build_dataset_context,
    build_user_prompt,
    build_summary_prompt
)

__all__ = [
    "OllamaClient",
    "SYSTEM_PROMPT",
    "SUMMARY_SYSTEM_PROMPT",
    "build_dataset_context",
    "build_user_prompt",
    "build_summary_prompt"
]
