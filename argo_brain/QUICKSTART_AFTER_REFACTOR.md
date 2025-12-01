# Quick Start After Refactoring

**TL;DR**: Core refactoring is done. You need to wire the orchestrator and test. This guide gets you running in 10 minutes.

---

## Step 1: Install Dependencies (2 min)

```bash
cd /home/krela/llm-argo/argo_brain

# Activate your venv if you have one
source ../llm-wsl/bin/activate  # Or your venv path

# Install new dependency
pip install duckduckgo-search
```

---

## Step 2: Wire the Orchestrator (5 min)

**File**: `argo_brain/assistant/orchestrator.py`

### 2a. Add imports (line ~6):
```python
from ..memory.session_manager import SessionManager
from ..memory.tool_tracker import ToolTracker
```

### 2b. Update `__init__` (line ~48):
```python
def __init__(
    self,
    *,
    llm_client: Optional[LLMClient] = None,
    memory_manager: Optional[MemoryManager] = None,
    session_manager: Optional[SessionManager] = None,  # ADD
    tool_tracker: Optional[ToolTracker] = None,        # ADD
    system_prompt: Optional[str] = None,
    tools: Optional[List[Tool]] = None,
    tool_registry: Optional[ToolRegistry] = None,
    default_session_mode: SessionMode = SessionMode.QUICK_LOOKUP,
    ingestion_manager: Optional[IngestionManager] = None,
    tool_policy: Optional[ToolPolicy] = None,
) -> None:
    self.llm_client = llm_client or LLMClient()
    self.memory_manager = memory_manager or MemoryManager(llm_client=self.llm_client)
    self.session_manager = session_manager or SessionManager()  # ADD
    self.tool_tracker = tool_tracker or ToolTracker()            # ADD
    # ... rest stays the same
```

### 2c. Update `send_message()` (line ~213):
```python
# Change line ~213:
self.session_manager.ensure_session(session_id)  # Was: self.memory_manager.ensure_session

# After line ~319 (after tool loop, before return):
thought, final_text = self._split_think(response_text)

# REPLACE the old record_interaction call with:
self.session_manager.record_turn(session_id, user_message, final_text)
recent_turns = self.session_manager.get_recent_messages(session_id, limit=4)
self.memory_manager.extract_and_store_memories(session_id, recent_turns)

for result in tool_results_accum:
    request = ToolRequest(
        tool_name=result.tool_name,
        query=user_message,
        session_id=session_id,
        metadata=result.metadata or {},
    )
    self.tool_tracker.process_result(session_id, request, result)
```

### 2d. Register WebSearchTool (line ~69):
```python
from ..tools.search import WebSearchTool

# In __init__, where tools are defined:
if tools is None:
    tools = [
        WebSearchTool(),              # ADD
        WebAccessTool(ingestion_manager=self.ingestion_manager),
        MemoryQueryTool(memory_manager=self.memory_manager),
        MemoryWriteTool(ingestion_manager=self.ingestion_manager),
    ]
```

### 2e. Increase tool call limit (line ~46):
```python
MAX_TOOL_CALLS = 10  # Was 3, increase for deep research
```

---

## Step 3: Update Entry Point Script (2 min)

**Find your chat script** (probably `scripts/chat.py` or similar)

**Change** this:
```python
runtime = create_runtime()
assistant = ArgoAssistant(
    llm_client=runtime.llm_client,
    memory_manager=runtime.memory_manager,
)
```

**To** this:
```python
runtime = create_runtime()
assistant = ArgoAssistant(
    llm_client=runtime.llm_client,
    memory_manager=runtime.memory_manager,
    session_manager=runtime.session_manager,  # ADD
    tool_tracker=runtime.tool_tracker,        # ADD
)
```

---

## Step 4: Test Basic Functionality (1 min)

```bash
# Start llama-server if not running
# (in another terminal)
llama-server -m /path/to/your/model.gguf -ngl 999

# Test the chat
python scripts/chat.py
```

**Try these commands:**
```
> Hello Argo
> Search for "RAG memory decay best practices"
> What did you find?
```

**Expected**:
- Search should work (fetches results from DuckDuckGo)
- Conversation should persist between messages
- Memory extraction should still work

---

## Step 5: Setup Cleanup Cron

**Linux/WSL:**
```bash
crontab -e

# Add this line:
0 3 * * * cd /home/krela/llm-argo/argo_brain && python scripts/cleanup_expired.py >> /tmp/argo_cleanup.log 2>&1
```

**Windows Task Scheduler:**
```powershell
schtasks /create /tn "ArgoCleanup" /tr "wsl python /home/krela/llm-argo/argo_brain/scripts/cleanup_expired.py" /sc daily /st 03:00
```

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'duckduckgo_search'"
```bash
pip install duckduckgo-search
```

### "AttributeError: 'MemoryManager' object has no attribute 'record_interaction'"
You forgot to update `send_message()` to use `session_manager.record_turn()` instead.

### "TypeError: __init__() got an unexpected keyword argument 'session_manager'"
You forgot to add `session_manager` and `tool_tracker` to orchestrator `__init__`.

### Web search returns empty results
- Check internet connection
- DuckDuckGo may rate-limit, wait a minute and try again
- Try SearXNG backend if you have it set up

### Tests failing
Expected! Update `tests/test_ingestion.py`:
```python
# OLD:
manager.ingest_document(doc, session_mode=SessionMode.INGEST, policy_override=IngestionPolicy.FULL)

# NEW:
manager.ingest_document(doc, ephemeral=False)
```

---

## Verification Checklist

- [ ] `pip install duckduckgo-search` succeeded
- [ ] Orchestrator updated with SessionManager/ToolTracker
- [ ] Entry point script updated to pass new components
- [ ] Chat starts without errors
- [ ] Search tool returns results
- [ ] Conversation persists between messages
- [ ] Cleanup cron job scheduled (optional but recommended)

---

## What Changed (Summary)

1. **Ingestion simpler**: Just `ephemeral=bool` instead of complex policies
2. **SessionManager**: Handles conversation history + summarization
3. **ToolTracker**: Logs tool runs + caches web results
4. **MemoryManager**: Only does memory extraction now
5. **WebSearchTool**: New tool for deep research
6. **Decay scoring**: Older content scores lower in retrieval
7. **Namespaces**: Renamed to match main.txt
8. **TTL cleanup**: Auto-expires web cache after 7 days

---

## Next Steps After Testing

1. **Fix unit tests** - Update for new API
2. **Try deep research** - Ask: "Research retention policies for RAG systems and summarize the top 3 approaches"
3. **Monitor logs** - Check that memory extraction still works
4. **Experiment with decay** - Query old content and see decay scoring in action

---

## Getting Help

- Check [REFACTORING_COMPLETE.md](REFACTORING_COMPLETE.md) for full details
- Check [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for technical notes
- Review conversation history for architectural decisions

---

**Time to completion**: ~10 minutes if you follow steps sequentially

**Status**: You're ready to wire and test! 🚀
