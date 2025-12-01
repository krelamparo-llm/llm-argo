# Research Mode: Best-in-Class Deep Research

Argo's research mode implements state-of-the-art patterns for thorough, methodical multi-step research based on findings from 40+ academic papers and industry best practices.

## Overview

Research mode (`--mode research`) transforms Argo from a simple Q&A assistant into a systematic research agent that:

- **Plans** before executing
- **Evaluates** results at each step
- **Refines** queries based on findings
- **Synthesizes** across multiple sources
- **Assesses** confidence and acknowledges gaps

## Quick Start

```bash
python scripts/chat_cli.py --mode research --session myresearch1
```

Then ask a research question:
```
You> What are the best practices for RAG retention policies in 2024?
```

## Three-Phase Research Framework

### Phase 1: Planning (Mandatory)

Before any tool execution, the LLM must provide a structured research plan:

```xml
<research_plan>
Research question breakdown:
- What are the main retention strategies for vector databases?
- How do major systems (Pinecone, Weaviate, ChromaDB) handle TTL?
- What are the trade-offs between automatic cleanup vs manual curation?

Search strategy:
- "RAG retention policies 2024"
- "vector database TTL best practices"
- "chromadb automatic cleanup"

Success criteria:
- Found specific TTL configurations from 3+ authoritative sources
- Identified pros/cons of different strategies
- Got recent benchmarks or case studies (2023-2025)

Expected sources:
- Technical blog posts from vector DB vendors
- Academic papers on information retrieval
- Production engineering case studies
</research_plan>
```

**Key elements:**
- Sub-questions that must be answered
- Specific search keywords/phrases
- Concrete success criteria
- Expected source types

### Phase 2: Execution (Iterative)

After each tool call, the LLM receives reflection prompts:

**After 0 sources:**
```
NEXT: Execute your search strategy from the plan
```

**After 1-2 sources:**
```
REFLECTION PROMPT:
- Did the last source provide what you needed?
- What information is still missing?
- Need 2 more authoritative sources
- Should you refine your search query based on what you've learned?
```

**Search query evolution:**
```
SEARCH QUERIES USED:
  1. "RAG retention policies"
  2. "vector database TTL best practices"  ← refined
  3. "chromadb automatic cleanup strategies"  ← more specific
```

**Source quality checks:**
```xml
<think>
Source quality check:
- Pinecone blog post (authoritative: industry vendor)
- Published: December 2024 (recent)
- Primary source (first-hand implementation details)
- VERDICT: High quality, use as primary reference
</think>
```

### Phase 3: Synthesis (Mandatory)

After gathering 3+ sources, the LLM must synthesize findings:

```xml
<synthesis>
Based on 5 authoritative sources, here are the best practices for RAG retention policies in 2024:

1. **Time-based expiration (TTL)**
   According to [Pinecone's 2024 guide](https://pinecone.io/...), TTL-based cleanup is the most common approach...

2. **Score-based retention**
   [ChromaDB documentation](https://docs.trychroma.com/...) recommends keeping items above a relevance threshold...

3. **Contradictions identified:**
   Source A recommends 7-day TTL for web cache, but Source B suggests 30 days.
   Resolution: 7 days appears more appropriate for high-velocity content based on...
</synthesis>

<confidence>Medium</confidence>

<gaps>
- Unable to find recent benchmarks comparing ChromaDB vs Pinecone cleanup performance
- Conflicting information on optimal chunk size (300-800 tokens)
- No case studies from production systems with >100M vectors
</gaps>
```

## Stopping Conditions

Research continues until ALL conditions are met:

**Real-time checklist shown to LLM:**
```
STOPPING CONDITIONS CHECKLIST:
✓ Explicit research plan created
✓ 3+ distinct sources (3/3)
? All sub-questions addressed (self-assess)
? Sources cross-referenced (self-assess)
✗ Confidence assessed (not done)
✗ Knowledge gaps identified (not done)
```

The assistant **cannot** conclude until all checkboxes are ✓.

## Quality Standards

### Citation Format
```
"According to [Pinecone Documentation](https://pinecone.io/docs/...), TTL is set per-namespace..."
```

### Source Authority Hierarchy
```
academic papers > industry expert blogs > general articles
```

### Contradiction Handling
```
"Source A claims X, but Source B claims Y. Based on source authority (A is primary, B is secondary)
and recency (A is 2024, B is 2022), X appears more reliable."
```

### Confidence Levels
- **High**: Multiple authoritative sources agree, recent, primary sources
- **Medium**: Some agreement, mix of primary/secondary, or slightly dated
- **Low**: Single source, opinion-based, or conflicting information

## Research Progress Tracking

Throughout research, the system tracks:

```python
{
    "sources_fetched": 3,
    "unique_urls": {"https://pinecone.io/...", "https://docs.trychroma.com/...", ...},
    "searches": 4,
    "search_queries": ["RAG retention", "vector DB TTL", ...],
    "has_plan": True,
    "plan_text": "Research question breakdown: ..."
}
```

This enables:
- Query refinement suggestions
- Progress feedback
- Duplicate source detection

## Implementation Details

### Prompt Engineering Patterns Applied

1. **Planning-First Architecture** (Pre-Act, Plan-and-Solve)
   - Explicit plan generation before execution
   - Sub-goal tracking throughout research

2. **Self-Reflection Loops** (ReAct, Tree-of-Thoughts)
   - Evaluation after each tool call
   - Quality assessment of each source
   - Coverage checks against plan

3. **Structured Context** (Anthropic best practices)
   - XML tags for clarity: `<research_plan>`, `<think>`, `<synthesis>`
   - Metadata embedded in chunk tags: `<chunk id="1" trust="high" url="...">`

4. **Explicit Stopping Conditions** (Agent reliability research)
   - Real-time checklist prevents premature conclusions
   - Multiple criteria must be satisfied

5. **Query Refinement** (Information retrieval research)
   - Tracks search evolution
   - Prompts for refinement based on gaps

### Architecture Components

**Orchestrator** ([argo_brain/assistant/orchestrator.py](argo_brain/argo_brain/assistant/orchestrator.py)):
- `_get_mode_description()`: Returns research-specific prompt
- `_format_research_progress()`: Generates reflection prompts
- `_extract_xml_tag()`: Parses structured outputs
- Research stats tracking in `send_message()`

**Tools**:
- `WebSearchTool`: DuckDuckGo/SearXNG integration
- `WebAccessTool`: Page fetching with trafilatura extraction

**Observability**:
- SQLite `tool_runs` table logs all searches/fetches
- Application logs track query evolution
- `:stats` command shows tool usage breakdown

## Example Session

```
You> Research the latest trends in vector search optimization

Argo> <research_plan>
Sub-questions:
1. What are the current SOTA algorithms for approximate nearest neighbor search?
2. How do recent innovations (HNSW, IVF-PQ) compare in 2024?
3. What are production lessons from high-scale deployments?

Search strategy:
- "vector search optimization 2024"
- "HNSW vs IVF-PQ benchmarks"
- "ANN algorithm comparison recent"

Success criteria:
- 3+ authoritative sources with benchmarks
- Coverage of algorithmic AND production considerations
- Recent data (2023-2025)

Expected sources:
- Research papers, vendor blogs, production engineering posts
</research_plan>

[Executes search for "vector search optimization 2024"]

[RESEARCH_PROGRESS: 0 sources fetched, 1 searches, 1 total tools]
STOPPING CONDITIONS CHECKLIST:
✓ Explicit research plan created
✗ 3+ distinct sources (0/3)
...

<think>
Search returned 5 results. Top 3 look promising:
1. Pinecone blog on HNSW optimization (Dec 2024) - industry expert
2. arXiv paper on DiskANN improvements (Nov 2024) - academic
3. Weaviate case study on billion-scale search (Oct 2024) - production

Will fetch Pinecone blog first as it's likely most accessible.
</think>

[Fetches https://pinecone.io/learn/hnsw-optimization/]

[RESEARCH_PROGRESS: 1 sources fetched, 1 searches, 2 total tools]
STOPPING CONDITIONS CHECKLIST:
✓ Explicit research plan created
✗ 3+ distinct sources (1/3)
...
REFLECTION PROMPT:
- Did the last source provide what you needed?
- What information is still missing?
- Need 2 more authoritative sources

<think>
Pinecone source covered HNSW well but limited on IVF-PQ comparison.
Missing: Academic benchmarks, production lessons from Weaviate.
Will fetch the arXiv paper next for academic perspective.
</think>

[Continues until all stopping conditions met...]

<synthesis>
Based on 4 authoritative sources, here are the latest trends in vector search optimization (2024):

1. **HNSW dominance for sub-second latency**
   According to [Pinecone's December 2024 analysis](https://pinecone.io/...), HNSW with
   dynamic pruning achieves 95%+ recall at <10ms p99 latency...

2. **DiskANN for cost-efficient billion-scale**
   [Microsoft Research paper](https://arxiv.org/...) demonstrates DiskANN reduces memory
   footprint by 10x while maintaining 90%+ recall...

3. **Production lessons: Hybrid approaches**
   [Weaviate's case study](https://weaviate.io/...) shows combining HNSW (hot data) with
   IVF-PQ (cold data) optimizes cost vs performance...

4. **Contradiction noted:**
   Pinecone recommends ef_construction=200 for HNSW, but arXiv paper shows ef=128
   sufficient for most use cases. Resolution: 128 appears optimal for general use,
   200 for precision-critical applications.
</synthesis>

<confidence>High</confidence>

<gaps>
- Limited data on GPU-accelerated ANN (only found NVIDIA blog, no benchmarks)
- Weaviate case study is Oct 2024, may be slightly outdated
- No direct comparison of commercial systems (Pinecone vs Qdrant vs Weaviate)
</gaps>
```

## Research Findings Applied

This implementation incorporates patterns from:

- **Anthropic**: Prompt engineering guide, XML structured prompts, Claude documentation
- **OpenAI**: ReAct paper, GPT-4 research capabilities documentation
- **DeepMind**: Self-critique loops, planning-first architectures
- **LangChain/LlamaIndex**: Multi-agent patterns, tool chaining
- **Academic IR**: Query reformulation, source quality assessment
- **Production systems**: Perplexity AI, You.com research mode architectures

40+ sources analyzed. See git commit history for full research bibliography.

## Configuration

**MAX_TOOL_CALLS**: 10 (vs 3 in quick-lookup mode)
**Stopping conditions**: 6 criteria enforced
**Minimum sources**: 3 distinct URLs
**Context format**: XML with structured metadata

## Logs & Debugging

**Application logs**:
```bash
tail -f /mnt/d/llm/argo_brain/state/logs/argo_brain.log
```

**Enable console logging**:
```bash
ARGO_LOG_TO_STDOUT=1 python scripts/chat_cli.py --mode research
```

**Session stats**:
```
:stats
```

Shows:
- Tool usage breakdown
- Search query evolution
- Message count
- Summary status

## Future Enhancements

Planned improvements:
- [ ] Source credibility scoring (domain authority, author credentials)
- [ ] Automatic fact verification via cross-referencing
- [ ] Research artifact persistence (save plans, syntheses to SQLite)
- [ ] Multi-language source support
- [ ] Academic paper integration (arXiv, Semantic Scholar APIs)
- [ ] Collaborative research (multi-user sessions)

## References

- Anthropic Prompt Engineering Guide: https://docs.anthropic.com/claude/docs/prompt-engineering
- ReAct Paper (Yao et al.): https://arxiv.org/abs/2210.03629
- Plan-and-Solve Prompting: https://arxiv.org/abs/2305.04091
- LangChain Agent Architectures: https://python.langchain.com/docs/modules/agents/
- Tree-of-Thoughts: https://arxiv.org/abs/2305.10601
