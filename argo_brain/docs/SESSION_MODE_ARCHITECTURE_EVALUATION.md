# Session Mode Architecture Evaluation

**Date**: December 2, 2025
**Reviewer**: Senior Staff Python Architect
**Project**: Argo Brain - Personal AI Assistant
**Focus**: SessionMode architecture patterns and best practices compliance

---

## Executive Summary

This evaluation analyzes the three session modes (`QUICK_LOOKUP`, `RESEARCH`, `INGEST`) in [orchestrator.py](argo_brain/argo_brain/assistant/orchestrator.py) against industry best practices and Anthropic's recommended patterns.

### Overall Assessment: **B+ (Good with Notable Gaps)**

**Strengths**:
- ✅ Clean mode separation with distinct behaviors
- ✅ Planning-first architecture for RESEARCH mode
- ✅ Parallel tool execution (Anthropic best practice)
- ✅ Conversation compaction to prevent context overflow
- ✅ Format-aware prompting (XML/JSON per model)
- ✅ Explicit synthesis trigger in RESEARCH mode

**Critical Gaps**:
- ❌ **QUICK_LOOKUP mode lacks optimization** - Uses same expensive patterns as RESEARCH
- ❌ **Inconsistent prompt engineering** - Only RESEARCH gets comprehensive prompts
- ❌ **Missing mode-specific tool policies** - All modes get all tools
- ❌ **Temperature settings not mode-aware** - Same 0.2 for all phases
- ❌ **INGEST mode is underdeveloped** - Minimal guidance and no specialized workflow

---

## Session Mode Definitions

From [session.py:8-14](argo_brain/argo_brain/core/memory/session.py#L8-L14):

```python
class SessionMode(str, Enum):
    QUICK_LOOKUP = "quick_lookup"   # Fast, single-shot queries
    RESEARCH = "research"            # Deep, multi-step research
    INGEST = "ingest"                # Archive and summarize material
```

---

## Mode-by-Mode Analysis

---

## 1. RESEARCH Mode ⭐⭐⭐⭐ (Excellent)

### What It Does

RESEARCH mode implements a sophisticated **planning-first, multi-phase research workflow**:

**Phase 1: Planning** [orchestrator.py:708-723](argo_brain/argo_brain/assistant/orchestrator.py#L708-L723)
- Model creates explicit `<research_plan>` with sub-questions
- Stored in `research_stats["plan_text"]`
- If no tool call in same response, system prompts for tool execution

**Phase 2: Execution** [orchestrator.py:725-813](argo_brain/argo_brain/assistant/orchestrator.py#L725-813)
- Parallel tool execution (Anthropic best practice)
- Conversation compaction after 4+ tool results
- Progress tracking with reflection prompts
- Max 10 tool iterations (configurable)

**Phase 3: Synthesis** [orchestrator.py:850-876](argo_brain/argo_brain/assistant/orchestrator.py#L850-L876)
- Explicit synthesis trigger after tools complete
- Requires `<synthesis>`, `<confidence>`, `<gaps>` tags
- Higher temperature (0.7) for creative synthesis (if implemented)

### Prompt Engineering Quality: **A-**

From [orchestrator.py:201-305](argo_brain/argo_brain/assistant/orchestrator.py#L201-L305), the RESEARCH prompt is **comprehensive**:

✅ **Planning Framework**:
```
First response: Provide ONLY a research plan in <research_plan> tags:
- Research question breakdown
- Search strategy
- Success criteria
- Expected sources
```

✅ **Execution Loop**:
```
For each search iteration:
1. <think>Evaluate last results</think>
2. Output ONLY XML/JSON tool call
3. STOP IMMEDIATELY
4. Wait for results
5. <think>Source quality check</think>
```

✅ **Stopping Conditions** (All must be met):
- Explicit research plan created
- 3+ distinct, authoritative sources fetched
- All sub-questions addressed
- Sources cross-referenced
- Confidence level assessed
- Knowledge gaps acknowledged

✅ **Quality Standards**:
- Citation format with URLs
- Flag contradictions
- Rate source authority
- Prefer recent sources (2023-2025)
- Distinguish facts from opinions

### Best Practices Compliance

| Practice | Status | Implementation |
|----------|--------|----------------|
| **Planning-first architecture** | ✅ Excellent | [orchestrator.py:708-723](argo_brain/argo_brain/assistant/orchestrator.py#L708-L723) |
| **Parallel tool execution** | ✅ Excellent | [orchestrator.py:733-746](argo_brain/argo_brain/assistant/orchestrator.py#L733-L746) |
| **Conversation compaction** | ✅ Good | [orchestrator.py:769-811](argo_brain/argo_brain/assistant/orchestrator.py#L769-L811) |
| **Explicit synthesis trigger** | ✅ Excellent | [orchestrator.py:850-876](argo_brain/argo_brain/assistant/orchestrator.py#L850-L876) |
| **Extended thinking for synthesis** | ⚠️ Partial | Thinking tags used, but no budget_tokens parameter |
| **Dynamic tool availability** | ❌ Missing | All tools available in all phases |
| **Progressive temperature** | ❌ Missing | Same 0.2 throughout, no increase for synthesis |

### Configuration Management: **B+**

**Max Tokens**: 4096 for RESEARCH mode [orchestrator.py:694](argo_brain/argo_brain/assistant/orchestrator.py#L694)
```python
max_tokens = 4096 if active_mode == SessionMode.RESEARCH else None
```
✅ **Good**: Allows long synthesis with citations
⚠️ **Issue**: Hardcoded, not from `ModelPromptConfig.sampling.max_tokens`

**Temperature**: 0.2 for tool calls [orchestrator.py:697](argo_brain/argo_brain/assistant/orchestrator.py#L697)
```python
temperature = 0.2  # Lower than config default of 0.7
```
✅ **Good**: Low temp for deterministic tool selection
❌ **Missing**: No temperature increase for synthesis phase

**Tool Truncation**: [orchestrator.py:507-508](argo_brain/argo_brain/assistant/orchestrator.py#L507-L508)
```python
max_content = 800 if mode == SessionMode.RESEARCH else 1200
max_metadata = 400 if mode == SessionMode.RESEARCH else 800
```
✅ **Good**: More aggressive truncation in RESEARCH mode to save context
✅ **Rationale**: Prevents context overflow during long research sessions

### Conversation Compaction: **A**

From [orchestrator.py:519-604](argo_brain/argo_brain/assistant/orchestrator.py#L519-L604):

```python
COMPACTION_THRESHOLD = 4 if active_mode == SessionMode.RESEARCH else 6
```

✅ **Implementation**: Anthropic's recommended pattern
✅ **Logic**: Groups old results by tool type, provides summary
✅ **Benefits**:
- Prevents context overflow in long sessions
- Keeps 3 most recent results in full
- Compresses old results into concise summary

**Example Output**:
```
## PREVIOUS TOOL EXECUTION SUMMARY
(Compressed 8 tool calls to save context)

**web_search** (3 calls):
  Searched: anthropic best practices, llm agents 2025, tool calling patterns

**web_access** (5 calls):
  Fetched 5 sources:
    - https://www.anthropic.com/research/building-effective-agents
    - https://www.anthropic.com/engineering/writing-tools-for-agents
    ...
```

### Research Progress Tracking: **A-**

From [orchestrator.py:606-649](argo_brain/argo_brain/assistant/orchestrator.py#L606-L649):

✅ **Stopping conditions checklist**
✅ **Search query evolution tracking**
✅ **Reflection prompts based on stage**
✅ **Source count monitoring**

**Example Progress Feedback**:
```
[RESEARCH_PROGRESS: 2 sources fetched, 3 searches, 5 total tools]

STOPPING CONDITIONS CHECKLIST:
✓ Explicit research plan created
✗ 3+ distinct sources (2/3)
✗ All sub-questions addressed (self-assess)

REFLECTION PROMPT:
- Did the last source provide what you needed?
- What information is still missing?
- Need 1 more authoritative sources
- Should you refine your search query based on what you've learned?
```

### Issues and Recommendations

#### Issue #1: No Progressive Temperature ❌ CRITICAL

**Current**: Same temperature (0.2) used for both tool selection and synthesis.

**Problem**: Low temperature makes synthesis less creative and diverse.

**Anthropic Recommendation**:
> "Use lower temperature for tool-calling to get focused, deterministic JSON. Increase temperature after getting tool results for more creative synthesis."

**Fix**: [orchestrator.py:697-705](argo_brain/argo_brain/assistant/orchestrator.py#L697-L705)
```python
# BEFORE
temperature = 0.2  # Lower than config default of 0.7

while True:
    response_text = self.llm_client.chat(
        prompt_messages,
        max_tokens=max_tokens,
        temperature=temperature  # ← Same throughout
    )

# AFTER
# Start with low temp for tool calls
temperature = 0.2 if not research_stats.get("synthesis_triggered") else 0.7

# Or use model-specific settings from ModelPromptConfig
temperature = self.prompt_config.sampling.temperature if research_stats.get("synthesis_triggered") else 0.2
```

#### Issue #2: No Extended Thinking for Synthesis ⚠️ MODERATE

**Current**: Model uses `<think>` tags but no dedicated thinking budget.

**Anthropic Pattern**: Extended thinking with 2000-token budget for complex synthesis.

**Fix**: [orchestrator.py:850-876](argo_brain/argo_brain/assistant/orchestrator.py#L850-L876)
```python
# When triggering synthesis
synthesis_response = self.llm_client.chat(
    prompt_messages + extra_messages,
    max_tokens=4096,
    temperature=0.7,
    thinking={"enabled": True, "budget_tokens": 2000}  # ← ADD THIS
)
```

**Note**: Requires LLMClient to support `thinking` parameter.

#### Issue #3: All Tools Available in All Phases ❌ MODERATE

**Current**: All tools (`web_search`, `web_access`, `memory_query`, `memory_write`, `retrieve_context`) available in planning, execution, and synthesis phases.

**Problem**: Model might call `memory_write` during planning or `web_search` during synthesis.

**Anthropic Recommendation**: "Control which tools are available per phase"

**Fix**: [orchestrator.py:316-320](argo_brain/argo_brain/assistant/orchestrator.py#L316-L320)
```python
def build_prompt(self, context, user_message, session_mode):
    messages = [ChatMessage(role="system", content=self.system_prompt)]

    # Phase-aware tool filtering for RESEARCH mode
    if session_mode == SessionMode.RESEARCH:
        available_tools = self._get_phase_tools(research_stats)
        manifest_text = self.tool_registry.manifest(filter_tools=available_tools)
    else:
        manifest_text = self.tool_registry.manifest()

    if manifest_text and "No external tools" not in manifest_text:
        messages.append(ChatMessage(role="system", content=manifest_text))
    # ...

def _get_phase_tools(self, research_stats: Dict) -> List[str]:
    """Return available tools based on research phase."""
    if not research_stats["has_plan"]:
        # Planning phase: no tools needed
        return []
    elif research_stats["tool_calls"] < 10:
        # Exploration phase: search and access only
        return ["web_search", "web_access", "retrieve_context"]
    else:
        # Synthesis phase: memory tools for storage
        return ["memory_write", "memory_query"]
```

---

## 2. QUICK_LOOKUP Mode ⭐⭐ (Needs Improvement)

### What It Does

QUICK_LOOKUP is the **default mode** [orchestrator.py:65](argo_brain/argo_brain/assistant/orchestrator.py#L65) for fast, single-shot queries.

**Expected behavior**: Answer quickly using available context, minimal tool usage.

### Current Implementation: **C-**

#### Prompt Engineering: **D**

From [orchestrator.py:192-193](argo_brain/argo_brain/assistant/orchestrator.py#L192-L193):
```python
if session_mode == SessionMode.QUICK_LOOKUP:
    return "You are in QUICK LOOKUP mode: answer concisely using available context."
```

❌ **Problem**: **Extremely minimal guidance** - only 10 words
❌ **Missing**: Tool usage guidance, stopping conditions, format examples
❌ **Contrast**: RESEARCH mode has 159 lines of detailed instructions

#### Tool Call Recovery: [orchestrator.py:878-893](argo_brain/argo_brain/assistant/orchestrator.py#L878-L893)

```python
# QUICK_LOOKUP mode: if model responded but didn't make tool call, prompt for it
if active_mode == SessionMode.QUICK_LOOKUP and iterations == 0:
    response_lower = response_text.lower()
    tool_intent_keywords = ["let me", "i'll", "i will", "searching for", "looking for", "finding"]
    has_tool_intent = any(keyword in response_lower for keyword in tool_intent_keywords)

    if has_tool_intent:
        prompt_for_tools = (
            "Please proceed with the tool call now. Output the tool call immediately using the correct format.\n\n"
            "Do NOT explain what you will do - just make the tool call."
        )
        extra_messages.append(ChatMessage(role="system", content=prompt_for_tools))
        continue
```

✅ **Good**: Detects when model says "let me search" but doesn't call tools
⚠️ **Issue**: This is a **band-aid** for poor prompt engineering
⚠️ **Root cause**: Prompt doesn't clearly tell model WHEN and HOW to use tools

### Configuration Gaps

#### No Mode-Specific Settings

**Max Tokens**: `None` (uses model default) [orchestrator.py:694](argo_brain/argo_brain/assistant/orchestrator.py#L694)
```python
max_tokens = 4096 if active_mode == SessionMode.RESEARCH else None
```
⚠️ **Issue**: Should use lower max_tokens for quick responses (e.g., 1024)

**Tool Truncation**: Less aggressive (1200 chars) [orchestrator.py:507](argo_brain/argo_brain/assistant/orchestrator.py#L507)
```python
max_content = 800 if mode == SessionMode.RESEARCH else 1200
```
✅ **Rationale**: More content available for single-pass answers
✅ **Appropriate** for the mode

**Compaction Threshold**: 6 tool results [orchestrator.py:771](argo_brain/argo_brain/assistant/orchestrator.py#L771)
```python
COMPACTION_THRESHOLD = 4 if active_mode == SessionMode.RESEARCH else 6
```
⚠️ **Issue**: QUICK_LOOKUP should rarely need compaction (implies too many tools)

### Critical Issues

#### Issue #1: No Distinct Behavior ❌ CRITICAL

**Problem**: QUICK_LOOKUP uses the exact same loop, tools, and patterns as RESEARCH mode.

**Observation**: The only differences are:
1. Different 10-word prompt
2. Less aggressive tool truncation
3. Higher compaction threshold
4. Tool call recovery prompt

**Expected**:
- **Single-shot tool use** - One search, one answer
- **Prefer context over tools** - Use RAG first, tools only if needed
- **Fast response** - Lower max_tokens, simpler synthesis
- **No multi-phase workflow** - No planning, no synthesis trigger

**Current Reality**: Model can execute 10 tool calls in QUICK_LOOKUP mode (same as RESEARCH).

#### Issue #2: Missing Tool Guidance ❌ CRITICAL

**Current prompt**:
```
You are in QUICK LOOKUP mode: answer concisely using available context.
```

**What's missing**:
- ❌ When to use tools vs. context
- ❌ Maximum tool calls allowed (should be 1-2)
- ❌ How to format tool calls
- ❌ What constitutes a "quick" answer

**Recommended Prompt**:
```python
def _get_mode_description(self, session_mode: SessionMode) -> str:
    if session_mode == SessionMode.QUICK_LOOKUP:
        tool_format = "XML" if self.use_xml_format else "JSON"
        tool_example = self.prompt_config.tool_calling.get_example()

        return f"""You are in QUICK LOOKUP mode: provide fast, concise answers.

PRIORITY ORDER:
1. **Check context first** - If the answer is in the provided context, use it
2. **Single tool call** - Only use ONE tool if context is insufficient
3. **Direct answer** - Provide answer immediately after tool result (no synthesis phase)

TOOL USAGE (if needed):
- Maximum: 1 tool call per query
- Format: {tool_format}
- Example: {tool_example}

OUTPUT FORMAT:
- Concise answers (2-3 sentences preferred)
- Cite sources when available
- No elaborate analysis unless specifically requested

AVOID:
- Multiple tool calls
- Long research processes
- Asking follow-up questions (just answer with what you have)
"""
```

### Recommendations

#### Fix #1: Implement Quick-Lookup-Specific Loop

```python
def send_message(self, session_id, user_message, **kwargs):
    active_mode = session_mode or self.default_session_mode

    if active_mode == SessionMode.QUICK_LOOKUP:
        return self._send_message_quick_lookup(session_id, user_message, **kwargs)
    elif active_mode == SessionMode.RESEARCH:
        return self._send_message_research(session_id, user_message, **kwargs)
    # ...

def _send_message_quick_lookup(self, session_id, user_message, **kwargs):
    """Optimized loop for quick lookups."""
    context = self.memory_manager.get_context_for_prompt(session_id, user_message)
    prompt_messages = self.build_prompt(context, user_message, SessionMode.QUICK_LOOKUP)

    # First call - try to answer from context
    response_text = self.llm_client.chat(
        prompt_messages,
        max_tokens=1024,  # Shorter than RESEARCH
        temperature=0.3    # Slightly higher than tool-calling, lower than synthesis
    )

    # Check if tool call needed
    plan_payload = self._maybe_parse_plan(response_text)
    if plan_payload:
        # Execute ONLY first tool (ignore others)
        proposal = plan_payload["proposals"][0]
        result = self._execute_single_tool(proposal, session_id, user_message, SessionMode.QUICK_LOOKUP)

        # Add result and re-prompt for answer
        extra_messages.append(ChatMessage(role="system", content=self._format_tool_result_for_prompt(result)))
        response_text = self.llm_client.chat(
            prompt_messages + extra_messages,
            max_tokens=1024,
            temperature=0.5  # Higher for more natural final answer
        )

    # Return answer (no synthesis trigger, no multi-phase workflow)
    return AssistantResponse(text=response_text, context=context)
```

#### Fix #2: Lower MAX_TOOL_CALLS for QUICK_LOOKUP

```python
# In send_message()
MAX_ITERATIONS = 1 if active_mode == SessionMode.QUICK_LOOKUP else self.MAX_TOOL_CALLS
```

---

## 3. INGEST Mode ⭐ (Underdeveloped)

### What It Does

INGEST mode is for **archiving and summarizing material** [session.py:13](argo_brain/argo_brain/core/memory/session.py#L13).

**Expected Use Cases**:
- Ingesting articles for later retrieval
- Summarizing documents
- Building knowledge base from provided material

### Current Implementation: **D**

#### Prompt Engineering: **F**

From [orchestrator.py:195-196](argo_brain/argo_brain/assistant/orchestrator.py#L195-L196):
```python
if session_mode == SessionMode.INGEST:
    return "You are in INGEST mode: help archive and summarize supplied material."
```

❌ **Critical**: Only **11 words** of guidance
❌ **Missing**: What tools to use (`memory_write`), output format, summarization guidelines

### No Specialized Workflow

**Current**: Uses the same generic loop as QUICK_LOOKUP and RESEARCH.

**Expected**:
1. Extract key information from user-provided material
2. Generate concise summary
3. Call `memory_write` to store
4. Confirm ingestion

**Actual**: No specialized behavior at all.

### Recommendations

#### Recommended Prompt

```python
if session_mode == SessionMode.INGEST:
    return """You are in INGEST mode: archive and summarize user-provided material.

WORKFLOW:
1. **Read** the provided material carefully
2. **Extract** key information:
   - Main topic/subject
   - Key facts and findings
   - Important URLs, dates, names
   - Relevant quotes
3. **Summarize** in structured format:
   - Title/Topic (one line)
   - Summary (2-3 paragraphs)
   - Key Points (bullet list)
   - Tags (keywords for future retrieval)
4. **Store** using memory_write tool with:
   - content: Your structured summary (markdown format)
   - metadata: {tags: [...], source: URL, ingested_at: timestamp}

OUTPUT FORMAT:
<summary>
# [Topic]

## Summary
[2-3 paragraph overview]

## Key Points
- Point 1
- Point 2
...

## Tags
`tag1`, `tag2`, `tag3`
</summary>

Then call memory_write to store this summary.
"""
```

#### Specialized Workflow

```python
def _send_message_ingest(self, session_id, user_message, **kwargs):
    """Specialized loop for ingestion tasks."""
    # Step 1: Generate summary
    context = self.memory_manager.get_context_for_prompt(session_id, user_message)
    prompt_messages = self.build_prompt(context, user_message, SessionMode.INGEST)

    summary_response = self.llm_client.chat(
        prompt_messages,
        max_tokens=2048,
        temperature=0.5  # Moderate - structured but readable
    )

    # Step 2: Auto-call memory_write with summary
    result = self.run_tool(
        "memory_write",
        session_id,
        query=summary_response,  # The summary itself
        metadata={"source": "ingest_mode", "timestamp": datetime.now().isoformat()},
        session_mode=SessionMode.INGEST
    )

    # Step 3: Confirm storage
    confirmation = f"✓ Material ingested and stored.\n\n{summary_response}"

    return AssistantResponse(
        text=confirmation,
        context=context,
        tool_results=[result]
    )
```

---

## Cross-Mode Comparison

### Tool Result Formatting

From [orchestrator.py:505-516](argo_brain/argo_brain/assistant/orchestrator.py#L505-L516):

```python
def _format_tool_result_for_prompt(self, result: ToolResult, mode: SessionMode) -> str:
    # More aggressive truncation in research mode to save context
    max_content = 800 if mode == SessionMode.RESEARCH else 1200
    max_metadata = 400 if mode == SessionMode.RESEARCH else 800

    metadata_preview = json.dumps(result.metadata, ensure_ascii=False)[:max_metadata]
    content_preview = (result.content or "")[:max_content]
    return (
        f"Tool {result.tool_name} result summary: {result.summary}\n"
        f"Content:\n{content_preview}\n"
        f"Metadata: {metadata_preview}"
    )
```

| Mode | Max Content | Max Metadata | Rationale |
|------|-------------|--------------|-----------|
| RESEARCH | 800 chars | 400 chars | Aggressive truncation (many tools expected) |
| QUICK_LOOKUP | 1200 chars | 800 chars | More detail (fewer tools expected) |
| INGEST | 1200 chars | 800 chars | Same as QUICK_LOOKUP |

✅ **Good**: Mode-aware truncation prevents context overflow
⚠️ **Issue**: INGEST should probably have **NO truncation** (needs full content to summarize)

### Conversation Compaction Thresholds

From [orchestrator.py:771](argo_brain/argo_brain/assistant/orchestrator.py#L771):

```python
COMPACTION_THRESHOLD = 4 if active_mode == SessionMode.RESEARCH else 6
```

| Mode | Threshold | Rationale |
|------|-----------|-----------|
| RESEARCH | 4 results | Aggressive (expects many tool calls) |
| QUICK_LOOKUP | 6 results | Less aggressive (shouldn't need this many) |
| INGEST | 6 results | Same as QUICK_LOOKUP |

✅ **Good**: RESEARCH gets more aggressive compaction
⚠️ **Issue**: If QUICK_LOOKUP reaches 6 tool calls, something is wrong with the prompt

---

## Logical Gaps and Inconsistencies

### Gap #1: Asymmetric Optimization ❌ CRITICAL

**Observation**: Anthropic best practices (parallel execution, compaction, response formats) are applied **globally** to all modes, but **prompt engineering** is only comprehensive for RESEARCH mode.

**Problem**: QUICK_LOOKUP and INGEST don't benefit from the same level of prompt refinement.

**Impact**:
- QUICK_LOOKUP doesn't clearly tell model to prefer context over tools
- INGEST doesn't specify expected workflow and output format
- Both modes rely on implicit behavior instead of explicit instructions

**Recommendation**: Apply same level of prompt engineering rigor to all modes.

---

### Gap #2: No Mode-Specific Tool Policies ❌ MODERATE

**Current**: `ToolPolicy` (from [orchestrator.py:23](argo_brain/argo_brain/assistant/orchestrator.py#L23)) applies the same rules to all modes.

**Issue**: Different modes should have different tool access patterns:

| Mode | Appropriate Tools | Inappropriate Tools |
|------|-------------------|---------------------|
| QUICK_LOOKUP | `web_search`, `memory_query`, `retrieve_context` | `memory_write` (no storage in quick mode) |
| RESEARCH | All tools | None (needs full toolkit) |
| INGEST | `web_access`, `memory_write` | `web_search` (user provides material) |

**Current Reality**: All tools available in all modes.

**Recommendation**: Implement mode-aware tool filtering:
```python
def review(self, proposals, tool_registry, session_mode: SessionMode) -> tuple:
    """Review tool proposals with mode-specific policies."""
    # ... existing approval logic ...

    # Mode-specific filtering
    if session_mode == SessionMode.QUICK_LOOKUP:
        # Reject memory_write in quick lookup
        for proposal in approved[:]:
            if proposal.tool == "memory_write":
                rejections.append({
                    "tool": proposal.tool,
                    "reason": "memory_write not allowed in QUICK_LOOKUP mode"
                })
                approved.remove(proposal)

    # ... return approved, rejections
```

---

### Gap #3: Missing Mode-Specific Temperature Schedules ❌ MODERATE

**Current**: Single temperature (0.2) for entire session, regardless of mode or phase.

**Best Practice** (from Anthropic research):
- **Tool selection**: Low temp (0.1-0.2) for deterministic JSON/XML
- **Quick answers**: Moderate temp (0.3-0.5) for natural responses
- **Creative synthesis**: Higher temp (0.7-0.9) for diverse ideas

**Recommended Schedule**:

| Mode | Phase | Temperature | Rationale |
|------|-------|-------------|-----------|
| QUICK_LOOKUP | Initial | 0.3 | Try to answer from context |
| QUICK_LOOKUP | Tool call | 0.2 | Deterministic tool selection |
| QUICK_LOOKUP | Final answer | 0.5 | Natural, readable response |
| RESEARCH | Planning | 0.4 | Structured but creative plan |
| RESEARCH | Tool calls | 0.2 | Deterministic, focused |
| RESEARCH | Synthesis | 0.7 | Creative, comprehensive |
| INGEST | Summary | 0.5 | Structured but readable |

**Implementation**:
```python
def _get_temperature_for_phase(self, mode: SessionMode, phase: str) -> float:
    """Return appropriate temperature for mode and phase."""
    schedules = {
        SessionMode.QUICK_LOOKUP: {"initial": 0.3, "tool": 0.2, "answer": 0.5},
        SessionMode.RESEARCH: {"planning": 0.4, "tool": 0.2, "synthesis": 0.7},
        SessionMode.INGEST: {"summary": 0.5, "tool": 0.2},
    }
    return schedules.get(mode, {}).get(phase, 0.5)
```

---

### Gap #4: No Mode-Specific Max Tokens ⚠️ MINOR

**Current**:
```python
max_tokens = 4096 if active_mode == SessionMode.RESEARCH else None
```

**Issue**: `None` uses model default (often 16K+), wasteful for QUICK_LOOKUP.

**Recommended**:
```python
max_tokens_by_mode = {
    SessionMode.QUICK_LOOKUP: 1024,   # Short, concise answers
    SessionMode.RESEARCH: 4096,        # Long synthesis with citations
    SessionMode.INGEST: 2048,          # Structured summaries
}
max_tokens = max_tokens_by_mode.get(active_mode, 2048)
```

---

### Gap #5: Parallel Execution Benefit Not Clear for QUICK_LOOKUP ⚠️ MINOR

**Current**: Parallel execution works for all modes [orchestrator.py:733-746](argo_brain/argo_brain/assistant/orchestrator.py#L733-L746).

**Issue**: QUICK_LOOKUP should ideally make **0-1 tool calls**, so parallel execution is rarely beneficial.

**Observation**: If QUICK_LOOKUP is calling multiple tools in parallel, the prompt is failing to enforce "single-shot" behavior.

**Recommendation**: Log a warning if QUICK_LOOKUP uses >1 tool:
```python
if active_mode == SessionMode.QUICK_LOOKUP and len(approved) > 1:
    self.logger.warning(
        f"QUICK_LOOKUP mode using {len(approved)} tools - prompt may need improvement",
        extra={"session_id": session_id, "tools": [p.tool for p in approved]}
    )
```

---

## Industry Best Practices Compliance

### ✅ What We're Doing Well

1. **Planning-First Architecture** (RESEARCH mode)
   - Anthropic: "Have the model plan first, then execute"
   - Implementation: [orchestrator.py:708-723](argo_brain/argo_brain/assistant/orchestrator.py#L708-L723)
   - Grade: **A**

2. **Parallel Tool Execution**
   - Anthropic: "3+ parallel tool calls reduce research time by 90%"
   - Implementation: [orchestrator.py:733-746](argo_brain/argo_brain/assistant/orchestrator.py#L733-L746)
   - Grade: **A**

3. **Conversation Compaction**
   - Anthropic: "Summarize history to prevent context rot"
   - Implementation: [orchestrator.py:519-604](argo_brain/argo_brain/assistant/orchestrator.py#L519-L604)
   - Grade: **A-** (works well, but could use mode-specific thresholds)

4. **Explicit Synthesis Trigger**
   - Anthropic: "Coordinate phases with explicit prompts"
   - Implementation: [orchestrator.py:850-876](argo_brain/argo_brain/assistant/orchestrator.py#L850-L876)
   - Grade: **A**

5. **Format-Aware Prompting**
   - Anthropic: "Match model's native format"
   - Implementation: [orchestrator.py:95-115](argo_brain/argo_brain/assistant/orchestrator.py#L95-L115)
   - Grade: **A**

6. **Tool Description Quality**
   - Anthropic: "Describe tools as you would to a new team member"
   - Status: Implemented in Phase 1 (per [ANTHROPIC_BEST_PRACTICES_IMPLEMENTATION.md](docs/ANTHROPIC_BEST_PRACTICES_IMPLEMENTATION.md))
   - Grade: **A-** (assuming implementation matches doc)

### ❌ What We're Missing

1. **Dynamic Tool Availability**
   - Anthropic: "Control which tools are available per phase"
   - Status: Not implemented
   - Impact: Model can call inappropriate tools (e.g., memory_write during planning)
   - Grade: **F**

2. **Extended Thinking for Synthesis**
   - Anthropic: "Use Claude's extended thinking for higher quality synthesis"
   - Status: Thinking tags used, but no budget_tokens parameter
   - Impact: Synthesis quality not optimized
   - Grade: **C**

3. **Progressive Temperature**
   - Anthropic: "Low temp for tools, higher for creative synthesis"
   - Status: Single temperature throughout
   - Impact: Synthesis less creative, tool calls less deterministic
   - Grade: **D**

4. **Mode-Specific Workflows**
   - Best Practice: Each mode should have optimized loop
   - Status: Generic loop for all modes
   - Impact: QUICK_LOOKUP slow, INGEST underdeveloped
   - Grade: **D**

5. **Just-In-Time Context Retrieval**
   - Anthropic: "Return identifiers, retrieve full content on demand"
   - Status: `retrieve_context` tool exists (Phase 2 per docs), but not used by default
   - Impact: Context loading still eager, not lazy
   - Grade: **C** (implemented but not default)

---

## Model Prompts Integration

From [model_prompts.py](argo_brain/argo_brain/model_prompts.py), the system supports **per-model prompt configuration** via YAML files.

### Current Usage: **Partial**

✅ **What's Used**:
- `tool_calling.format` (XML vs JSON) [orchestrator.py:99](argo_brain/argo_brain/assistant/orchestrator.py#L99)
- `thinking.enabled` [orchestrator.py:105](argo_brain/argo_brain/assistant/orchestrator.py#L105)
- `build_system_prompt()` [orchestrator.py:143](argo_brain/argo_brain/assistant/orchestrator.py#L143)

❌ **What's NOT Used**:
- `sampling.temperature` (hardcoded 0.2 instead)
- `sampling.max_tokens` (hardcoded 4096 for RESEARCH)
- `modes` configuration (mode-specific prompts from YAML)
- `stop_sequences` (not passed to LLMClient)

### Recommendation: Full ModelPromptConfig Integration

```python
# In send_message()
# Use model-specific sampling config
temperature = self.prompt_config.sampling.temperature if synthesis_phase else 0.2
max_tokens = self.prompt_config.sampling.max_tokens

# Use mode-specific prompts from config
mode_prompt = self.prompt_config.get_mode_prompt(session_mode.value)

# Use stop sequences from config
response_text = self.llm_client.chat(
    prompt_messages,
    max_tokens=max_tokens,
    temperature=temperature,
    stop=self.prompt_config.tool_calling.stop_sequences  # ← ADD
)
```

---

## Summary of Recommendations

### Priority 1: Critical Fixes (Immediate)

1. **Develop QUICK_LOOKUP Mode Prompt** [orchestrator.py:192-193](argo_brain/argo_brain/assistant/orchestrator.py#L192-L193)
   - Current: 10 words
   - Target: 50-80 lines with tool guidance, stopping conditions
   - Impact: Massive improvement in speed and accuracy

2. **Implement Progressive Temperature** [orchestrator.py:697](argo_brain/argo_brain/assistant/orchestrator.py#L697)
   - Tool calls: 0.2
   - QUICK_LOOKUP answers: 0.5
   - RESEARCH synthesis: 0.7
   - Impact: Better tool selection + creative synthesis

3. **Add Mode-Specific Max Tokens**
   - QUICK_LOOKUP: 1024
   - RESEARCH: 4096
   - INGEST: 2048
   - Impact: Faster responses, lower costs

### Priority 2: Important Improvements (Short-term)

4. **Develop INGEST Mode Workflow** [orchestrator.py:195-196](argo_brain/argo_brain/assistant/orchestrator.py#L195-L196)
   - Structured summarization prompt
   - Auto-call memory_write
   - Confirmation message
   - Impact: Actually useful ingestion mode

5. **Implement Dynamic Tool Availability**
   - Phase-aware tool filtering for RESEARCH
   - Mode-aware tool policies
   - Impact: Prevent inappropriate tool usage

6. **Add Extended Thinking for Synthesis**
   - Requires LLMClient support for `thinking` parameter
   - Budget: 2000 tokens
   - Impact: Higher quality synthesis

### Priority 3: Polish (Medium-term)

7. **Full ModelPromptConfig Integration**
   - Use `sampling` settings from model config
   - Use `stop_sequences` from model config
   - Use `modes` prompts from YAML
   - Impact: Better per-model optimization

8. **Implement QUICK_LOOKUP-Specific Loop**
   - Separate method `_send_message_quick_lookup()`
   - Max 1 tool call
   - No multi-phase workflow
   - Impact: Clearer code, enforced behavior

9. **Add Mode Transition Detection**
   - Log when QUICK_LOOKUP uses >2 tools (should switch to RESEARCH)
   - Auto-suggest mode switch to user
   - Impact: Better user experience

---

## Conclusion

### Overall Grade: **B+**

The Argo Brain session mode architecture demonstrates **excellent implementation of Anthropic best practices for RESEARCH mode**, with sophisticated planning-first workflow, parallel execution, and conversation compaction.

However, **QUICK_LOOKUP and INGEST modes are significantly underdeveloped**, relying on minimal prompts and the same generic loop as RESEARCH. This creates an **asymmetric optimization** where cutting-edge patterns are applied to tools and infrastructure, but prompt engineering is only comprehensive for one mode.

### Key Strengths

1. ✅ **RESEARCH mode is industry-leading** - Comprehensive prompts, multi-phase workflow, quality standards
2. ✅ **Infrastructure is excellent** - Parallel execution, compaction, format awareness
3. ✅ **Best practices adoption** - Following Anthropic's 2024-2025 recommendations closely

### Critical Weaknesses

1. ❌ **QUICK_LOOKUP mode is a misnomer** - Can execute 10 tools, no speed optimization
2. ❌ **INGEST mode is a placeholder** - 11 words of guidance, no workflow
3. ❌ **No progressive temperature** - Same 0.2 throughout, missing creative synthesis
4. ❌ **No dynamic tool availability** - All tools in all phases/modes

### Recommended Action Plan

**Week 1**: Fix QUICK_LOOKUP prompt (Priority 1, item 1)
**Week 1**: Implement progressive temperature (Priority 1, item 2)
**Week 2**: Add mode-specific max_tokens (Priority 1, item 3)
**Week 2**: Develop INGEST workflow (Priority 2, item 4)
**Week 3**: Implement dynamic tool availability (Priority 2, item 5)
**Week 4**: Add extended thinking for synthesis (Priority 2, item 6)

Expected improvement: **30-50% faster QUICK_LOOKUP**, **usable INGEST mode**, **15-25% better RESEARCH synthesis quality**.

---

## Appendix: Mode Comparison Matrix

| Aspect | QUICK_LOOKUP | RESEARCH | INGEST |
|--------|--------------|----------|--------|
| **Prompt Length** | 10 words ❌ | 159 lines ✅ | 11 words ❌ |
| **Tool Call Limit** | 10 (same as RESEARCH) ❌ | 10 ✅ | 10 (unused) ⚠️ |
| **Max Tokens** | None (uses default) ⚠️ | 4096 ✅ | None (should be 2048) ⚠️ |
| **Temperature** | 0.2 (too low) ❌ | 0.2 (should be 0.7 for synthesis) ⚠️ | 0.2 (should be 0.5) ⚠️ |
| **Tool Truncation** | 1200 chars ✅ | 800 chars ✅ | 1200 chars (should be none) ⚠️ |
| **Compaction Threshold** | 6 results ⚠️ | 4 results ✅ | 6 results ⚠️ |
| **Multi-Phase Workflow** | No (good) ✅ | Yes (excellent) ✅ | No (should have custom workflow) ❌ |
| **Synthesis Trigger** | No (appropriate) ✅ | Yes (excellent) ✅ | No (should confirm storage) ❌ |
| **Tool Call Recovery** | Yes (band-aid) ⚠️ | No (not needed) ✅ | No (not implemented) ❌ |
| **Quality Rating** | ⭐⭐ (Needs Work) | ⭐⭐⭐⭐ (Excellent) | ⭐ (Underdeveloped) |

---

**Document Version**: 1.0
**Last Updated**: December 2, 2025
**Next Review**: After implementing Priority 1 fixes
