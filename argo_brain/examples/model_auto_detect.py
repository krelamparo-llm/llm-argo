#!/usr/bin/env python3
"""Example: Automatic Model Configuration Detection

This script demonstrates how Argo Brain automatically detects and configures
model-specific settings, parsers, and tokenizers with intelligent fallbacks.
"""

from pathlib import Path

from argo_brain.model_registry import get_global_registry


def main():
    """Demonstrate automatic model detection."""

    print("=" * 70)
    print("Argo Brain - Automatic Model Configuration Detection")
    print("=" * 70)

    # Get the global registry (automatically scans models directory)
    print("\n🔍 Scanning models directory...")
    registry = get_global_registry()

    # List all detected models
    models = registry.list_models()
    print(f"\n✅ Found {len(models)} model(s):")
    for model_name in models:
        print(f"   - {model_name}")

    if not models:
        print("\n⚠️  No models found. Ensure models are in the configured directory.")
        from argo_brain.config import CONFIG
        print(f"   Models root: {CONFIG.paths.models_root}")
        return

    print("\n" + "=" * 70)
    print("Model Details")
    print("=" * 70)

    # Inspect each model
    for model_name in models:
        model = registry.get_model(model_name)
        if not model:
            continue

        print(f"\n📦 Model: {model_name}")
        print(f"   Path: {model.path}")
        print(f"   Components:")
        print(f"      Tokenizer:      {'✅ Yes' if model.has_tokenizer else '❌ No (using fallback)'}")
        print(f"      Chat Template:  {'✅ Yes' if model.has_chat_template else '❌ No (using fallback)'}")
        print(f"      Tool Parser:    {'✅ Custom' if model.has_tool_parser else '❌ Default XML'}")
        print(f"      Config:         {'✅ Yes' if model.has_config else '❌ No'}")

        # Show recommended settings
        print(f"   Recommended Settings:")
        if model.recommended_temperature is not None:
            print(f"      Temperature:          {model.recommended_temperature}")
        if model.recommended_top_p is not None:
            print(f"      Top-P:                {model.recommended_top_p}")
        if model.recommended_top_k is not None:
            print(f"      Top-K:                {model.recommended_top_k}")
        if model.recommended_repetition_penalty is not None:
            print(f"      Repetition Penalty:   {model.recommended_repetition_penalty}")
        if model.recommended_max_tokens is not None:
            print(f"      Max Tokens:           {model.recommended_max_tokens:,}")

        # Get complete recommended config
        full_config = registry.get_recommended_config(model)
        print(f"   Complete Config: {full_config}")

    # Demonstrate auto-configuration
    print("\n" + "=" * 70)
    print("Auto-Configuration Example")
    print("=" * 70)

    if models:
        example_model = models[0]
        print(f"\n🚀 Auto-configuring model: {example_model}")

        config = registry.auto_configure(example_model)

        print("\n✅ Auto-configuration complete!")
        print(f"   Tokenizer:     {type(config['tokenizer']).__name__ if config['tokenizer'] else 'None (fallback)'}")
        print(f"   Parser:        {config['parser'].__name__}")
        print(f"   Chat Template: {'Loaded' if config['chat_template'] else 'Default'}")
        print(f"   Sampling:      {config['sampling']}")

        # Demonstrate parser usage
        print("\n📝 Testing tool call parser...")
        parser = config["parser"]()
        print(f"   Parser class:  {parser.__class__.__name__}")

        # Example XML tool call
        example_output = """
        Let me search for that information.

        <tool_call>
        <function=web_search>
        <parameter=query>
        best practices for LLM integration
        </parameter>
        <parameter=max_results>
        5
        </parameter>
        </function>
        </tool_call>
        """

        print(f"\n   Example LLM output:")
        print("   " + example_output.strip().replace("\n", "\n   "))

        tool_calls = parser.extract_tool_calls(example_output)

        if tool_calls:
            print(f"\n   ✅ Parsed {len(tool_calls)} tool call(s):")
            for i, call in enumerate(tool_calls, 1):
                print(f"      {i}. Tool: {call['tool']}")
                print(f"         Args: {call['arguments']}")
        else:
            print("\n   ⚠️  No tool calls detected (expected if parser is basic)")

    print("\n" + "=" * 70)
    print("🎉 Auto-detection complete!")
    print("=" * 70)
    print("\n💡 Tips:")
    print("   - Place new models in the models directory")
    print("   - Include README.md with recommended settings")
    print("   - Add tokenizer files for best results")
    print("   - Custom tool parsers are automatically detected")
    print("\n📖 See docs/AUTO_DETECTION.md for more information")


if __name__ == "__main__":
    main()
