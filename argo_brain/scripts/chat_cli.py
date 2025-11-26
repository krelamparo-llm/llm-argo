"""Interactive CLI for chatting with Argo using layered memory."""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from argo_brain.assistant.orchestrator import ArgoAssistant

COMMANDS = {
    ":help": "Show this help message",
    ":quit": "Exit the chat session",
    ":new": "Start a new session with a fresh memory buffer",
    ":facts": "List stored profile facts",
    ":summary": "Show the current session summary",
}


def _print_help() -> None:
    print("Available commands:")
    for cmd, desc in COMMANDS.items():
        print(f"  {cmd:<8} {desc}")


def chat_loop(initial_session: str) -> None:
    assistant = ArgoAssistant()
    session_id = initial_session
    print("Starting Argo chat. Type :help for commands.")
    while True:
        try:
            user_input = input("You> ").strip()
        except EOFError:
            print()
            break
        if not user_input:
            continue
        if user_input.startswith(":"):
            cmd = user_input.lower()
            if cmd in (":quit", ":q"):
                break
            if cmd == ":help":
                _print_help()
                continue
            if cmd == ":new":
                session_id = uuid.uuid4().hex[:8]
                print(f"New session: {session_id}")
                continue
            if cmd == ":facts":
                print(assistant.list_profile_facts())
                continue
            if cmd == ":summary":
                summary = assistant.memory_manager.get_session_summary(session_id)
                print(summary or "No summary yet.")
                continue
            print(f"Unknown command: {user_input}")
            continue
        response = assistant.send_message(session_id, user_input)
        print(f"Argo> {response.text}\n")
        context = response.context
        summary_flag = "yes" if context.session_summary else "no"
        print(
            f"[context] summary={summary_flag}, auto_mem={len(context.autobiographical_chunks)}, "
            f"rag={len(context.rag_chunks)}"
        )
        if context.autobiographical_chunks:
            print("[auto] " + " | ".join(chunk.text for chunk in context.autobiographical_chunks))
        if context.rag_chunks:
            print("[rag] " + " | ".join(chunk.metadata.get("source_type", "unknown") for chunk in context.rag_chunks))
        print()


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Chat with Argo in the terminal")
    parser.add_argument(
        "--session",
        help="Existing session ID to resume (default: random)",
    )
    args = parser.parse_args(argv)
    session_id = args.session or uuid.uuid4().hex[:8]
    chat_loop(session_id)


if __name__ == "__main__":
    main(sys.argv[1:])
