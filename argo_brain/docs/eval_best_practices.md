# Evaluation Best Practices for Agentic Systems

Last updated: 2025-12-04

## Goals
- Catch regressions in tool use, safety, and memory fidelity without human label loops.
- Keep evaluation sets fresh and contamination-resistant for local models.
- Balance objective checks (ground truth) with trajectory-aware judgment.

## Patterns to Use
- **Objective, refreshable sets (LiveBench-style)**: Maintain small but regularly rotated questions with verifiable answers; expire or rotate items every ~6 months to avoid prompt overfitting.
- **Trajectory-aware judges (Agent-as-a-Judge)**: When labels are subjective, have an evaluator agent score intermediate steps (tool choices, parameter extraction, refusals) instead of only final text.
- **Pre-execution policy gates**: Validate tool calls before execution (scheme/host, parameter bounds, PII/file patterns) and log denials as first-class events.
- **Continuous sampling in prod**: Sample a slice of live traffic for ongoing scoring (correctness, faithfulness, tool-selection accuracy, safety), and alert on drift.
- **Parallelism-aware performance checks**: Track timestamp proximity between tool runs to verify that “parallel” behaviors are actually concurrent.
- **PII & dangerous-query hygiene**: Treat PII echoes and dangerous payloads (file paths, command strings) as hard fails; require explicit refusals without tool calls.

## Signals to Log for Every Eval
- Tool run metadata: name, inputs, timestamps, outcome/refusal.
- Conversation traces: user turns, assistant responses (raw + cleaned).
- Citations: URL count and diversity per answer.
- Safety events: policy rejections, injection handling, sanitized queries.
- Memory events: writes vs queries ordering, conflicts/recency resolutions.

## Local Test Suite Strategy
- **Heuristic self-checks first**: Cheap regex/structure checks catch 80% of regressions; keep them fast so they run in `--auto`.
- **Model judges only for nuance**: Reserve LLM-judged evals for fuzzy tasks (tone, helpfulness), and pin model/temperature to keep scores stable.
- **Per-turn artifacts**: Store `/tmp/test_<id>_<session>_turnN.txt` for reproducible failures without rerunning the suite.

## Maintenance
- Rotate scenarios and URLs quarterly to reduce staleness.
- Version eval prompts and pin judge models when used.
- Track historical pass/fail by test ID to spot drifts over time.

References: LiveBench (ICLR 2025 spotlight), Agent-as-a-Judge (arXiv:2410.10934), AWS AgentCore Evaluations (2025-12) for continuous quality gating.
