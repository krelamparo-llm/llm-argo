# Automatic Model Configuration Detection

## Overview

The Argo Brain Model Registry provides **automatic detection and loading** of model-specific configurations with intelligent fallbacks. When you download a new model, the system will automatically detect and use its custom configurations if available, or gracefully fall back to sensible defaults.

## How It Works

### Detection Process

When you place a model in `/mnt/d/llm/models/<model-name>/`, the registry automatically scans for:

1. **Tokenizer Files**:
   - `tokenizer.json`
   - `tokenizer_config.json`
   - `vocab.json`

2. **Chat Templates**:
   - `chat_template.jinja`
   - `template.jinja`

3. **Tool Parsers**:
   - `*tool_parser.py` (e.g., `qwen3coder_tool_parser.py`)

4. **Configuration Files**:
   - `config.json` (model architecture)
   - `generation_config.json` (generation settings)

5. **Documentation**:
   - `README.md` (extracts recommended parameters)

### Fallback Strategy

If any file is missing, the system uses intelligent defaults:

| Component | If Present | If Missing |
|-----------|-----------|-----------|
| Tokenizer | Use HuggingFace AutoTokenizer | Simple chat formatter |
| Chat Template | Load from .jinja file | Default `<\|im_start\|>` format |
| Tool Parser | Import custom parser | Default XML parser |
| Config | Load from config.json | Use baseline defaults |
| Sampling Params | Extract from README | Qwen3-Coder best practices |

## Usage

### Automatic Configuration

```python
from argo_brain.model_registry import get_global_registry

# Get the global registry (automatically scans models directory)
registry = get_global_registry()

# Auto-configure everything for a model
config = registry.auto_configure("qwen3-coder-30b")

# Access components
tokenizer = config["tokenizer"]          # TokenizerWrapper or None
parser_class = config["parser"]          # Parser class (default or custom)
chat_template = config["chat_template"]  # Jinja template string or None
sampling = config["sampling"]            # Dict of sampling parameters

# Use the parser
parser = parser_class()
tool_calls = parser.extract_tool_calls(llm_output)
```

### Manual Model Inspection

```python
from argo_brain.model_registry import get_global_registry

registry = get_global_registry()

# List all detected models
models = registry.list_models()
print(f"Found models: {models}")
# Output: ['qwen3-coder-30b', 'qwen3-32b', 'gemma-3-1b']

# Get model info
model = registry.get_model("qwen3-coder-30b")
print(f"Has tokenizer: {model.has_tokenizer}")
print(f"Has chat template: {model.has_chat_template}")
print(f"Has custom parser: {model.has_tool_parser}")
print(f"Recommended temp: {model.recommended_temperature}")
```

### Loading Components Individually

```python
from argo_brain.model_registry import get_global_registry

registry = get_global_registry()
model = registry.get_model("qwen3-coder-30b")

# Load tokenizer
if model.has_tokenizer:
    tokenizer = registry.load_tokenizer(model)
    formatted = tokenizer.apply_chat_template(messages)

# Load tool parser
parser_class = registry.load_tool_parser(model)
parser = parser_class()

# Get recommended config
sampling = registry.get_recommended_config(model)
print(f"Recommended settings: {sampling}")
```

## Adding New Models

### Step 1: Download Model

Place your model files in the models directory:

```bash
/mnt/d/llm/models/
├── qwen3-coder-30b/
│   ├── qwen3-coder-30b.gguf
│   ├── tokenizer.json
│   ├── tokenizer_config.json
│   ├── chat_template.jinja
│   ├── qwen3coder_tool_parser.py
│   ├── config.json
│   ├── generation_config.json
│   └── README.md
└── my-new-model/
    ├── model.gguf
    └── README.md  # Optional but recommended
```

### Step 2: Registry Auto-Detects

The registry automatically scans on startup:

```python
# No code needed! Registry scans automatically
from argo_brain.model_registry import get_global_registry

registry = get_global_registry()
# Registry has already scanned and detected all models
```

### Step 3: Use Auto-Configuration

```python
# Just specify the model name
config = registry.auto_configure("my-new-model")

# Everything is configured with intelligent fallbacks!
# - If no tokenizer files: uses simple formatter
# - If no tool parser: uses default XML parser
# - If no README: uses Qwen3-Coder best practices
# - If no chat template: uses default format
```

## Example Scenarios

### Scenario 1: Full-Featured Model (Qwen3-Coder)

Model includes everything:

```
qwen3-coder-30b/
├── tokenizer.json ✓
├── chat_template.jinja ✓
├── qwen3coder_tool_parser.py ✓
├── config.json ✓
└── README.md ✓
```

Result:
- ✅ Uses HuggingFace tokenizer
- ✅ Uses custom chat template
- ✅ Uses custom tool parser
- ✅ Extracts recommended parameters from README

### Scenario 2: Minimal Model (Only GGUF)

Model has only the GGUF file:

```
simple-model/
└── model.gguf
```

Result:
- ✅ Uses simple chat formatter (fallback)
- ✅ Uses default XML tool parser (fallback)
- ✅ Uses Qwen3-Coder sampling defaults (fallback)
- ⚠️ Warning logged: "No tokenizer found, using fallback"

### Scenario 3: Partial Model (Tokenizer Only)

Model has tokenizer but no parser:

```
partial-model/
├── model.gguf
├── tokenizer.json ✓
└── tokenizer_config.json ✓
```

Result:
- ✅ Uses HuggingFace tokenizer
- ✅ Uses default XML tool parser (fallback)
- ✅ Uses Qwen3-Coder sampling defaults (fallback)

## Parameter Extraction from README

The registry automatically extracts recommended parameters from README files:

### Supported Patterns

```markdown
# In README.md

## Best Practices
We recommend using `temperature=0.7`, `top_p=0.8`, `top_k=20`,
`repetition_penalty=1.05`.

## Settings
- Temperature: 0.8
- Top-P: 0.9
- Max tokens: 65536
```

### Extracted Values

```python
model = registry.get_model("model-name")
print(model.recommended_temperature)        # 0.7
print(model.recommended_top_p)             # 0.8
print(model.recommended_top_k)             # 20
print(model.recommended_repetition_penalty) # 1.05
print(model.recommended_max_tokens)        # 65536
```

## Configuration Priority

Settings are applied in this order (later overrides earlier):

1. **Hard-coded defaults** (Qwen3-Coder best practices)
2. **README recommendations** (extracted automatically)
3. **generation_config.json** (if present)
4. **argo.toml** (user configuration)
5. **Environment variables** (highest priority)

Example:

```python
# 1. Default: temperature = 0.7 (Qwen3-Coder)
# 2. README says: temperature = 0.8 (overrides default)
# 3. argo.toml says: temperature = 0.6 (overrides README)
# 4. ENV says: ARGO_LLM_TEMPERATURE=0.9 (overrides everything)

# Final result: temperature = 0.9
```

## Integration with LLMClient

The LLMClient can be initialized with auto-detected configuration:

```python
from argo_brain.model_registry import get_global_registry
from argo_brain.llm_client import LLMClient, ChatMessage

# Auto-configure for a specific model
registry = get_global_registry()
config = registry.auto_configure("qwen3-coder-30b")

# Use recommended sampling parameters
llm_client = LLMClient()
response = llm_client.chat(
    messages=[ChatMessage(role="user", content="Hello")],
    **config["sampling"]  # Automatically applies best settings!
)
```

## Custom Tool Parsers

### Requirements for Custom Parsers

If you have a model-specific tool parser, it should:

1. Be named with `*tool_parser.py` pattern
2. Have a class named with `*ToolParser` or `*Parser`
3. Implement these methods:

```python
class MyCustomToolParser:
    def __init__(self):
        pass

    def extract_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """Extract tool calls from LLM output.

        Returns:
            List of dicts with {"tool": "name", "arguments": {...}}
        """
        pass
```

### Example: Loading Custom Parser

```python
from argo_brain.model_registry import get_global_registry

registry = get_global_registry()
model = registry.get_model("qwen3-coder-30b")

# Dynamically load the custom parser
parser_class = registry.load_tool_parser(model)

# Instantiate and use
parser = parser_class()
results = parser.extract_tool_calls(llm_output)
```

## Environment Configuration

Override auto-detection via environment variables:

```bash
# Force a specific model configuration
export ARGO_MODEL_NAME="qwen3-coder-30b"

# Override tokenizer path
export ARGO_LLM_TOKENIZER_PATH="/custom/path/to/tokenizer"

# Disable auto-detection
export ARGO_DISABLE_AUTO_DETECTION=1

# Custom models root
export ARGO_MODELS_ROOT="/different/path/to/models"
```

## Debugging

### Enable Debug Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("argo_brain.model_registry")
logger.setLevel(logging.DEBUG)

# Now you'll see detailed detection logs
from argo_brain.model_registry import get_global_registry
registry = get_global_registry()
```

### Check What Was Detected

```python
from argo_brain.model_registry import get_global_registry

registry = get_global_registry()

for model_name in registry.list_models():
    model = registry.get_model(model_name)
    print(f"\nModel: {model_name}")
    print(f"  Path: {model.path}")
    print(f"  Has tokenizer: {model.has_tokenizer}")
    print(f"  Has template: {model.has_chat_template}")
    print(f"  Has parser: {model.has_tool_parser}")
    print(f"  Recommended temp: {model.recommended_temperature}")

    if model.has_tool_parser:
        print(f"  Parser path: {model.tool_parser_path}")
```

## Best Practices

### 1. Keep README Files

Always include a README.md with your model that specifies:

```markdown
## Recommended Settings

- temperature=0.7
- top_p=0.8
- top_k=20
- repetition_penalty=1.05
- max_tokens=2048
```

### 2. Include Standard Files

For best results, include:
- `tokenizer.json`, `tokenizer_config.json`
- `config.json`
- `README.md` with recommendations

### 3. Test Auto-Detection

After adding a new model, verify detection:

```python
from argo_brain.model_registry import get_global_registry

registry = get_global_registry()
config = registry.auto_configure("your-model-name")

print("Detected configuration:")
print(f"  Tokenizer: {config['tokenizer'] is not None}")
print(f"  Parser: {config['parser'].__name__}")
print(f"  Sampling: {config['sampling']}")
```

### 4. Handle Missing Files Gracefully

Your code should work even with minimal model files:

```python
# This works with ANY model, even if it only has a GGUF file
config = registry.auto_configure("any-model")

# Always returns valid defaults!
parser = config["parser"]()  # Never None
sampling = config["sampling"]  # Always has values
```

## Troubleshooting

### "Model not found in registry"

```python
# Check what models were detected
registry = get_global_registry()
print(registry.list_models())

# If empty, check your models_root path
from argo_brain.config import CONFIG
print(CONFIG.paths.models_root)
```

### "Failed to load tokenizer"

```bash
# Install transformers if not present
pip install transformers

# Check tokenizer files exist
ls -la /mnt/d/llm/models/your-model/tokenizer*
```

### "Custom parser not loading"

- Verify file name matches `*tool_parser.py`
- Ensure class name contains "ToolParser" or "Parser"
- Check Python syntax in parser file
- Enable debug logging to see import errors

## Summary

The Model Registry provides:

✅ **Automatic detection** of model capabilities
✅ **Intelligent fallbacks** when files are missing
✅ **Zero-config operation** for most scenarios
✅ **Extensible** for custom parsers and templates
✅ **Parameter extraction** from README files
✅ **Unified interface** regardless of model type

**You never have to manually configure model-specific settings** - just place the model in the directory and let the registry handle the rest!
