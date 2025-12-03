"""Lightweight LLM-readable logging utilities.

Designed for minimal token overhead while maximizing semantic clarity for LLMs.
"""

from enum import Enum


class LogTag(str, Enum):
    """Compact semantic tags for LLM log parsing.

    Format: [CATEGORY:EVENT] - short, descriptive, parseable.
    Examples: [R:URL], [R:SYNTH], [STATE:->]
    """

    # Research mode events (R: prefix for brevity)
    RESEARCH_URL = "R:URL"           # URL tracking
    RESEARCH_SEARCH = "R:SRCH"       # Search queries
    RESEARCH_PLAN = "R:PLAN"         # Research plan created
    RESEARCH_SYNTHESIS = "R:SYNTH"   # Synthesis triggered
    RESEARCH_CHECK = "R:CHK"         # Synthesis condition check

    # State transitions (compact arrows)
    STATE_TRANSITION = "STATE:->"    # State changes

    # Execution paths (E: prefix)
    EXEC_BATCH = "E:BATCH"           # Batch execution
    EXEC_INDIVIDUAL = "E:INDV"       # Individual execution

    # Decisions (D: prefix)
    DECISION = "D:"                  # Decision point


def format_llm_log(
    tag: LogTag,
    message: str,
    context: dict | None = None,
    milestone: bool = False
) -> str:
    """
    Format log message for LLM consumption with minimal tokens.

    Example outputs:
    - "[R:URL] #3/3 ✓ (batch)"
    - "[STATE:->] exec->synth (3 URLs)"
    - "[D:] trigger=Y (plan=Y, urls=3)"

    Args:
        tag: Semantic tag for event type
        message: Core message (keep brief)
        context: Key-value pairs (optional, keep minimal)
        milestone: Add ✓ marker for important events

    Returns:
        Formatted log string optimized for LLM parsing
    """
    parts = [f"[{tag}]"]

    if milestone:
        parts.append("✓")  # Single char milestone marker

    parts.append(message)

    # Add context only if present - use compact format
    if context:
        # Use short keys: p=batch, u=3, not execution_path=batch, urls=3
        compact = ", ".join(f"{k}={v}" for k, v in context.items())
        parts.append(f"({compact})")

    return " ".join(parts)


def format_state_transition(from_state: str, to_state: str, reason: str) -> str:
    """Format state transition with minimal tokens.

    Example: "[STATE:->] exec->synth (3 URLs+plan)"
    """
    # Use arrow notation, abbreviated states, brief reason
    message = f"{from_state[:4]}→{to_state[:4]}"  # First 4 chars + arrow
    return format_llm_log(
        LogTag.STATE_TRANSITION,
        message,
        context={"why": reason} if len(reason) < 30 else None,
        milestone=True
    )


def format_decision(
    decision_point: str,
    outcome: bool,
    **rationale
) -> str:
    """Format decision with compact rationale.

    Example: "[D:] synth=Y (plan=Y, u=3/3)"

    Keep rationale keys short:
    - p=plan, u=urls, t=triggered, etc.
    """
    outcome_char = "Y" if outcome else "N"
    message = f"{decision_point[:5]}={outcome_char}"  # Abbreviated

    # Only include rationale if outcome is interesting (False or True with constraints)
    if not outcome or len(rationale) > 0:
        return format_llm_log(LogTag.DECISION, message, context=rationale)

    return format_llm_log(LogTag.DECISION, message)


def format_progress(
    event_type: LogTag,
    current: int,
    total: int,
    **context
) -> str:
    """Format progress indicator.

    Example: "[R:URL] #3/3 ✓ (batch)"
    """
    message = f"#{current}/{total}"
    milestone = (current >= total)
    return format_llm_log(event_type, message, context=context, milestone=milestone)
