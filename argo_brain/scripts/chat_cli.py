"""Interactive CLI for chatting with Argo using layered memory."""

from __future__ import annotations

import argparse
import sys
import textwrap
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


def _render_debug_context(response, debug: bool, show_prompt: bool) -> None:
    context = response.context
    summary_flag = "yes" if context.session_summary else "no"
    print(
        f"[context] summary={summary_flag}, auto_mem={len(context.autobiographical_chunks)}, "
        f"rag={len(context.rag_chunks)}, short_term={len(context.short_term_messages)}"
    )
    if debug and context.session_summary:
        print(f"[summary] {context.session_summary}")
    if context.autobiographical_chunks:
        print("[auto] " + " | ".join(chunk.text for chunk in context.autobiographical_chunks))
    if context.rag_chunks:
        print("[rag] " + " | ".join(chunk.metadata.get("source_type", "unknown") for chunk in context.rag_chunks))
    if show_prompt and response.prompt_messages:
        print("\n[prompt]\n" + "\n".join(f"{m.role}: {m.content}" for m in response.prompt_messages))


def _render_answer(response, debug: bool) -> None:
    if debug and response.thought:
        print(textwrap.indent(response.thought, prefix="[think] "))
    print(f"Argo> {response.text}\n")


def chat_loop(initial_session: str, debug: bool = False, show_prompt: bool = False) -> None:
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
        response = assistant.send_message(
            session_id,
            user_input,
            return_prompt=show_prompt or debug,
        )
        _render_answer(response, debug)
        _render_debug_context(response, debug=debug, show_prompt=show_prompt)
        print()


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Chat with Argo in the terminal")
    parser.add_argument(
        "--session",
        help="Existing session ID to resume (default: random)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show additional context (summary, memory counts, think blocks if present)",
    )
    parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="Dump the full prompt messages sent to the LLM",
    )
    args = parser.parse_args(argv)
    session_id = args.session or uuid.uuid4().hex[:8]
    chat_loop(session_id, debug=args.debug, show_prompt=args.show_prompt)


if __name__ == "__main__":
    main(sys.argv[1:])
