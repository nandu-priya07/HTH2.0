"""
LLM package for local Ollama inference.
"""

from .client import OllamaClient
from .manager import LLMModelManager, get_llm_model_manager
from .prompts import (
    SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    build_dataset_context,
    build_user_prompt,
    build_summary_prompt
)

__all__ = [
    "OllamaClient",
    "LLMModelManager",
    "get_llm_model_manager",
    "SYSTEM_PROMPT",
    "SUMMARY_SYSTEM_PROMPT",
    "build_dataset_context",
    "build_user_prompt",
    "build_summary_prompt"
]
