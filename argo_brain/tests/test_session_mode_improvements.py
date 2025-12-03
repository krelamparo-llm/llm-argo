#!/usr/bin/env python3
"""Test session mode architectural improvements.

This script validates the implementation of:
- Comprehensive prompts for all modes
- Progressive temperature schedules
- Mode-specific max_tokens
- Dynamic tool availability
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from argo_brain.assistant.orchestrator import ArgoAssistant
from argo_brain.core.memory.session import SessionMode


def test_prompt_lengths():
    """Test that all modes have comprehensive prompts."""
    print("=" * 80)
    print("TEST 1: Prompt Comprehensiveness")
    print("=" * 80)

    assistant = ArgoAssistant()

    # Test QUICK_LOOKUP prompt
    quick_prompt = assistant._get_mode_description(SessionMode.QUICK_LOOKUP)
    quick_lines = len(quick_prompt.split('\n'))
    print(f"\n✓ QUICK_LOOKUP prompt: {quick_lines} lines, {len(quick_prompt)} chars")
    assert quick_lines >= 48, f"QUICK_LOOKUP prompt too short: {quick_lines} lines (expected >=48)"
    assert ("Maximum" in quick_prompt and "1 tool call" in quick_prompt), "QUICK_LOOKUP should enforce 1 tool max"
    assert "PRIORITY ORDER" in quick_prompt, "QUICK_LOOKUP should have priority order"
    print("  - Contains '1 tool call' maximum ✓")
    print("  - Contains 'PRIORITY ORDER' ✓")

    # Test INGEST prompt
    ingest_prompt = assistant._get_mode_description(SessionMode.INGEST)
    ingest_lines = len(ingest_prompt.split('\n'))
    print(f"\n✓ INGEST prompt: {ingest_lines} lines, {len(ingest_prompt)} chars")
    assert ingest_lines >= 75, f"INGEST prompt too short: {ingest_lines} lines (expected >=75)"
    assert "STEP 1:" in ingest_prompt, "INGEST should have workflow steps"
    assert "STEP 2:" in ingest_prompt, "INGEST should have workflow steps"
    assert "STEP 3:" in ingest_prompt, "INGEST should have workflow steps"
    assert "STEP 4:" in ingest_prompt, "INGEST should have workflow steps"
    print("  - Contains 4-step workflow ✓")

    # Test RESEARCH prompt (should remain comprehensive)
    research_prompt = assistant._get_mode_description(SessionMode.RESEARCH)
    research_lines = len(research_prompt.split('\n'))
    print(f"\n✓ RESEARCH prompt: {research_lines} lines, {len(research_prompt)} chars")
    assert research_lines >= 65, f"RESEARCH prompt too short: {research_lines} lines (expected >=65)"
    assert "PHASE 1: PLANNING" in research_prompt, "RESEARCH should have planning phase"
    assert "PHASE 2: EXECUTION" in research_prompt, "RESEARCH should have execution phase"
    assert "PHASE 3: SYNTHESIS" in research_prompt, "RESEARCH should have synthesis phase"
    print("  - Contains 3-phase framework ✓")

    print("\n" + "=" * 80)
    print("TEST 1: PASSED ✓")
    print("=" * 80)


def test_temperature_schedules():
    """Test progressive temperature calculation."""
    print("\n" + "=" * 80)
    print("TEST 2: Progressive Temperature")
    print("=" * 80)

    assistant = ArgoAssistant()

    # QUICK_LOOKUP temperatures
    print("\nQUICK_LOOKUP mode:")
    temp_initial = assistant._get_temperature_for_phase(SessionMode.QUICK_LOOKUP, "answer", has_tool_results=False)
    temp_after = assistant._get_temperature_for_phase(SessionMode.QUICK_LOOKUP, "answer", has_tool_results=True)
    print(f"  Initial (no tools): {temp_initial}")
    print(f"  After tools: {temp_after}")
    assert temp_initial == 0.3, f"QUICK_LOOKUP initial temp should be 0.3, got {temp_initial}"
    assert temp_after == 0.5, f"QUICK_LOOKUP after temp should be 0.5, got {temp_after}"
    assert temp_after > temp_initial, "Temperature should increase after tools in QUICK_LOOKUP"
    print("  ✓ Progressive temperature (0.3 → 0.5)")

    # RESEARCH temperatures
    print("\nRESEARCH mode:")
    temp_planning = assistant._get_temperature_for_phase(SessionMode.RESEARCH, "planning")
    temp_tool = assistant._get_temperature_for_phase(SessionMode.RESEARCH, "tool_call")
    temp_synthesis = assistant._get_temperature_for_phase(SessionMode.RESEARCH, "synthesis")
    print(f"  Planning: {temp_planning}")
    print(f"  Tool calls: {temp_tool}")
    print(f"  Synthesis: {temp_synthesis}")
    assert temp_planning == 0.4, f"RESEARCH planning temp should be 0.4, got {temp_planning}"
    assert temp_tool == 0.2, f"RESEARCH tool temp should be 0.2, got {temp_tool}"
    assert temp_synthesis == 0.7, f"RESEARCH synthesis temp should be 0.7, got {temp_synthesis}"
    assert temp_tool < temp_planning < temp_synthesis, "RESEARCH temp should be lowest for tools, highest for synthesis"
    print("  ✓ Progressive temperature (0.4 → 0.2 → 0.7)")

    # INGEST temperature
    print("\nINGEST mode:")
    temp_ingest = assistant._get_temperature_for_phase(SessionMode.INGEST, "summary")
    print(f"  Summary: {temp_ingest}")
    assert temp_ingest == 0.5, f"INGEST temp should be 0.5, got {temp_ingest}"
    print("  ✓ Balanced temperature (0.5)")

    print("\n" + "=" * 80)
    print("TEST 2: PASSED ✓")
    print("=" * 80)


def test_max_tokens():
    """Test mode-specific max_tokens."""
    print("\n" + "=" * 80)
    print("TEST 3: Mode-Specific Max Tokens")
    print("=" * 80)

    assistant = ArgoAssistant()

    print("\nMax tokens by mode:")
    max_quick = assistant._get_max_tokens_for_mode(SessionMode.QUICK_LOOKUP)
    max_research = assistant._get_max_tokens_for_mode(SessionMode.RESEARCH)
    max_ingest = assistant._get_max_tokens_for_mode(SessionMode.INGEST)

    print(f"  QUICK_LOOKUP: {max_quick}")
    print(f"  RESEARCH: {max_research}")
    print(f"  INGEST: {max_ingest}")

    assert max_quick == 1024, f"QUICK_LOOKUP max_tokens should be 1024, got {max_quick}"
    assert max_research == 4096, f"RESEARCH max_tokens should be 4096, got {max_research}"
    assert max_ingest == 2048, f"INGEST max_tokens should be 2048, got {max_ingest}"
    assert max_quick < max_ingest < max_research, "RESEARCH should have highest max_tokens"

    print("  ✓ QUICK_LOOKUP < INGEST < RESEARCH")

    print("\n" + "=" * 80)
    print("TEST 3: PASSED ✓")
    print("=" * 80)


def test_dynamic_tool_availability():
    """Test phase-aware tool filtering."""
    print("\n" + "=" * 80)
    print("TEST 4: Dynamic Tool Availability")
    print("=" * 80)

    assistant = ArgoAssistant()

    # QUICK_LOOKUP tools
    print("\nQUICK_LOOKUP mode:")
    quick_tools = assistant._get_available_tools_for_mode(SessionMode.QUICK_LOOKUP)
    print(f"  Available tools: {quick_tools}")
    assert quick_tools is not None, "QUICK_LOOKUP should filter tools"
    assert "memory_write" not in quick_tools, "QUICK_LOOKUP should not allow memory_write"
    assert "web_search" in quick_tools, "QUICK_LOOKUP should allow web_search"
    assert "memory_query" in quick_tools, "QUICK_LOOKUP should allow memory_query"
    print("  ✓ No memory_write (read-only mode)")

    # RESEARCH planning phase
    print("\nRESEARCH mode - Planning phase:")
    research_stats_planning = {"has_plan": False, "tool_calls": 0}
    planning_tools = assistant._get_available_tools_for_mode(SessionMode.RESEARCH, research_stats_planning)
    print(f"  Available tools: {planning_tools}")
    assert planning_tools == [], "RESEARCH planning should have no tools"
    print("  ✓ No tools during planning")

    # RESEARCH exploration phase
    print("\nRESEARCH mode - Exploration phase:")
    research_stats_explore = {"has_plan": True, "tool_calls": 5, "synthesis_triggered": False}
    explore_tools = assistant._get_available_tools_for_mode(SessionMode.RESEARCH, research_stats_explore)
    print(f"  Available tools: {explore_tools}")
    assert explore_tools is not None, "RESEARCH exploration should filter tools"
    assert "web_search" in explore_tools, "RESEARCH exploration should allow web_search"
    assert "web_access" in explore_tools, "RESEARCH exploration should allow web_access"
    assert "memory_write" not in explore_tools, "RESEARCH exploration should not allow memory_write yet"
    print("  ✓ Search and access only")

    # RESEARCH synthesis phase
    print("\nRESEARCH mode - Synthesis phase:")
    research_stats_synthesis = {"has_plan": True, "tool_calls": 10, "synthesis_triggered": True}
    synthesis_tools = assistant._get_available_tools_for_mode(SessionMode.RESEARCH, research_stats_synthesis)
    print(f"  Available tools: {synthesis_tools}")
    assert synthesis_tools is not None, "RESEARCH synthesis should filter tools"
    assert "memory_write" in synthesis_tools, "RESEARCH synthesis should allow memory_write"
    assert "web_search" not in synthesis_tools, "RESEARCH synthesis should not allow web_search"
    print("  ✓ Memory operations only")

    # INGEST tools
    print("\nINGEST mode:")
    ingest_tools = assistant._get_available_tools_for_mode(SessionMode.INGEST)
    print(f"  Available tools: {ingest_tools}")
    assert ingest_tools is not None, "INGEST should filter tools"
    assert "memory_write" in ingest_tools, "INGEST should allow memory_write"
    assert "web_access" in ingest_tools, "INGEST should allow web_access"
    assert "web_search" not in ingest_tools, "INGEST should not allow web_search"
    print("  ✓ No web_search (user provides material)")

    print("\n" + "=" * 80)
    print("TEST 4: PASSED ✓")
    print("=" * 80)


def test_max_tool_calls_per_mode():
    """Test per-mode tool call limits."""
    print("\n" + "=" * 80)
    print("TEST 5b: Max Tool Calls Per Mode")
    print("=" * 80)

    assistant = ArgoAssistant()

    print("\nMax tool calls by mode:")
    max_quick = assistant._get_max_tool_calls_for_mode(SessionMode.QUICK_LOOKUP)
    max_research = assistant._get_max_tool_calls_for_mode(SessionMode.RESEARCH)
    max_ingest = assistant._get_max_tool_calls_for_mode(SessionMode.INGEST)

    print(f"  QUICK_LOOKUP: {max_quick}")
    print(f"  RESEARCH: {max_research}")
    print(f"  INGEST: {max_ingest}")

    assert max_quick == 2, f"QUICK_LOOKUP max_tool_calls should be 2, got {max_quick}"
    assert max_research == 10, f"RESEARCH max_tool_calls should be 10, got {max_research}"
    assert max_ingest == 3, f"INGEST max_tool_calls should be 3, got {max_ingest}"
    assert max_quick < max_ingest < max_research, "RESEARCH should allow most tool calls"

    print("  ✓ QUICK_LOOKUP (2) < INGEST (3) < RESEARCH (10)")

    print("\n" + "=" * 80)
    print("TEST 5b: PASSED ✓")
    print("=" * 80)


def test_tool_registry_filtering():
    """Test that ToolRegistry.manifest() supports filtering."""
    print("\n" + "=" * 80)
    print("TEST 5: ToolRegistry Filtering")
    print("=" * 80)

    from argo_brain.tools.base import ToolRegistry
    from argo_brain.tools.search import WebSearchTool
    from argo_brain.tools import MemoryQueryTool, MemoryWriteTool

    registry = ToolRegistry()
    registry.register(WebSearchTool())
    registry.register(MemoryQueryTool(memory_manager=None))
    registry.register(MemoryWriteTool(ingestion_manager=None))

    # Test unfiltered manifest
    print("\nUnfiltered manifest:")
    full_manifest = registry.manifest()
    assert "web_search" in full_manifest.lower(), "Full manifest should include web_search"
    assert "memory_query" in full_manifest.lower(), "Full manifest should include memory_query"
    assert "memory_write" in full_manifest.lower(), "Full manifest should include memory_write"
    print("  ✓ Contains all 3 tools")

    # Test filtered manifest
    print("\nFiltered manifest (web_search only):")
    filtered_manifest = registry.manifest(filter_tools=["web_search"])
    assert "web_search" in filtered_manifest.lower(), "Filtered manifest should include web_search"
    assert "memory_query" not in filtered_manifest.lower(), "Filtered manifest should not include memory_query"
    assert "memory_write" not in filtered_manifest.lower(), "Filtered manifest should not include memory_write"
    print("  ✓ Contains only web_search")

    # Test empty filter
    print("\nEmpty filter (no tools):")
    empty_manifest = registry.manifest(filter_tools=[])
    assert empty_manifest == "", "Empty filter should return empty manifest"
    print("  ✓ Returns empty string")

    print("\n" + "=" * 80)
    print("TEST 5: PASSED ✓")
    print("=" * 80)


def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("SESSION MODE ARCHITECTURE IMPROVEMENTS - TEST SUITE")
    print("=" * 80)

    try:
        test_prompt_lengths()
        test_temperature_schedules()
        test_max_tokens()
        test_dynamic_tool_availability()
        test_max_tool_calls_per_mode()
        test_tool_registry_filtering()

        print("\n" + "=" * 80)
        print("ALL TESTS PASSED ✓✓✓")
        print("=" * 80)
        print("\nSummary:")
        print("  ✓ Comprehensive prompts for all modes")
        print("  ✓ Progressive temperature schedules")
        print("  ✓ Mode-specific max_tokens")
        print("  ✓ Dynamic tool availability (5 configurations)")
        print("  ✓ Per-mode max_tool_calls limits")
        print("  ✓ ToolRegistry filtering support")
        print("\nImplementation is ready for production testing!")
        print("=" * 80)

        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
