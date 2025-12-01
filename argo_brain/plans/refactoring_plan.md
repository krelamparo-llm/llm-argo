# Argo Brain Refactoring Plan

**Date**: 2025-11-30
**Status**: Implemented

## Context

This plan addresses inconsistencies and deficiencies found during architectural critique of Argo Brain against the requirements in `main.txt`.

## Key Decisions (From Karl)

1. **Observation-first model** - Argo should passively observe, not just respond to queries
2. **Namespaces = content types** - Not trust levels
3. **Full-chunk storage** - Browser history stored as full chunks, not summarized
4. **Loose retention** - Plenty of storage, use decay scoring instead of hard deletes
5. **Deep research is near-term goal** - Web search + multi-step research loop

## Implementation Components

### P0 - Critical Simplifications

#### A. Simplify Ingestion Layer
- Remove `IngestionPolicy` enum (EPHEMERAL/SUMMARY_ONLY/FULL)
- Replace with simple `ephemeral: bool` flag
- Remove 7-step policy decision tree
- Move summarization to separate concern (future)
- Result: 40% code reduction, clearer logic

#### B. Refactor MemoryManager
- Extract `SessionManager` - conversation lifecycle + summarization
- Extract `ToolTracker` - tool audit log + web caching
- Keep `MemoryManager` focused on memory extraction only
- Result: Single Responsibility Principle, easier testing

#### G. Update Namespace Configuration
- Rename to match main.txt: `reading_history`, `youtube_history`, `notes_journal`
- Add `RetentionPolicy` dataclass with TTL + decay settings
- Add backward-compatibility aliases
- Result: Consistent naming, clear retention rules

### P1 - Deep Research Feature

#### E. Web Search Tool
- Implement `WebSearchTool` with DuckDuckGo backend
- Support SearXNG as alternative
- Register in orchestrator
- Increase MAX_TOOL_CALLS from 3 to 10
- Result: LLM can autonomously search the web

#### F. Retention & Decay System
- Implement decay scoring: `score *= 0.5^(age / half_life)`
- Implement TTL filtering for ephemeral content
- Create cleanup script for expired web_cache
- Integrate into `retrieve_knowledge()`
- Result: Old content deprioritized, web cache auto-expires

### P2 - Future Work (Not in this refactor)

#### C. YouTube Ingestion Daemon
- Status: Keep as Planned
- Will tackle separately after deep research

#### D. Browser History Ingestion Daemon
- Status: Keep as Planned
- Independent of deep research

## Architecture After Refactoring

```
┌─────────────────────────────────────────────────────────┐
│                    ArgoAssistant                        │
│  (orchestrates conversation, tools, memory)             │
└─────────────┬──────────────┬──────────────┬─────────────┘
              │              │              │
     ┌────────▼───────┐ ┌────▼────┐ ┌──────▼──────┐
     │ SessionManager │ │ToolTrack│ │MemoryManager│
     │ - history      │ │- audit  │ │- extraction │
     │ - summaries    │ │- caching│ │- queries    │
     └────────────────┘ └─────────┘ └─────────────┘
              │              │              │
              └──────────────┴──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │      IngestionManager       │
              │  - chunking                 │
              │  - namespace routing        │
              │  - ephemeral vs archival    │
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │         VectorStore         │
              │  - reading_history          │
              │  - youtube_history          │
              │  - notes_journal            │
              │  - autobiographical_memory  │
              │  - web_cache (TTL: 7 days)  │
              └─────────────────────────────┘
```

## Files Created

- `argo_brain/memory/session_manager.py`
- `argo_brain/memory/tool_tracker.py`
- `argo_brain/tools/search.py`
- `argo_brain/core/memory/decay.py`
- `scripts/cleanup_expired.py`

## Files Modified

- `argo_brain/core/memory/ingestion.py` - Simplified
- `argo_brain/memory/manager.py` - Refactored
- `argo_brain/config.py` - New namespaces + retention
- `argo_brain/runtime.py` - New components
- `argo_brain/rag.py` - Decay integration
- `argo_brain/tools/web.py` - Simplified ingestion call

## Remaining Work

- Wire orchestrator to use new components
- Update entry point scripts
- Update tests for new API
