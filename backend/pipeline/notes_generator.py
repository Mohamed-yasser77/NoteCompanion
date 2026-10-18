"""
backend/pipeline/notes_generator.py

Steps 3 and 4 of the pipeline:
  Step 3 — generate bullet-point notes for each transcript chunk (LLM call per chunk)
  Step 4 — generate a 2-3 line summary + topic title for the whole video

SPEC constraint: LLM must only use content from the chunk. No outside facts.
SPEC constraint: Respect MAX_CHUNKS_PER_VIDEO; append a warning banner if truncated.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from backend.llm import generate, LLMError
from backend.transcript.chunker import Chunk


# ── Prompts ──────────────────────────────────────────────────────────────────

_NOTES_SYSTEM = (
    "You are a precise note-taker. "
    "Extract key concepts, definitions, and examples ONLY from the text provided. "
    "Do NOT add any facts, context, or explanations that are not present in the text. "
    "Format your output as a short title on the first line, then bullet points."
)

_NOTES_PROMPT_TEMPLATE = """\
Extract structured notes from the following video transcript segment.

Transcript:
{text}

Output format:
Topic: <short topic title for this segment>
- <key point>
- <key point>
- ...

Use only information from the transcript above. Do not add outside facts."""

_SUMMARY_SYSTEM = (
    "You are a concise summariser. "
    "Write a 2-3 sentence summary and a short topic title based ONLY on the notes provided."
)

_SUMMARY_PROMPT_TEMPLATE = """\
Based on the following notes from a YouTube video, write:
1. A short topic title (5-8 words)
2. A 2-3 sentence summary

Notes:
{notes_text}

Output format:
Title: <topic title>
Summary: <2-3 sentences>"""


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ChunkNotes:
    chunk_index: int
    start_seconds: float
    topic: str
    bullets: List[str]


@dataclass
class VideoNotes:
    title: str          # LLM-generated topic title
    summary: str        # 2-3 line summary
    chunks: List[ChunkNotes]
    truncated: bool     # True if MAX_CHUNKS_PER_VIDEO was hit
    total_chunks: int   # total number of chunks before truncation


# ── Helpers ───────────────────────────────────────────────────────────────────

def _max_chunks() -> int:
    return int(os.getenv("MAX_CHUNKS_PER_VIDEO", "10"))


def _parse_chunk_notes(raw: str, chunk_index: int, start_seconds: float) -> ChunkNotes:
    """Parse LLM output for a single chunk into a ChunkNotes object."""
    lines = raw.strip().splitlines()
    topic = f"Segment {chunk_index + 1}"
    bullets: List[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("topic:"):
            topic = stripped[len("topic:"):].strip()
        elif stripped.startswith("-"):
            bullets.append(stripped.lstrip("- ").strip())
        elif stripped and not bullets:
            # Fallback: treat first non-empty, non-topic line as a bullet
            bullets.append(stripped)

    return ChunkNotes(
        chunk_index=chunk_index,
        start_seconds=start_seconds,
        topic=topic,
        bullets=bullets,
    )


def _parse_summary(raw: str) -> tuple[str, str]:
    """Parse LLM summary output into (title, summary) strings."""
    title = "Learning Notes"
    summary_lines: List[str] = []

    for line in raw.strip().splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("title:"):
            title = stripped[len("title:"):].strip()
        elif stripped.lower().startswith("summary:"):
            summary_lines.append(stripped[len("summary:"):].strip())
        elif summary_lines:
            summary_lines.append(stripped)

    summary = " ".join(summary_lines).strip() or raw.strip()
    return title, summary


# ── Public API ────────────────────────────────────────────────────────────────

def generate_notes(chunks: List[Chunk]) -> VideoNotes:
    """
    Run Steps 3 and 4: generate notes per chunk, then a summary for the whole video.

    Args:
        chunks: Output from chunk_transcript().

    Returns:
        VideoNotes with per-chunk bullet notes and an overall summary.

    If MAX_CHUNKS_PER_VIDEO is exceeded, processes only the first N chunks and
    sets VideoNotes.truncated = True (a warning banner is added by the renderer).
    """
    max_chunks = _max_chunks()
    total_chunks = len(chunks)
    truncated = total_chunks > max_chunks
    active_chunks = chunks[:max_chunks]

    chunk_notes_list: List[ChunkNotes] = []

    for chunk in active_chunks:
        prompt = _NOTES_PROMPT_TEMPLATE.format(text=chunk.text)
        try:
            raw = generate(prompt, system=_NOTES_SYSTEM)
        except LLMError as exc:
            # SPEC: skip the chunk gracefully, surface the message
            print(f"  ⚠️  Skipped chunk {chunk.index + 1}: {exc}")
            chunk_notes_list.append(
                ChunkNotes(
                    chunk_index=chunk.index,
                    start_seconds=chunk.start_seconds,
                    topic=f"Segment {chunk.index + 1} (skipped — LLM error)",
                    bullets=[f"Error: {exc}"],
                )
            )
            continue

        chunk_notes_list.append(
            _parse_chunk_notes(raw, chunk.index, chunk.start_seconds)
        )

    # Step 4 — summary of the whole video
    all_notes_text = "\n".join(
        f"[Segment {cn.chunk_index + 1}] {cn.topic}\n"
        + "\n".join(f"  - {b}" for b in cn.bullets)
        for cn in chunk_notes_list
    )
    summary_prompt = _SUMMARY_PROMPT_TEMPLATE.format(notes_text=all_notes_text)

    try:
        raw_summary = generate(summary_prompt, system=_SUMMARY_SYSTEM)
        title, summary = _parse_summary(raw_summary)
    except LLMError as exc:
        print(f"  ⚠️  Summary generation failed: {exc}")
        title = "Learning Notes"
        summary = "(Summary unavailable — LLM error)"

    return VideoNotes(
        title=title,
        summary=summary,
        chunks=chunk_notes_list,
        truncated=truncated,
        total_chunks=total_chunks,
    )
