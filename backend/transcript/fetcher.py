"""
backend/transcript/fetcher.py

Fetches the timestamped caption transcript for a YouTube video.

This is the ONLY module in the project that imports youtube_transcript_api.
All transcript fetching must go through fetch_transcript().
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from youtube_transcript_api import (
    YouTubeTranscriptApi,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    CouldNotRetrieveTranscript,
)


class TranscriptError(Exception):
    """Raised when a transcript cannot be retrieved for a video."""


@dataclass
class TranscriptEntry:
    """A single caption segment from a YouTube video."""

    start_seconds: float
    text: str


def extract_video_id(url_or_id: str) -> str:
    """
    Extract a YouTube video ID from a full URL or return the raw ID if already bare.

    Supports:
        https://www.youtube.com/watch?v=VIDEO_ID
        https://youtu.be/VIDEO_ID
        VIDEO_ID  (11-char bare ID)
    """
    patterns = [
        r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)

    # Assume it is already a bare video ID if it looks like one
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url_or_id):
        return url_or_id

    raise TranscriptError(
        f"Could not extract a valid YouTube video ID from: {url_or_id!r}\n"
        "Expected a URL like https://www.youtube.com/watch?v=VIDEO_ID "
        "or a bare 11-character video ID."
    )


def fetch_transcript(url_or_id: str) -> tuple[str, List[TranscriptEntry]]:
    """
    Fetch the caption transcript for a YouTube video.

    Args:
        url_or_id: A YouTube video URL or bare video ID.

    Returns:
        A tuple of (video_id, list_of_TranscriptEntry).

    Raises:
        TranscriptError: If no captions are available or the video cannot be found.
            The error message is human-readable and suitable for direct display.
    """
    video_id = extract_video_id(url_or_id)

    try:
        # v1.x API: instantiate the class, then call .fetch()
        api = YouTubeTranscriptApi()
        raw = api.fetch(video_id)
    except TranscriptsDisabled:
        raise TranscriptError(
            f"No captions available for video '{video_id}'.\n"
            "The uploader has disabled subtitles/captions for this video.\n"
            "NoteCompanion requires captions to generate notes (no audio fallback in v1)."
        )
    except NoTranscriptFound:
        raise TranscriptError(
            f"No transcript found for video '{video_id}'.\n"
            "This video has no available captions in any language.\n"
            "NoteCompanion requires captions to generate notes (no audio fallback in v1)."
        )
    except VideoUnavailable:
        raise TranscriptError(
            f"Video '{video_id}' is unavailable (private, deleted, or age-restricted)."
        )
    except CouldNotRetrieveTranscript as exc:
        raise TranscriptError(
            f"Could not retrieve transcript for '{video_id}': {exc}"
        ) from exc
    except Exception as exc:
        raise TranscriptError(
            f"Unexpected error fetching transcript for '{video_id}': {exc}"
        ) from exc

    # v1.x returns a FetchedTranscript — iterable of snippet objects with .start and .text
    entries = [
        TranscriptEntry(start_seconds=float(snippet.start), text=snippet.text.strip())
        for snippet in raw
        if snippet.text.strip()
    ]

    if not entries:
        raise TranscriptError(
            f"Transcript for video '{video_id}' is empty (no caption text found)."
        )

    return video_id, entries
