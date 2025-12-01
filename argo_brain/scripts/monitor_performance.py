#!/usr/bin/env python3
"""Performance monitoring script for Argo Brain.

This script tails the log file and shows timing information in real-time.
"""

import re
import sys
import time
from pathlib import Path


def tail_logs(log_path: Path):
    """Tail the log file and show performance metrics."""

    print("=" * 80)
    print("Argo Brain Performance Monitor")
    print("=" * 80)
    print(f"Monitoring: {log_path}")
    print("=" * 80)
    print()

    # Track timing between events
    last_timestamp = None
    last_event = None

    try:
        with log_path.open('r') as f:
            # Go to end of file
            f.seek(0, 2)

            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.1)
                    continue

                # Parse log line
                # Format: 2025-12-01T15:29:31 [INFO] argo_brain.llm_client - LLM request completed
                match = re.match(
                    r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}) \[(\w+)\] ([\w.]+) - (.+)',
                    line
                )

                if not match:
                    continue

                timestamp, level, logger, message = match.groups()

                # Extract elapsed_ms if present
                elapsed_match = re.search(r'elapsed_ms=([\d.]+)', message)
                tokens_match = re.search(r'tokens_max=(\d+)', message)

                # Calculate time since last event
                if last_timestamp:
                    try:
                        from datetime import datetime
                        current = datetime.fromisoformat(timestamp)
                        previous = datetime.fromisoformat(last_timestamp)
                        delta = (current - previous).total_seconds()
                    except:
                        delta = 0
                else:
                    delta = 0

                # Color coding for events
                color = ""
                reset = "\033[0m"

                if "LLM request completed" in message:
                    color = "\033[92m"  # Green
                    if elapsed_match:
                        elapsed = float(elapsed_match.group(1))
                        print(f"{color}[{timestamp}] LLM completed in {elapsed/1000:.2f}s (since last: {delta:.1f}s){reset}")
                        if elapsed > 60000:  # More than 60 seconds
                            print(f"  ⚠️  WARNING: Very slow LLM response!")
                elif "Executing tool" in message:
                    color = "\033[94m"  # Blue
                    tool_match = re.search(r'tool=([\w_]+)', message)
                    tool_name = tool_match.group(1) if tool_match else "unknown"
                    print(f"{color}[{timestamp}] Executing tool: {tool_name} (since last: {delta:.1f}s){reset}")
                elif "Web search completed" in message or "WebAccessTool fetched" in message:
                    color = "\033[93m"  # Yellow
                    print(f"{color}[{timestamp}] Tool completed (since last: {delta:.1f}s){reset}")
                elif "User message received" in message:
                    color = "\033[95m"  # Magenta
                    print(f"\n{color}{'='*80}{reset}")
                    print(f"{color}[{timestamp}] NEW USER MESSAGE{reset}")
                    print(f"{color}{'='*80}{reset}\n")
                elif "Assistant completed response" in message:
                    color = "\033[96m"  # Cyan
                    print(f"{color}[{timestamp}] RESPONSE COMPLETE (total time: {delta:.1f}s){reset}\n")

                last_timestamp = timestamp
                last_event = message

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped.")


def main():
    """Main entry point."""

    # Find log file
    log_candidates = [
        Path("/home/krela/llm-argo/.argo_data/state/logs/argo_brain.log"),
        Path("../.argo_data/state/logs/argo_brain.log"),
        Path(".argo_data/state/logs/argo_brain.log"),
    ]

    log_path = None
    for candidate in log_candidates:
        if candidate.exists():
            log_path = candidate
            break

    if not log_path:
        print("Error: Could not find log file")
        print("Tried:")
        for c in log_candidates:
            print(f"  - {c}")
        sys.exit(1)

    tail_logs(log_path)


if __name__ == "__main__":
    main()
