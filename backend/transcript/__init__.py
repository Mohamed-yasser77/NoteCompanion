"""
backend/transcript/__init__.py
Transcript module — the ONLY place in the codebase that imports youtube_transcript_api.
All other modules that need transcript data must call functions from this module.
"""
from .fetcher import fetch_transcript, TranscriptError
from .chunker import chunk_transcript, Chunk

__all__ = ["fetch_transcript", "TranscriptError", "chunk_transcript", "Chunk"]
