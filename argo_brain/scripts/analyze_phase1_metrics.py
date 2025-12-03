#!/usr/bin/env python3
"""Parse Argo logs and extract Phase 1 metrics."""

import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta

# Adjust path based on your setup
log_file = Path.home() / "llm-argo/.argo_data/state/logs/argo_brain.log"

if not log_file.exists():
    print(f"Error: Log file not found at {log_file}")
    print("Please adjust the path in this script or create logs by running Argo.")
    exit(1)

metrics = {
    "llm_calls": [],
    "tool_executions": defaultdict(list),
    "parallel_executions": [],
    "token_usage": [],
    "sessions": defaultdict(dict),
}

# Parse only recent logs (last 24 hours)
cutoff_time = datetime.now() - timedelta(hours=24)

print(f"Parsing logs from {log_file}...")
print(f"Analyzing entries from the last 24 hours...\n")

with open(log_file) as f:
    for line in f:
        # Parse timestamp
        timestamp_match = re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', line)
        if timestamp_match:
            try:
                log_time = datetime.strptime(timestamp_match.group(1), "%Y-%m-%dT%H:%M:%S")
                if log_time < cutoff_time:
                    continue
            except ValueError:
                pass

        # LLM request completed with token counts
        if "LLM request completed" in line:
            elapsed_match = re.search(r"elapsed_ms=([\d.]+)", line)
            prompt_match = re.search(r"prompt_tokens=(\d+)", line)
            completion_match = re.search(r"completion_tokens=(\d+)", line)
            total_match = re.search(r"total_tokens=(\d+)", line)

            if elapsed_match:
                metrics["llm_calls"].append(float(elapsed_match.group(1)))

            if prompt_match and completion_match and total_match:
                metrics["token_usage"].append({
                    "prompt": int(prompt_match.group(1)),
                    "completion": int(completion_match.group(1)),
                    "total": int(total_match.group(1))
                })

        # Tool execution with output length
        if "Tool execution completed" in line:
            # Match both tool= and tool_name= for compatibility (log_setup uses tool=)
            tool_match = re.search(r"tool=(\w+)", line) or re.search(r"tool_name=(\w+)", line)
            output_match = re.search(r"output_length=(\d+)", line)

            if tool_match and output_match:
                tool_name = tool_match.group(1)
                output_len = int(output_match.group(1))
                metrics["tool_executions"][tool_name].append(output_len)

        # Parallel execution - match "X tools in parallel"
        if "tools in parallel" in line:
            count_match = re.search(r"Executing (\d+) tools? in parallel", line)
            if count_match:
                metrics["parallel_executions"].append(int(count_match.group(1)))

# Calculate and display statistics
print("=" * 70)
print(" " * 20 + "PHASE 1 METRICS REPORT")
print("=" * 70)

# LLM Performance
if metrics["llm_calls"]:
    avg_llm = sum(metrics["llm_calls"]) / len(metrics["llm_calls"])
    print(f"\n📊 LLM PERFORMANCE")
    print(f"   Total calls: {len(metrics['llm_calls'])}")
    print(f"   Average duration: {avg_llm:.1f}ms ({avg_llm/1000:.1f}s)")
    print(f"   Min duration: {min(metrics['llm_calls']):.1f}ms")
    print(f"   Max duration: {max(metrics['llm_calls']):.1f}ms")
else:
    print(f"\n📊 LLM PERFORMANCE")
    print(f"   No LLM calls found in recent logs")

# Token Usage
if metrics["token_usage"]:
    avg_prompt = sum(t["prompt"] for t in metrics["token_usage"]) / len(metrics["token_usage"])
    avg_completion = sum(t["completion"] for t in metrics["token_usage"]) / len(metrics["token_usage"])
    avg_total = sum(t["total"] for t in metrics["token_usage"]) / len(metrics["token_usage"])

    print(f"\n🎯 TOKEN USAGE (NEW!)")
    print(f"   Total LLM calls with tokens: {len(metrics['token_usage'])}")
    print(f"   Average prompt tokens: {avg_prompt:.0f}")
    print(f"   Average completion tokens: {avg_completion:.0f}")
    print(f"   Average total tokens: {avg_total:.0f}")
    print(f"   Total tokens consumed: {sum(t['total'] for t in metrics['token_usage'])}")
else:
    print(f"\n🎯 TOKEN USAGE")
    print(f"   No token usage data found")
    print(f"   Note: Token counting was just added. Run a query to generate data.")

# Tool Executions
if metrics["tool_executions"]:
    print(f"\n🔧 TOOL EXECUTIONS")
    for tool_name, outputs in sorted(metrics["tool_executions"].items()):
        avg_output = sum(outputs) / len(outputs)
        print(f"   {tool_name}:")
        print(f"      Calls: {len(outputs)}")
        print(f"      Avg output size: {avg_output:.0f} chars ({avg_output/4:.0f} tokens est.)")
        print(f"      Min: {min(outputs)} chars, Max: {max(outputs)} chars")

        # Highlight web_access token savings
        if tool_name == "web_access" and avg_output < 3000:
            print(f"      ✅ Concise mode working! (~80% token savings vs 10K baseline)")
else:
    print(f"\n🔧 TOOL EXECUTIONS")
    print(f"   No tool executions found in recent logs")

# Parallel Execution
if metrics["parallel_executions"]:
    total_parallel_tools = sum(metrics["parallel_executions"])
    avg_batch_size = total_parallel_tools / len(metrics["parallel_executions"])
    print(f"\n⚡ PARALLEL EXECUTION (NEW!)")
    print(f"   Parallel batches executed: {len(metrics['parallel_executions'])}")
    print(f"   Total tools run in parallel: {total_parallel_tools}")
    print(f"   Average tools per batch: {avg_batch_size:.1f}")
    print(f"   ✅ Phase 1 parallel execution is working!")
else:
    print(f"\n⚡ PARALLEL EXECUTION")
    print(f"   No parallel tool executions detected")
    print(f"   Note: Parallel execution triggers when 2+ tools are called together")

print("\n" + "=" * 70)

# Phase 1 Success Indicators
print("\n✅ PHASE 1 SUCCESS INDICATORS")
success_indicators = []

if metrics["tool_executions"].get("web_access"):
    avg_web_access = sum(metrics["tool_executions"]["web_access"]) / len(metrics["tool_executions"]["web_access"])
    if avg_web_access < 3000:
        success_indicators.append("✓ web_access using concise mode (avg < 3K chars)")
    else:
        success_indicators.append("✗ web_access output still large (check response_format)")

if metrics["parallel_executions"]:
    success_indicators.append(f"✓ Parallel execution working ({len(metrics['parallel_executions'])} batches)")
else:
    success_indicators.append("? No parallel executions yet (run multi-tool query)")

if metrics["token_usage"]:
    avg_total = sum(t["total"] for t in metrics["token_usage"]) / len(metrics["token_usage"])
    if avg_total < 3000:
        success_indicators.append(f"✓ Token usage reasonable (avg {avg_total:.0f} tokens)")
    else:
        success_indicators.append(f"⚠ Token usage high (avg {avg_total:.0f} tokens, target <3K)")
else:
    success_indicators.append("? Token counting just added (run query to test)")

for indicator in success_indicators:
    print(f"   {indicator}")

print("\n" + "=" * 70)
print("\n💡 TIP: Run 'tail -f ~/.argo_data/logs/argo_brain.log' to watch metrics in real-time")
print("💡 TIP: Check full guide at docs/PHASE1_MEASUREMENT_GUIDE.md")
print()
