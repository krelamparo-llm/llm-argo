# Research Mode Synthesis Fix

## Problem Identified

**Root Cause**: Research mode creates a plan successfully, but then **exits the loop without executing tools** when the LLM doesn't respond with a tool call after being prompted.

### Evidence
- TEST-004, TEST-005, TEST-011 all show **only** `<research_plan>`, no tool execution or synthesis
- Even though tests "pass" (validation was relaxed), the actual behavior is broken

### Code Flow Analysis

**File**: `orchestrator.py:1127-1351`

```
1. LLM generates <research_plan>
2. Code detects plan (line 1128-1133), sets has_plan=True
3. Checks if <tool_call> is in response (line 1136)
4. If NO tool call found, adds prompt: "Output your FIRST tool call now" (line 1137-1141)
5. Adds to extra_messages and continues loop (line 1141-1143)

-- NEXT ITERATION --

6. LLM is called again with the "output tool call" prompt
7. Response comes back
8. _maybe_parse_plan() tries to extract tool calls (line 1145)
9. IF NO TOOL CALL FOUND:
   → Line 1342-1351: Logs warning and BREAKS out of loop
   → Returns only the research plan
```

**The Critical Bug** (orchestrator.py:1341-1351):
```python
# No tool call detected and no recovery possible - log and exit
self.logger.warning(
    "Conversation loop exiting without tool call",
    extra={
        "session_id": session_id,
        "iterations": iterations,
        "response_preview": response_text[:200],
        "tool_results_count": len(tool_results_accum)
    }
)
break  # ← THIS EXITS THE LOOP TOO EARLY IN RESEARCH MODE
```

---

## Why This Happens

### Hypothesis 1: LLM Not Following Instructions
The model is prompted "Output your FIRST tool call now" but:
- Might be confused by the context
- Might be generating text explanation instead of XML
- Might hit a stop sequence prematurely
- Might be repeating the plan instead of outputting tools

### Hypothesis 2: max_tokens Too Low
Planning phase uses lower temperature and might have restricted tokens, causing truncation before tool call is generated.

### Hypothesis 3: Tool Call Format Issues
The model might be outputting tool calls in a format that `_maybe_parse_plan()` doesn't recognize:
- Wrong XML structure
- Missing closing tags
- JSON instead of XML (or vice versa)

---

## Proposed Fixes

### Fix 1: Don't Exit Early in Research Mode (IMMEDIATE)

**Location**: `orchestrator.py:1341-1351`

**Change**: Add special handling for research mode to retry more aggressively:

```python
# No tool call detected - decide whether to exit or retry
if active_mode == SessionMode.RESEARCH and research_stats["has_plan"] and iterations < 3:
    # In research mode with a plan, retry up to 3 times to get tool execution
    retry_prompt = (
        "CRITICAL ERROR: You created a research plan but did not execute any tools.\n\n"
        "You MUST now output a tool call to execute your first search from the plan.\n\n"
        "Example:\n"
        f"{'<tool_call><function=web_search><parameter=query>Claude vs GPT-4 differences</parameter></function></tool_call>' if self.use_xml_format else '{\"name\": \"web_search\", \"arguments\": {\"query\": \"Claude vs GPT-4 differences\"}}'}\n\n"
        "Output ONLY the tool call. No explanation. STOP after the closing tag."
    )
    extra_messages.append(ChatMessage(role="system", content=retry_prompt))
    self.logger.warning(
        "Research mode: no tool call after plan, retrying",
        extra={"session_id": session_id, "retry_attempt": iterations}
    )
    continue  # Retry

# For other modes or after retries exhausted, exit
self.logger.warning(
    "Conversation loop exiting without tool call",
    extra={
        "session_id": session_id,
        "iterations": iterations,
        "response_preview": response_text[:200],
        "tool_results_count": len(tool_results_accum)
    }
)
break
```

---

### Fix 2: Improve "Output Tool Call" Prompt (MEDIUM PRIORITY)

**Location**: `orchestrator.py:1137-1140`

**Current**:
```python
prompt_for_tools = (
    "Good! You've created a research plan. Now IMMEDIATELY begin executing your first search.\n\n"
    "Output your FIRST tool call now (no other text)."
)
```

**Improved**:
```python
prompt_for_tools = (
    "RESEARCH PLAN ACCEPTED. Now execute the FIRST search from your plan.\n\n"
    "Output format (EXACTLY this structure, replace query with your search):\n"
    f"{'<tool_call><function=web_search><parameter=query>your search query here</parameter></function></tool_call>' if self.use_xml_format else '<tool_call>{\"name\": \"web_search\", \"arguments\": {\"query\": \"your search query here\"}}</tool_call>'}\n\n"
    "Use the FIRST query from your search strategy. Output ONLY the tool call above. STOP after closing tag."
)
```

---

### Fix 3: Add Diagnostic Logging (IMMEDIATE)

**Location**: `orchestrator.py:1145` (before _maybe_parse_plan)

```python
# Log the raw response for debugging
if active_mode == SessionMode.RESEARCH:
    self.logger.debug(
        "Research mode response after plan",
        extra={
            "session_id": session_id,
            "has_plan": research_stats["has_plan"],
            "response_preview": response_text[:500],
            "has_tool_call_tag": "<tool_call>" in response_text.lower(),
        }
    )

plan_payload = self._maybe_parse_plan(response_text)
if not plan_payload and active_mode == SessionMode.RESEARCH and research_stats["has_plan"]:
    self.logger.warning(
        "Failed to parse tool calls in research mode",
        extra={
            "session_id": session_id,
            "response_text": response_text[:1000],  # Log more for debugging
        }
    )
```

---

### Fix 4: Validate Tool Call Parsing (INVESTIGATION)

Check if `_maybe_parse_plan()` is failing to extract tool calls that ARE in the response.

**Test**:
1. Add logging of raw LLM responses
2. Check if `<tool_call>` tags are present but not being parsed
3. Verify XML structure matches what the parser expects

---

## Implementation Priority

| Priority | Fix | Effort | Impact |
|----------|-----|--------|--------|
| **P0** | Fix 1: Don't exit early in research mode | 10 min | Fixes TEST-004, TEST-005, TEST-011 |
| **P0** | Fix 3: Add diagnostic logging | 5 min | Enables debugging |
| **P1** | Fix 2: Improve tool call prompt | 10 min | Better LLM guidance |
| **P2** | Fix 4: Validate parser | 30 min | Catches edge cases |

---

## Testing Plan

After implementing Fix 1 + Fix 3:

1. Run TEST-004, TEST-005, TEST-011 with logging enabled
2. Check logs for:
   - "Prompting for tool execution after plan"
   - "Research mode: no tool call after plan, retrying"
   - Raw response text showing what LLM actually generated
3. Verify tool calls are being extracted or identify why they're not

### Success Criteria
- Research tests should show: Plan → Tool Execution → Synthesis
- Logs should show the full flow: plan creation → tool prompt → tool execution → synthesis trigger
- No more "exiting without tool call" warnings in research mode (unless retries exhausted)

---

## Alternative: Force Tool Execution

If the LLM continues to not output tool calls even with better prompts, we can **force** tool execution programmatically:

```python
# After plan creation, if no tool call detected after 2 retries:
if active_mode == SessionMode.RESEARCH and research_stats["has_plan"] and iterations >= 2 and not tool_results_accum:
    # Extract first query from plan and force execute it
    plan_text = research_stats.get("plan_text", "")
    first_query = self._extract_first_search_query(plan_text)
    if first_query:
        self.logger.info(
            "Forcing tool execution with extracted query",
            extra={"session_id": session_id, "query": first_query}
        )
        # Create synthetic tool call
        forced_proposal = ProposedToolCall(
            tool="web_search",
            arguments={"query": first_query}
        )
        # Execute it
        result = self._execute_single_tool(forced_proposal, session_id, user_message, active_mode)
        tool_results_accum.append(result)
        research_stats["tool_calls"] += 1
        research_stats["searches"] += 1
```

This is a **last resort** but ensures research mode always executes at least one search.
