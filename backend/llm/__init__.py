"""
backend/llm/__init__.py

LLM module — the ONLY place in the project that imports google.generativeai.
All LLM calls must go through generate(). No other module may import the Gemini SDK.
This keeps model-swapping to a single file change.
"""
from .wrapper import generate, LLMError

__all__ = ["generate", "LLMError"]
