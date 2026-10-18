"""
backend/transcript/chunker.py

Splits a transcript entry list into time-based chunks of ~CHUNK_TARGET_MINUTES each.

Rules (from SPEC §3 Step 2):
  - Each chunk keeps its start_seconds and end_seconds.
  - If the video is shorter than one chunk window, it becomes a single chunk.
  - Never split mid-sentence; break at the nearest caption entry boundary.
    (Caption boundaries are already sentence-aligned by YouTube's ASR.)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

from .fetcher import TranscriptEntry

# Default chunk window in seconds; overridden by CHUNK_TARGET_MINUTES env var
_DEFAULT_CHUNK_SECONDS = 4 * 60  # 4 minutes


def _chunk_target_seconds() -> int:
    minutes = float(os.getenv("CHUNK_TARGET_MINUTES", "4"))
    return int(minutes * 60)


@dataclass
class Chunk:
    """A time-bounded slice of a video transcript."""

    index: int                          # 0-based chunk number
    start_seconds: float                # start of first entry in chunk
    end_seconds: float                  # start of first entry in the NEXT chunk (exclusive)
    entries: List[TranscriptEntry] = field(default_factory=list)

    @property
    def text(self) -> str:
        """All caption text in this chunk joined into one string."""
        return " ".join(e.text for e in self.entries)


def chunk_transcript(entries: List[TranscriptEntry]) -> List[Chunk]:
    """
    Split transcript entries into time-based chunks.

    Args:
        entries: Ordered list of TranscriptEntry objects (must be non-empty).

    Returns:
        A non-empty list of Chunk objects covering the full transcript.
    """
    if not entries:
        raise ValueError("Cannot chunk an empty transcript.")

    target_seconds = _chunk_target_seconds()
    video_duration = entries[-1].start_seconds

    # If the whole video fits in one chunk, return it as-is
    if video_duration <= target_seconds:
        return [
            Chunk(
                index=0,
                start_seconds=entries[0].start_seconds,
                end_seconds=entries[-1].start_seconds + 1,
                entries=list(entries),
            )
        ]

    chunks: List[Chunk] = []
    current_entries: List[TranscriptEntry] = []
    chunk_start = entries[0].start_seconds
    chunk_index = 0

    for i, entry in enumerate(entries):
        current_entries.append(entry)

        # Check if we've hit the target window boundary
        elapsed = entry.start_seconds - chunk_start
        is_last = i == len(entries) - 1

        if elapsed >= target_seconds or is_last:
            # End of chunk: boundary is the start of the current entry
            # (caption-boundary aligned, never mid-sentence)
            next_start = entries[i + 1].start_seconds if not is_last else entry.start_seconds + 1
            chunks.append(
                Chunk(
                    index=chunk_index,
                    start_seconds=chunk_start,
                    end_seconds=next_start,
                    entries=list(current_entries),
                )
            )
            chunk_index += 1
            current_entries = []
            if not is_last:
                chunk_start = entries[i + 1].start_seconds

    return chunks
