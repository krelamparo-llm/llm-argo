# Research Plan Bug Fix

## Problem

When using research mode, the model would output a `<research_plan>` but then stop WITHOUT executing any tools, even though the plan explicitly stated what searches needed to be done.

### Example Behavior (Before Fix)

```
User: What did Anthropic announce about Claude 3.5 Opus in December 2024?

Argo: <research_plan>
To find information about Anthropic's December 2024 announcements:
1. Search for official announcements from Anthropic
2. Look for press releases about Claude 3.5 Opus
3. Check for specific updates in December 2024
</research_plan>

[No tools executed - just returns the plan]
```

## Root Cause

The research mode prompt says:
> "**PHASE 1: PLANNING**
> First response: Provide ONLY a research plan in <research_plan> tags"

The model follows this instruction literally:
1. Model outputs `<research_plan>...</research_plan>`
2. Stops (as instructed: "ONLY a research plan")
3. Code checks for tool calls via `_maybe_parse_plan()`
4. No tool calls found → returns None
5. Loop breaks at line 864
6. Returns the plan as the final answer

## The Fix

Added logic at [orchestrator.py:711-719](argo_brain/argo_brain/assistant/orchestrator.py#L711-L719):

```python
# If plan was created but no tool call in same response, prompt for tool execution
if "<tool_call>" not in response_text.lower():
    prompt_for_tools = (
        "Good! You've created a research plan. Now IMMEDIATELY begin executing your first search.\n\n"
        "Output your FIRST tool call now (no other text)."
    )
    extra_messages.append(ChatMessage(role="system", content=prompt_for_tools))
    self.logger.info("Prompting for tool execution after plan", extra={"session_id": session_id})
    continue  # Continue loop to get tool call
```

### How It Works

1. Model outputs `<research_plan>` (Phase 1 complete)
2. System detects plan was created
3. System checks if tool call was also provided
4. If no tool call found, system adds a prompt: "Now execute your first search"
5. Loop continues → model outputs tool call
6. Tools execute normally

## Logs Before Fix

```
2025-12-02T00:30:02 [INFO] Research plan created [session=8e1785c8]
2025-12-02T00:30:03 [INFO] Assistant completed response [session=8e1785c8]
```

No tool execution logged!

## Expected Logs After Fix

```
2025-12-02T00:30:02 [INFO] Research plan created [session=8e1785c8]
2025-12-02T00:30:02 [INFO] Prompting for tool execution after plan [session=8e1785c8]
2025-12-02T00:30:03 [INFO] Executing tool [session=8e1785c8, tool=web_search]
2025-12-02T00:30:04 [INFO] Web search completed [session=8e1785c8]
```

Tool execution happens automatically after plan!

## Related Issue: Model Name Configuration

The original debugging also revealed that the system was configured to use `model_name: qwen3-coder-30b` but the user wanted to test with `qwen3-coder-30b-unsloth`.

To use the Unsloth model, update your config to:
```yaml
llm:
  model_name: qwen3-coder-30b-unsloth
```

This will automatically load the correct prompt configuration:
- **qwen3-coder-30b**: XML format, thinking enabled
- **qwen3-coder-30b-unsloth**: JSON format, thinking disabled

## Testing

To test the fix:
1. Start Argo with research mode
2. Ask a question requiring web search
3. Verify the model:
   - Creates a research plan
   - **Automatically executes tools** after the plan
   - Gathers multiple sources
   - Provides synthesis with citations

Example test query:
```
What did Anthropic announce about Claude 3.5 Opus in December 2024? Search for official announcements.
```

Expected behavior:
1. Model outputs `<research_plan>`
2. System prompts for tool execution
3. Model outputs `<tool_call>` for web_search
4. Tools execute
5. Model continues research
6. Final synthesis provided

## Files Modified

- [orchestrator.py:711-719](argo_brain/argo_brain/assistant/orchestrator.py#L711-L719) - Added prompt after plan detection
