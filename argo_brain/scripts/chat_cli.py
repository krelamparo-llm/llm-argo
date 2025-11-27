"""Interactive CLI for chatting with Argo using layered memory and tools."""

from __future__ import annotations

import argparse
import logging
import sys
import textwrap
import uuid
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from argo_brain.assistant.orchestrator import ArgoAssistant
from argo_brain.core.memory.session import SessionMode
from argo_brain.logging import setup_logging
from argo_brain.tools.base import ToolExecutionError, ToolResult

COMMANDS = {
    ":help": "Show this help message",
    ":quit": "Exit the chat session",
    ":new": "Start a new session with a fresh memory buffer",
    ":facts": "List stored profile facts",
    ":summary": "Show the current session summary",
    ":webcache": "Show recent tool/browser runs for this session",
    ":tools": "List available tools",
    ":tool": "Run a tool: :tool <name> <query_or_url>",
}


def _print_help() -> None:
    print("Available commands:")
    for cmd, desc in COMMANDS.items():
        print(f"  {cmd:<8} {desc}")


def _print_tools(assistant: ArgoAssistant) -> None:
    tools = assistant.available_tools()
    if not tools:
        print("No tools registered.")
        return
    for tool in tools:
        print(f"- {tool.name}: {tool.description}")


def _print_tool_runs(assistant: ArgoAssistant, session_id: str) -> None:
    runs = assistant.memory_manager.recent_tool_runs(session_id, limit=5)
    if not runs:
        print("No tool runs logged for this session yet.")
        return
    for run in runs:
        print(
            f"[{run.created_at}] {run.tool_name} input={run.input_payload} output_ref={run.output_ref or '-'}"
        )


def _run_tool_command(
    assistant: ArgoAssistant,
    session_id: str,
    user_input: str,
    pending_tool_results: List[ToolResult],
    session_mode: SessionMode,
) -> None:
    parts = user_input.split(maxsplit=2)
    if len(parts) < 3:
        print("Usage: :tool <name> <query_or_url>")
        return
    _, tool_name, tool_query = parts
    try:
        result = assistant.run_tool(
            tool_name,
            session_id,
            tool_query,
            session_mode=session_mode,
        )
    except ToolExecutionError as exc:
        print(f"Tool error: {exc}")
        return
    pending_tool_results.append(result)
    print(f"[tool:{tool_name}] {result.summary}")


def _render_debug_context(response, debug: bool, show_prompt: bool) -> None:
    context = response.context
    summary_flag = "yes" if context.session_summary else "no"
    print(
        f"[context] summary={summary_flag}, auto_mem={len(context.autobiographical_chunks)}, "
        f"rag={len(context.rag_chunks)}, web_cache={len(context.web_cache_chunks)}, "
        f"short_term={len(context.short_term_messages)}"
    )
    if debug and context.session_summary:
        print(f"[summary] {context.session_summary}")
    if context.autobiographical_chunks:
        print("[auto] " + " | ".join(chunk.text for chunk in context.autobiographical_chunks))
    if context.rag_chunks:
        print("[rag] " + " | ".join(chunk.metadata.get("source_type", "unknown") for chunk in context.rag_chunks))
    if context.web_cache_chunks:
        print(
            "[web] "
            + " | ".join(
                f"{chunk.metadata.get('url', 'n/a')} @ {chunk.metadata.get('fetched_at', 'unknown')}"
                for chunk in context.web_cache_chunks
            )
        )
    if context.tool_results:
        print("[tools] " + " | ".join(result.summary for result in context.tool_results))
    if show_prompt and response.prompt_messages:
        print("\n[prompt]\n" + "\n".join(f"{m.role}: {m.content}" for m in response.prompt_messages))


def _render_answer(response, debug: bool) -> None:
    if debug and response.thought:
        print(textwrap.indent(response.thought, prefix="[think] "))
    print(f"Argo> {response.text}\n")


def chat_loop(
    initial_session: str,
    mode: SessionMode,
    debug: bool = False,
    show_prompt: bool = False,
) -> None:
    setup_logging()
    logger = logging.getLogger("argo_brain.cli")
    assistant = ArgoAssistant(default_session_mode=mode)
    session_id = initial_session
    pending_tool_results: List[ToolResult] = []
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
                logger.info("Session %s exiting chat loop", session_id)
                break
            if cmd == ":help":
                logger.debug("Help requested", extra={"session_id": session_id})
                _print_help()
                continue
            if cmd == ":new":
                session_id = uuid.uuid4().hex[:8]
                pending_tool_results.clear()
                logger.info("Starting new session %s", session_id)
                print(f"New session: {session_id}")
                continue
            if cmd == ":facts":
                logger.debug("Listing profile facts", extra={"session_id": session_id})
                print(assistant.list_profile_facts())
                continue
            if cmd == ":summary":
                logger.debug("Showing session summary", extra={"session_id": session_id})
                summary = assistant.memory_manager.get_session_summary(session_id)
                print(summary or "No summary yet.")
                continue
            if cmd == ":webcache":
                logger.debug("Listing web cache/tool runs", extra={"session_id": session_id})
                _print_tool_runs(assistant, session_id)
                continue
            if cmd == ":tools":
                logger.debug("Listing tools", extra={"session_id": session_id})
                _print_tools(assistant)
                continue
            if cmd.startswith(":tool"):
                logger.debug("Running tool command", extra={"session_id": session_id})
                _run_tool_command(assistant, session_id, user_input, pending_tool_results, mode)
                continue
            print(f"Unknown command: {user_input}")
            continue
        logger.info(
            "Processing user message",
            extra={"session_id": session_id, "chars": len(user_input)},
        )
        response = assistant.send_message(
            session_id,
            user_input,
            tool_results=pending_tool_results or None,
            return_prompt=show_prompt or debug,
            session_mode=mode,
        )
        pending_tool_results = []
        logger.info(
            "Assistant replied",
            extra={"session_id": session_id, "chars": len(response.text)},
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
    parser.add_argument(
        "--mode",
        choices=[m.value for m in SessionMode],
        default=SessionMode.QUICK_LOOKUP.value,
        help="Session mode guiding ingestion defaults",
    )
    args = parser.parse_args(argv)
    session_id = args.session or uuid.uuid4().hex[:8]
    mode = SessionMode.from_raw(args.mode)
    chat_loop(session_id, mode, debug=args.debug, show_prompt=args.show_prompt)


if __name__ == "__main__":
    main(sys.argv[1:])
