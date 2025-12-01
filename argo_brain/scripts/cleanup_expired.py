#!/usr/bin/env python3
"""Background task to purge expired web cache entries.

This script should be run periodically (e.g., daily via cron or systemd timer)
to remove web_cache entries older than the configured TTL.

Setup:
    Linux (cron):
        0 3 * * * cd /home/krela/llm-argo/argo_brain && python scripts/cleanup_expired.py

    Windows (Task Scheduler):
        schtasks /create /tn "ArgoCleanup" /tr "wsl python /home/krela/llm-argo/argo_brain/scripts/cleanup_expired.py" /sc daily /st 03:00
"""

import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from argo_brain.config import CONFIG
from argo_brain.vector_store import get_vector_store


def cleanup_web_cache():
    """Delete web_cache entries older than TTL."""

    policy = CONFIG.collections.get_policy(CONFIG.collections.web_cache)
    if policy.ttl_days is None:
        print("Web cache has no TTL configured - no cleanup needed")
        return 0

    current_time = int(time.time())
    max_age_seconds = policy.ttl_days * 86400
    cutoff_timestamp = current_time - max_age_seconds

    print(f"Cleaning web cache entries older than {policy.ttl_days} days...")
    print(f"Cutoff timestamp: {cutoff_timestamp} ({time.ctime(cutoff_timestamp)})")

    vector_store = get_vector_store()

    try:
        # Delete chunks with fetched_at < cutoff
        deleted_count = vector_store.delete(
            namespace=CONFIG.collections.web_cache, filters={"fetched_at": {"$lt": cutoff_timestamp}}
        )

        print(f"✓ Deleted {deleted_count} expired web cache entries")
        return deleted_count
    except Exception as e:
        print(f"✗ Cleanup failed: {e}", file=sys.stderr)
        return 0


def cleanup_all_namespaces():
    """Clean up all namespaces with TTL policies."""

    total_deleted = 0

    # Get all namespaces with TTL
    namespaces_with_ttl = [
        (CONFIG.collections.web_cache, CONFIG.collections.get_policy(CONFIG.collections.web_cache)),
        # Add more if you configure TTL for other namespaces
    ]

    for namespace, policy in namespaces_with_ttl:
        if policy.ttl_days is None:
            continue

        print(f"\nCleaning namespace: {namespace} (TTL: {policy.ttl_days} days)")

        current_time = int(time.time())
        max_age_seconds = policy.ttl_days * 86400
        cutoff_timestamp = current_time - max_age_seconds

        vector_store = get_vector_store()

        try:
            deleted_count = vector_store.delete(
                namespace=namespace, filters={"fetched_at": {"$lt": cutoff_timestamp}}
            )
            print(f"  ✓ Deleted {deleted_count} entries")
            total_deleted += deleted_count
        except Exception as e:
            print(f"  ✗ Failed: {e}", file=sys.stderr)

    return total_deleted


if __name__ == "__main__":
    print("=" * 60)
    print("Argo Brain - Expired Content Cleanup")
    print("=" * 60)

    deleted = cleanup_all_namespaces()

    print("\n" + "=" * 60)
    print(f"Total entries deleted: {deleted}")
    print("=" * 60)
