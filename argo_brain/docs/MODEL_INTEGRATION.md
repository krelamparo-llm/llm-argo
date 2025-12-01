# Model Integration Best Practices

This document describes the model integration improvements inspired by the Qwen3-Coder-30B model documentation and other modern LLM best practices.

## Quick Start: Automatic Configuration

**✨ NEW: Zero-config model integration!**

When you download a new model, Argo Brain automatically detects and uses its custom configurations:

```python
from argo_brain.model_registry import get_global_registry

# Automatically detects tokenizers, parsers, and recommended settings
registry = get_global_registry()
config = registry.auto_configure("qwen3-coder-30b")

# Everything is configured with intelligent fallbacks!
tokenizer = config["tokenizer"]
parser = config["parser"]()
sampling = config["sampling"]
```

**📖 See [AUTO_DETECTION.md](./AUTO_DETECTION.md) for complete details on automatic model detection.**

## Overview

The Argo Brain system now includes enhanced support for:

1. **Automatic Model Detection** - 🆕 Zero-config with intelligent fallbacks
2. **Advanced Sampling Parameters** - Following Qwen3-Coder recommendations
3. **Tokenizer Integration** - HuggingFace transformers compatibility
4. **XML-based Tool Parsing** - Structured tool call format
5. **Chat Template Support** - Model-specific prompt formatting

## 1. Advanced Sampling Parameters

### Configuration

The following parameters are now configurable in `argo.toml`:

```toml
[llm]
temperature = 0.7              # Sampling temperature (0.0-2.0)
top_p = 0.8                    # Nucleus sampling probability
top_k = 20                     # Top-K sampling limit
repetition_penalty = 1.05      # Penalty for token repetition
max_tokens = 2048              # Maximum tokens to generate
```

### Best Practices from Qwen3-Coder-30B

Based on the official Qwen3-Coder documentation, we recommend:

- **temperature=0.7**: Balanced creativity and accuracy
- **top_p=0.8**: Nucleus sampling for diverse but coherent outputs
- **top_k=20**: Limits vocabulary to prevent unlikely tokens
- **repetition_penalty=1.05**: Subtle penalty to reduce repetitive text
- **max_tokens=2048-65536**: Adequate for instruct models (65536 recommended for comprehensive responses)

### Usage

These parameters are automatically applied when using the `LLMClient`:

```python
from argo_brain.llm_client import LLMClient

client = LLMClient()
response = client.chat(
    messages,
    temperature=0.7,  # Override config
    top_p=0.8,
    top_k=20,
    repetition_penalty=1.05,
    max_tokens=2048
)
```

## 2. Tokenizer Integration

### Setup

Install the transformers library:

```bash
pip install transformers
```

Configure the tokenizer path in `argo.toml`:

```toml
[llm]
use_chat_template = 1
tokenizer_path = "/mnt/d/llm/models/qwen3-coder-30b"
```

### Using the Tokenizer

```python
from argo_brain.tokenizer import create_tokenizer

# Load tokenizer
tokenizer = create_tokenizer("/mnt/d/llm/models/qwen3-coder-30b")

# Apply chat template
messages = [
    {"role": "user", "content": "Write a function"}
]
formatted = tokenizer.apply_chat_template(messages, add_generation_prompt=True)

# Encode/decode
token_ids = tokenizer.encode("Hello world")
text = tokenizer.decode(token_ids)
```

### Chat Template Features

The tokenizer supports:

- **Special tokens**: `<|im_start|>`, `<|im_end|>`
- **Tool formatting**: XML-based tool calls
- **Multiple roles**: system, user, assistant, tool
- **Custom templates**: Load Jinja2 templates from files

## 3. XML-based Tool Call Parser

### Format

The parser supports XML-formatted tool calls:

```xml
<tool_call>
<function=function_name>
<parameter=arg1>
value1
</parameter>
<parameter=arg2>
value2
</parameter>
</function>
</tool_call>
```

### Usage

```python
from argo_brain.tools.xml_parser import XMLToolParser

parser = XMLToolParser()

# Extract tool calls from LLM output
tool_calls = parser.extract_tool_calls(llm_response)

for call in tool_calls:
    tool_name = call["tool"]
    arguments = call["arguments"]
    print(f"Tool: {tool_name}, Args: {arguments}")
```

### Type Conversion

The parser automatically converts parameter values based on JSON schema types:

- **string**: No conversion
- **int/integer**: Converted to Python `int`
- **float/number**: Converted to Python `float`
- **boolean/bool**: Converted to Python `bool` (true/false)
- **object/dict**: Parsed as JSON
- **array/list**: Parsed as JSON

Example:

```python
# Define schema
schema = {
    "properties": {
        "count": {"type": "integer"},
        "enabled": {"type": "boolean"},
        "data": {"type": "object"}
    }
}

# Parse with type conversion
parser.convert_param_value("42", "count", schema, "my_function")
# Returns: 42 (int)

parser.convert_param_value("true", "enabled", schema, "my_function")
# Returns: True (bool)
```

## 4. Tool Definition Format

### XML Format for Prompts

Tools can be formatted in XML for better LLM parsing:

```python
from argo_brain.tools.xml_parser import XMLToolParser

parser = XMLToolParser()

tool_xml = parser.format_tool_for_prompt(
    tool_name="search_web",
    description="Search the web for information",
    parameters={
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return"
            }
        }
    }
)
```

Output:

```xml
<function>
<name>search_web</name>
<description>Search the web for information</description>
<parameters>
<parameter>
<name>query</name>
<type>string</type>
<description>Search query</description>
</parameter>
<parameter>
<name>max_results</name>
<type>integer</type>
<description>Maximum results to return</description>
</parameter>
</parameters>
</function>
```

## 5. Model-Specific Configuration

### Qwen3-Coder-30B

For optimal performance with Qwen3-Coder-30B:

```toml
[llm]
model = "qwen3-coder-30b"
temperature = 0.7
top_p = 0.8
top_k = 20
repetition_penalty = 1.05
max_tokens = 65536  # Full capability
use_chat_template = 1
tokenizer_path = "/mnt/d/llm/models/qwen3-coder-30b"
```

### Context Length

Qwen3-Coder supports:
- **Native**: 262,144 tokens
- **Extended (Yarn)**: Up to 1M tokens
- **Recommended**: 32,768 for most use cases

### Non-Thinking Mode

This model does not generate `<think></think>` blocks by default. No need to set `enable_thinking=False`.

## 6. Environment Variables

All configuration can be overridden via environment variables:

```bash
# Sampling parameters
export ARGO_LLM_TEMPERATURE=0.7
export ARGO_LLM_TOP_P=0.8
export ARGO_LLM_TOP_K=20
export ARGO_LLM_REPETITION_PENALTY=1.05
export ARGO_LLM_MAX_TOKENS=2048

# Tokenizer
export ARGO_LLM_USE_CHAT_TEMPLATE=1
export ARGO_LLM_TOKENIZER_PATH="/mnt/d/llm/models/qwen3-coder-30b"

# Server
export ARGO_LLM_BASE_URL="http://127.0.0.1:8080/v1/chat/completions"
export ARGO_LLM_TIMEOUT=300
```

## 7. Migration Guide

### From Old Configuration

**Before:**
```toml
[llm]
base_url = "http://127.0.0.1:8080/v1/chat/completions"
model = "local-llm"
```

**After:**
```toml
[llm]
base_url = "http://127.0.0.1:8080/v1/chat/completions"
model = "local-llm"
temperature = 0.7
top_p = 0.8
top_k = 20
repetition_penalty = 1.05
max_tokens = 2048
```

### Code Updates

No code changes required! The new parameters are backward compatible and use sensible defaults.

## 8. Performance Tuning

### Response Quality

- **More creative**: Increase `temperature` (0.8-1.0)
- **More focused**: Decrease `temperature` (0.3-0.6)
- **More diverse**: Increase `top_p` (0.9-0.95)
- **More deterministic**: Decrease `top_p` (0.5-0.7)

### Response Length

- **Quick answers**: `max_tokens=512-1024`
- **Standard responses**: `max_tokens=2048`
- **Comprehensive analysis**: `max_tokens=4096-8192`
- **Full capability**: `max_tokens=65536` (Qwen3-Coder)

### Repetition Control

- **Less repetitive**: Increase `repetition_penalty` (1.1-1.2)
- **More natural flow**: Use default `1.05`
- **Allow repetition**: Decrease to `1.0` (no penalty)

## 9. References

- [Qwen3-Coder Technical Report](https://arxiv.org/abs/2505.09388)
- [Qwen3-Coder HuggingFace](https://huggingface.co/Qwen/Qwen3-Coder-30B-A3B-Instruct)
- [HuggingFace Transformers](https://huggingface.co/docs/transformers)
- [llama.cpp Sampling](https://github.com/ggerganov/llama.cpp/wiki/Sampling)

## 10. Troubleshooting

### High Latency

- Reduce `max_tokens` to 2048 or lower
- Use smaller context window
- Consider model quantization (Q4_K_M, Q8_0)

### Out of Memory

- Lower `max_tokens`
- Use smaller batch sizes
- Enable streaming mode

### Poor Quality Responses

- Adjust `temperature` (try 0.7)
- Increase `top_k` to 40-50
- Add more context to prompts

### Tool Call Parsing Errors

- Verify XML format in LLM output
- Check tool schema definitions
- Enable debug logging for parser
