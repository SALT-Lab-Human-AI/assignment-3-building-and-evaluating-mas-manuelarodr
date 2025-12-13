# Guardrails AI Hub Setup

This document explains how to set up Guardrails AI Hub validators for enhanced safety checks.

## Quick Setup

The system includes fallback validation methods, so it will work without Hub validators. However, installing Hub validators provides more robust safety checks.

### Option 1: Use the Setup Script (Recommended)

**For Linux/Mac:**
```bash
bash scripts/setup_guardrails_hub.sh
```

**For Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_guardrails_hub.ps1
```

**Cross-platform (Python):**
```bash
python scripts/setup_guardrails_hub.py
```

### Option 2: Manual Setup

1. **Configure Guardrails Hub** (optional):
   ```bash
   guardrails configure
   ```
   - You can skip the API key if not using remote inference
   - Say "No" to remote inferencing if you have your own API keys (Groq/OpenAI)

2. **Install validators:**
   ```bash
   guardrails hub install hub://guardrails/toxic_language
   guardrails hub install hub://guardrails/detect_pii
   guardrails hub install hub://guardrails/bias_check
   ```

## What Each Validator Does

- **toxic_language**: Detects harmful or inappropriate language in inputs and outputs
- **detect_pii**: Detects personally identifiable information (emails, phone numbers, SSNs, etc.)
- **bias_check**: Detects biased language and content in outputs

## Fallback Validators

The system includes fallback validation methods that work without Hub installation:

- **Prompt injection detection**: Pattern-based detection of common injection attempts
- **Relevance checking**: Keyword-based checking for topic "Ethical AI in Education"

## Troubleshooting

- If validators fail to install, the system will use fallback methods
- Check that `guardrails-ai` is installed: `pip install guardrails-ai`
- Verify installation: `python -c "from guardrails.hub import ToxicLanguage; print('OK')"`

## More Information

- [Guardrails AI Hub Documentation](https://docs.guardrailsai.com/)
- [Guardrails AI Hub Website](https://hub.guardrailsai.com)
