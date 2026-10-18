"""
backend/llm/wrapper.py

Single LLM call surface for the entire project.

IMPORTANT: This is the only file that imports google.generativeai.
           No other module in backend/ may import it directly.
           Swap the model by editing only this file.
"""

from __future__ import annotations

import os

import google.genai as genai
from google.genai import types as genai_types


class LLMError(Exception):
    """Raised when the LLM call fails after exhausting retries."""


def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise LLMError(
            "GEMINI_API_KEY is not set. "
            "Copy .env.example to .env and add your Gemini API key."
        )
    return genai.Client(api_key=api_key)


def generate(prompt: str, system: str | None = None) -> str:
    """
    Call the configured LLM and return the text response.

    Args:
        prompt: The user-facing prompt text.
        system: Optional system instruction prepended to the conversation.

    Returns:
        The model's text response as a plain string.

    Raises:
        LLMError: On any API failure (auth, quota, network, empty response).
    """
    try:
        client = _get_client()

        contents = prompt
        config = None
        if system:
            config = genai_types.GenerateContentConfig(system_instruction=system)

        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )

        if not response.text:
            raise LLMError("LLM returned an empty response.")

        return response.text.strip()

    except LLMError:
        raise
    except Exception as exc:
        raise LLMError(f"LLM call failed: {exc}") from exc
