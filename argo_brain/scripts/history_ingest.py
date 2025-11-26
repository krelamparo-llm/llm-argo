"""
Chrome history ingestion pipeline for Argo Brain.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from rag_core import ingest_url
from youtube_ingest import ingest_youtube_url

BASE_DIR = Path("/mnt/d/llm/argo_brain")
DATA_RAW_DIR = BASE_DIR / "data_raw"
CONFIG_DIR = BASE_DIR / "config"
STATE_PATH = DATA_RAW_DIR / "history_state.json"
HISTORY_COPY_PATH = DATA_RAW_DIR / "chrome_history_copy"
WINDOWS_USERNAME_FILE = CONFIG_DIR / "windows_username.txt"


def get_windows_username() -> str:
    """
    Resolve the Windows username so the script can locate Chrome history.

    The username is read from the WINDOWS_USERNAME environment variable if
    available, otherwise from config/windows_username.txt.
    """

    env_username = os.environ.get("WINDOWS_USERNAME")
    if env_username:
        return env_username.strip()
    if WINDOWS_USERNAME_FILE.exists():
        return WINDOWS_USERNAME_FILE.read_text(encoding="utf-8").strip()
    raise RuntimeError(
        "Windows username not configured. Set the WINDOWS_USERNAME environment "
        "variable or create config/windows_username.txt containing the username."
    )


def copy_history_db(username: str) -> Path:
    """
    Copy the locked Chrome History database into /mnt/d for safe querying.

    Args:
        username: Windows account name used in /mnt/c/Users/<username>.

    Returns:
        Path to the copied SQLite DB file.
    """

    source = (
        Path("/mnt/c/Users")
        / username
        / "AppData/Local/Google/Chrome/User Data/Default/History"
    )
    if not source.exists():
        raise FileNotFoundError(f"Chrome history file not found at {source}")
    DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, HISTORY_COPY_PATH)
    return HISTORY_COPY_PATH


def load_last_visit_time() -> int:
    """Return the last processed Chrome timestamp."""

    if STATE_PATH.exists():
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return int(data.get("last_visit_time", 0))
    return 0


def save_last_visit_time(timestamp: int) -> None:
    """Persist the last processed Chrome timestamp."""

    STATE_PATH.write_text(
        json.dumps({"last_visit_time": timestamp}, indent=2),
        encoding="utf-8",
    )


def fetch_new_history(conn: sqlite3.Connection, since: int) -> List[Tuple[str, str, int]]:
    """
    Fetch browser history entries newer than the provided timestamp.

    Args:
        conn: sqlite3 connection to the copied Chrome database.
        since: Chrome timestamp (microseconds since 1601) representing the last processed row.

    Returns:
        List of tuples shaped as (url, title, last_visit_time).
    """

    query = """
        SELECT url, title, last_visit_time
        FROM urls
        WHERE last_visit_time > ?
          AND url LIKE 'http%'
        ORDER BY last_visit_time ASC
    """
    cursor = conn.execute(query, (since,))
    return [(row[0], row[1], row[2]) for row in cursor.fetchall()]


def is_youtube_url(url: str) -> bool:
    """Return True when the URL appears to reference YouTube."""

    lowered = url.lower()
    return "youtube.com" in lowered or "youtu.be" in lowered


def process_url(url: str) -> None:
    """
    Dispatch ingestion based on whether a URL is a YouTube link or a general web page.

    Args:
        url: URL to ingest.
    """

    if is_youtube_url(url):
        ingest_youtube_url(url)
    else:
        ingest_url(url)


def run_ingestion() -> None:
    """Run the incremental Chrome history ingestion loop."""

    username = get_windows_username()
    history_path = copy_history_db(username)
    last_timestamp = load_last_visit_time()

    with sqlite3.connect(history_path) as conn:
        rows = fetch_new_history(conn, last_timestamp)

    if not rows:
        print("No new history entries found.")
        return

    latest_seen = last_timestamp
    for url, title, last_visit_time in rows:
        latest_seen = max(latest_seen, last_visit_time)
        print(f"Ingesting {url} (title: {title})")
        try:
            process_url(url)
        except Exception as exc:  # noqa: BLE001 - want to continue processing
            print(f"Failed to ingest {url}: {exc}")

    save_last_visit_time(latest_seen)
    print(f"Processed {len(rows)} entries. Updated last_visit_time to {latest_seen}.")


def _main(argv: List[str]) -> None:
    """CLI entry point."""

    if len(argv) != 1:
        print("Usage: python3 history_ingest.py")
        return
    run_ingestion()


if __name__ == "__main__":
    _main(sys.argv)
