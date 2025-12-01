# Argo Brain Examples

This directory contains example scripts demonstrating various features of Argo Brain.

## Available Examples

### [model_auto_detect.py](./model_auto_detect.py)

**Automatic Model Configuration Detection**

Demonstrates how Argo Brain automatically detects and configures model-specific settings:

```bash
python examples/model_auto_detect.py
```

**Features shown:**
- Scanning models directory
- Detecting tokenizers, chat templates, and tool parsers
- Extracting recommended parameters from README files
- Auto-configuration with fallbacks
- Tool call parsing demonstration

**Expected output:**
```
======================================================================
Argo Brain - Automatic Model Configuration Detection
======================================================================

🔍 Scanning models directory...

✅ Found 3 model(s):
   - qwen3-coder-30b
   - qwen3-32b
   - gemma-3-1b

======================================================================
Model Details
======================================================================

📦 Model: qwen3-coder-30b
   Path: /mnt/d/llm/models/qwen3-coder-30b
   Components:
      Tokenizer:      ✅ Yes
      Chat Template:  ✅ Yes
      Tool Parser:    ✅ Custom
      Config:         ✅ Yes
   Recommended Settings:
      Temperature:          0.7
      Top-P:                0.8
      Top-K:                20
      Repetition Penalty:   1.05
      Max Tokens:           65,536
...
```

## Running Examples

### Prerequisites

```bash
# Install Argo Brain
cd argo_brain
pip install -e .

# Optional: Install transformers for tokenizer support
pip install transformers
```

### Basic Usage

```bash
# Run model auto-detection
python examples/model_auto_detect.py

# Run with custom models directory
export ARGO_MODELS_ROOT="/custom/path/to/models"
python examples/model_auto_detect.py

# Enable debug logging
export ARGO_LOG_LEVEL=DEBUG
python examples/model_auto_detect.py
```

## Creating Your Own Examples

### Template

```python
#!/usr/bin/env python3
"""Example: Your Feature Name

Brief description of what this example demonstrates.
"""

from argo_brain.config import CONFIG
from argo_brain.llm_client import LLMClient


def main():
    """Your example implementation."""
    print("Hello from Argo Brain!")

    # Your code here...


if __name__ == "__main__":
    main()
```

### Best Practices

1. **Include docstrings** - Explain what the example demonstrates
2. **Add error handling** - Show graceful failure
3. **Use logging** - Help users debug issues
4. **Keep it simple** - Focus on one feature at a time
5. **Include comments** - Explain non-obvious parts

## Additional Resources

- [MODEL_INTEGRATION.md](../docs/MODEL_INTEGRATION.md) - Complete feature guide
- [AUTO_DETECTION.md](../docs/AUTO_DETECTION.md) - Auto-detection documentation
- [IMPLEMENTATION_SUMMARY.md](../docs/IMPLEMENTATION_SUMMARY.md) - Implementation overview

## Contributing

Have an example to share? We'd love to see it!

1. Create a new `.py` file in this directory
2. Follow the template above
3. Test it thoroughly
4. Update this README with a description
5. Submit a pull request

## Common Issues

### "No models found"

**Solution:** Check your models directory path:

```python
from argo_brain.config import CONFIG
print(CONFIG.paths.models_root)
```

Set custom path:
```bash
export ARGO_MODELS_ROOT="/path/to/models"
```

### "Failed to load tokenizer"

**Solution:** Install transformers:

```bash
pip install transformers
```

Or use fallback mode (automatic if transformers not installed).

### "Module not found"

**Solution:** Install Argo Brain in development mode:

```bash
cd argo_brain
pip install -e .
```
