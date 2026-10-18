"""
backend/pipeline/cli.py

Phase 1 CLI entrypoint.

Usage:
    python -m backend.pipeline.cli <youtube_url_or_video_id>

What it does (Phase 1 scope):
    1. Fetch transcript
    2. Chunk by time
    3. LLM: notes per chunk
    4. LLM: summary
    5. Print timestamped notes to stdout (no file save yet — that is Phase 2)

Phase 2+ (not here yet): save to markdown, push to GitHub, calendar.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is on sys.path when run as a module
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from dotenv import load_dotenv
load_dotenv()  # load .env before any module reads env vars

from backend.transcript import fetch_transcript, TranscriptError, chunk_transcript
from backend.pipeline.notes_generator import generate_notes


def _seconds_to_mmss(seconds: float) -> str:
    """Convert a float seconds value to MM:SS display string."""
    total = int(seconds)
    mm, ss = divmod(total, 60)
    return f"{mm:02d}:{ss:02d}"


def _print_notes(video_id: str, notes) -> None:
    """Print the generated notes to stdout in the SPEC note file format."""
    print()
    print("=" * 70)
    print(f"  {notes.title}")
    print(f"  Source: https://youtu.be/{video_id}")
    print("=" * 70)
    print()
    print("## Summary")
    print(notes.summary)
    print()

    if notes.truncated:
        cap = len(notes.chunks)
        total = notes.total_chunks
        print(
            f"> ⚠️  Notes truncated after chunk {cap} of {total} "
            f"due to cost cap (MAX_CHUNKS_PER_VIDEO={cap})."
        )
        print()

    print("## Notes")
    for cn in notes.chunks:
        timestamp = _seconds_to_mmss(cn.start_seconds)
        yt_link = f"https://youtu.be/{video_id}?t={int(cn.start_seconds)}"
        print(f"\n### [{timestamp}] {cn.topic}  (link: {yt_link})")
        for bullet in cn.bullets:
            print(f"  - {bullet}")

    print()


def run(url_or_id: str) -> None:
    """
    Main Phase 1 pipeline: fetch → chunk → notes → print.

    Args:
        url_or_id: YouTube URL or bare video ID.
    """
    print(f"[>] Fetching transcript for: {url_or_id}")
    try:
        video_id, entries = fetch_transcript(url_or_id)
    except TranscriptError as exc:
        print(f"\n[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"[OK] Got {len(entries)} caption entries for video '{video_id}'")

    print("[~] Chunking transcript...")
    chunks = chunk_transcript(entries)
    print(f"[OK] {len(chunks)} chunk(s) created")

    print("[AI] Generating notes (this may take a moment)...")
    notes = generate_notes(chunks)
    print("[OK] Notes generated")

    _print_notes(video_id, notes)


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: python -m backend.pipeline.cli <youtube_url_or_video_id>\n"
            "Example: python -m backend.pipeline.cli https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            file=sys.stderr,
        )
        sys.exit(1)

    run(sys.argv[1])


if __name__ == "__main__":
    main()
