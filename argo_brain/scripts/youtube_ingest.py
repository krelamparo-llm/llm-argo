"""
YouTube transcript ingestion utilities for the Argo Brain project.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)

from argo_brain.core.memory.document import SourceDocument
from argo_brain.core.memory.session import SessionMode
from argo_brain.runtime import create_runtime

YOUTUBE_ID_PATTERN = re.compile(
    r"(?:v=|youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})"
)

INGESTION_MANAGER = create_runtime().ingestion_manager


def extract_video_id(url: str) -> Optional[str]:
    """
    Extract the YouTube video ID from common URL formats.

    Args:
        url: Raw URL copied from the browser.

    Returns:
        The 11-character video ID or None if no ID was found.
    """

    match = YOUTUBE_ID_PATTERN.search(url)
    return match.group(1) if match else None


def _get_transcript(video_id: str, languages: Optional[List[str]] = None) -> List[dict]:
    """Fetch the transcript segments for a video, trying a list of languages."""

    langs = languages or ["en", "en-US", "en-GB"]
    try:
        return YouTubeTranscriptApi.get_transcript(video_id, languages=langs)
    except (NoTranscriptFound, TranscriptsDisabled):
        # Fall back to auto-generated captions or other languages.
        return YouTubeTranscriptApi.get_transcript(video_id)


def fetch_transcript_text(video_id: str) -> str:
    """
    Retrieve and join the transcript text for a YouTube video.

    Args:
        video_id: Unique 11-character ID of the YouTube video.

    Returns:
        Plain-text transcript.
    """

    segments = _get_transcript(video_id)
    return "\n".join(segment["text"].strip() for segment in segments if segment["text"])


def ingest_youtube_url(url: str) -> None:
    """
    Fetch and ingest the transcript associated with a YouTube URL.

    Args:
        url: Full YouTube watch/share URL.
    """

    video_id = extract_video_id(url)
    if not video_id:
        raise ValueError(f"Could not find a video ID in URL: {url}")
    transcript = fetch_transcript_text(video_id)
    doc = SourceDocument(
        id=f"youtube:{video_id}",
        source_type="youtube_transcript",
        raw_text=transcript,
        cleaned_text=transcript,
        url=url,
        metadata={
            "video_id": video_id,
            "fetched_ts": int(time.time()),
        },
    )
    INGESTION_MANAGER.ingest_document(
        doc,
        session_mode=SessionMode.INGEST,
        user_intent="explicit_save",
    )


def _main(argv: List[str]) -> None:
    """CLI entry point for ingesting a single YouTube URL."""

    if len(argv) != 2:
        print("Usage: python3 youtube_ingest.py <youtube_url>")
        return
    ingest_youtube_url(argv[1])
    print(f"Ingested transcript for {argv[1]}")


if __name__ == "__main__":
    _main(sys.argv)
