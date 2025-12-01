# Integration Gap Analysis

## Current State (What We Have vs. What We Use)

### What We Built ✅

We created comprehensive infrastructure for model-specific integration:

1. **[model_registry.py](../argo_brain/model_registry.py)** - Auto-detection system
   - Scans model directories
   - Detects tokenizers, parsers, chat templates
   - Extracts recommended settings from README

2. **[tokenizer.py](../argo_brain/tokenizer.py)** - HuggingFace tokenizer wrapper
   - `apply_chat_template()` support
   - Encoding/decoding
   - Custom template loading

3. **[tools/xml_parser.py](../argo_brain/tools/xml_parser.py)** - Generic XML parser
   - Parses XML tool calls
   - Type conversion
   - Schema validation

### What We're NOT Using ❌

**CRITICAL GAP**: None of this infrastructure is integrated into the orchestrator!

Currently, the orchestrator (`argo_brain/assistant/orchestrator.py`):
- ❌ Does NOT use `ModelRegistry`
- ❌ Does NOT use model-specific parsers
- ❌ Does NOT use chat templates
- ❌ Does NOT use tokenizers
- ❌ Forces JSON format regardless of model

## The Problem

### Qwen3-Coder-30B Format Mismatch

The model has these files in `/mnt/d/llm/models/qwen3-coder-30b/`:

1. **`chat_template.jinja`** - Tells the model to use XML format:
   ```
   If you choose to call a function ONLY reply in the following format:

   <tool_call>
   <function=example_function_name>
   <parameter=param1>
   value
   </parameter>
   </function>
   </tool_call>
   ```

2. **`qwen3coder_tool_parser.py`** - Parses XML format:
   ```python
   self.tool_call_start_token = "<tool_call>"
   self.tool_call_prefix = "<function="
   self.parameter_prefix = "<parameter="
   ```

3. **`tokenizer.json`** - Contains special tokens for tool calling

### But We're Forcing JSON! ❌

In our orchestrator prompts, we say:

```python
"When you need a tool, output ONLY this JSON format (nothing else):\n"
"{\"plan\": \"explanation\", \"tool_calls\": [{\"tool\": \"name\", \"args\": {}}]}\n"
```

**This contradicts the model's training!** The model is confused because:
- Its chat template says: "Use XML format"
- Our prompt says: "Use JSON format"
- Result: Model generates BOTH formats or gets confused

## What Each Model Has

### qwen3-coder-30b (Full-Featured)
```
✅ chat_template.jinja         - XML format instructions
✅ qwen3coder_tool_parser.py    - Custom parser for XML
✅ tokenizer.json              - Special tokens
✅ config.json                 - Model config
✅ generation_config.json      - Generation settings
✅ README.md                   - Recommends temp=0.7, top_p=0.8, etc.
```

### qwen3-32b (Minimal)
```
❌ No special files (only GGUF)
```

### gemma-3-1b (Minimal)
```
❌ No special files (only GGUF + README)
```

## The Correct Architecture

### Model-Aware Format Selection

```python
# Pseudo-code for what we SHOULD be doing:

if model.has_custom_parser:
    # Use model's native format (XML for qwen3-coder)
    use_xml_format = True
    parser = load_model_parser(model)
else:
    # Use JSON format as fallback
    use_xml_format = False
    parser = JSONParser()

if model.has_chat_template:
    # Use model's chat template
    messages = tokenizer.apply_chat_template(messages, tools=tools)
else:
    # Use simple format
    messages = simple_format(messages)
```

### Integration Points

1. **ArgoAssistant.__init__()** - Should detect model and load parser
2. **build_prompt()** - Should use chat template if available
3. **_maybe_parse_tool_call()** - Should use model-specific parser
4. **System prompts** - Should match model's expected format

## What Needs to Change

### 1. Detect Model on Initialization

```python
class ArgoAssistant:
    def __init__(self, model_name: Optional[str] = None):
        # NEW: Detect which model we're using
        registry = get_global_registry()
        model_config = registry.auto_configure(model_name or "qwen3-coder-30b")

        self.parser = model_config["parser"]()
        self.tokenizer = model_config["tokenizer"]
        self.format = "xml" if model_config.get("uses_xml") else "json"
```

### 2. Update System Prompt Based on Format

```python
def _get_tool_format_instructions(self):
    if self.format == "xml":
        return """
        When you need a tool, use this XML format:
        <tool_call>
        <function=tool_name>
        <parameter=arg>value</parameter>
        </function>
        </tool_call>
        """
    else:
        return """
        When you need a tool, use this JSON format:
        {"plan": "...", "tool_calls": [...]}
        """
```

### 3. Use Model-Specific Parser

```python
def _maybe_parse_tool_call(self, response_text: str):
    if self.format == "xml":
        # Use qwen3coder_tool_parser.py
        return self.parser.extract_tool_calls(response_text)
    else:
        # Use JSON parser
        return extract_json_object(response_text)
```

### 4. Use Chat Template

```python
def build_prompt(self, messages):
    if self.tokenizer:
        # Use model's chat template
        return self.tokenizer.apply_chat_template(
            messages,
            tools=self.get_tools(),
            add_generation_prompt=True
        )
    else:
        # Fallback to simple format
        return simple_format(messages)
```

## Benefits of Proper Integration

### For qwen3-coder-30b:
- ✅ Model uses its **native XML format** (what it was trained on)
- ✅ **No confusion** between JSON and XML
- ✅ Uses proper **chat template** with tool descriptions
- ✅ Uses model's **custom parser** with type conversion
- ✅ **Faster** and more accurate tool calling

### For other models (qwen3-32b, gemma):
- ✅ **Falls back gracefully** to JSON format
- ✅ Uses simple chat formatting
- ✅ Still works with default parser

### Overall:
- ✅ **Each model uses its native format**
- ✅ **Automatic** detection and configuration
- ✅ **No manual configuration** needed
- ✅ **Extensible** for future models

## Why This Matters

**Current behavior** (forcing JSON on qwen3-coder):
```
Model generates:
<research_plan>...</research_plan>

{"plan": "...", "tool_calls": [...]}  ← Forced format

{"plan": "...", "tool_calls": [...]}  ← Confusion!

{"plan": "...", "tool_calls": [...]}  ← Multiple!
```

**Correct behavior** (using native XML):
```
Model generates:
<research_plan>...</research_plan>

<tool_call>
<function=web_search>
<parameter=query>query here</parameter>
</function>
</tool_call>
← STOPS (what it was trained to do!)
```

## Action Items

1. [ ] Add model detection to `ArgoAssistant.__init__()`
2. [ ] Create format adapter that switches between XML/JSON
3. [ ] Update system prompts to match model format
4. [ ] Use chat template when available
5. [ ] Use model-specific parser when available
6. [ ] Test with qwen3-coder-30b using XML format
7. [ ] Verify fallback works for models without custom parsers

## Testing Strategy

### Test Case 1: qwen3-coder-30b
- Should use XML format
- Should use qwen3coder_tool_parser.py
- Should use chat_template.jinja
- Should NOT generate multiple tool calls

### Test Case 2: qwen3-32b (no custom files)
- Should use JSON format
- Should use default parser
- Should use simple chat format
- Should still work correctly

### Test Case 3: New model with custom parser
- Should auto-detect parser
- Should use model's native format
- Should work without code changes

## Priority

**HIGH PRIORITY** - This explains why:
1. Model is slow (confusion → multiple attempts)
2. Model generates multiple tool calls (format conflict)
3. Model doesn't stop after generating tools (not using trained format)

Fixing this will likely **solve all three problems at once**.
