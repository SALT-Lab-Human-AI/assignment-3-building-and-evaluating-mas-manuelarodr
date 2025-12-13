#!/bin/bash
# Setup script for Guardrails AI Hub validators
# This script installs validators from the Guardrails Hub for enhanced safety checks

echo "=========================================="
echo "Guardrails AI Hub Validator Setup"
echo "=========================================="
echo ""

# Check if guardrails-ai is installed
if ! command -v guardrails &> /dev/null; then
    echo "❌ Error: guardrails-ai is not installed."
    echo "   Please install it first: pip install guardrails-ai"
    exit 1
fi

echo "✅ Guardrails AI is installed"
echo ""

# Configure Guardrails Hub (optional)
echo "Step 1: Configuring Guardrails Hub..."
echo "   (You can skip API key if not using remote inference)"
read -p "   Do you want to configure Guardrails Hub now? (y/n): " configure_choice

if [[ $configure_choice == "y" || $configure_choice == "Y" ]]; then
    guardrails configure
else
    echo "   Skipping configuration. You can run 'guardrails configure' later if needed."
fi

echo ""
echo "Step 2: Installing validators from Guardrails Hub..."
echo ""

# Validators to install
VALIDATORS=(
    "hub://guardrails/toxic_language"
    "hub://guardrails/detect_pii"
    "hub://guardrails/bias_check"
)

for validator in "${VALIDATORS[@]}"; do
    echo "Installing $validator..."
    if guardrails hub install "$validator"; then
        echo "   ✅ Successfully installed $validator"
    else
        echo "   ⚠️  Warning: Failed to install $validator (may already be installed or not available)"
    fi
    echo ""
done

echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Installed validators:"
echo "  - toxic_language: Detects harmful or inappropriate language"
echo "  - detect_pii: Detects personally identifiable information"
echo "  - bias_check: Detects biased language and content"
echo ""
echo "Note: The system includes fallback validation methods, so it will"
echo "      work even if Hub validators are not installed."
echo ""
