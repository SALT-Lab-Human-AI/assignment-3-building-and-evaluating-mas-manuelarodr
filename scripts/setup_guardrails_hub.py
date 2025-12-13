#!/usr/bin/env python3
"""
Setup script for Guardrails AI Hub validators.
This script installs validators from the Guardrails Hub for enhanced safety checks.

Usage:
    python scripts/setup_guardrails_hub.py
"""

import subprocess  # nosec B404 - Safe CLI utility script
import sys
import shutil


def check_guardrails_installed():
    """Check if guardrails CLI is available."""
    if not shutil.which("guardrails"):
        print("❌ Error: guardrails-ai is not installed.")
        print("   Please install it first: pip install guardrails-ai")
        sys.exit(1)
    print("✅ Guardrails AI is installed")
    return True


def configure_guardrails():
    """Configure Guardrails Hub (optional)."""
    print("\nStep 1: Configuring Guardrails Hub...")
    print("   (You can skip API key if not using remote inference)")
    choice = input("   Do you want to configure Guardrails Hub now? (y/n): ").strip().lower()

    if choice == "y":
        try:
            subprocess.run(["guardrails", "configure"], check=True)  # nosec B603, B607 - Safe CLI utility
        except subprocess.CalledProcessError:
            print("   ⚠️  Configuration failed or was cancelled")
    else:
        print("   Skipping configuration. You can run 'guardrails configure' later if needed.")


def install_validators():
    """Install validators from Guardrails Hub."""
    print("\nStep 2: Installing validators from Guardrails Hub...\n")

    validators = [
        "hub://guardrails/toxic_language",
        "hub://guardrails/detect_pii",
        "hub://guardrails/bias_check"
    ]

    for validator in validators:
        print(f"Installing {validator}...")
        try:
            result = subprocess.run(
                ["guardrails", "hub", "install", validator],  # nosec B603, B607 - Safe CLI utility
                capture_output=True,
                text=True,
                check=True
            )
            print(f"   ✅ Successfully installed {validator}")
        except subprocess.CalledProcessError as e:
            print(f"   ⚠️  Warning: Failed to install {validator}")
            print(f"      (may already be installed or not available)")
            if e.stderr:
                print(f"      Error: {e.stderr.strip()}")
        except FileNotFoundError:
            print("   ❌ Error: guardrails command not found")
            sys.exit(1)
        print()


def main():
    """Main setup function."""
    print("=" * 50)
    print("Guardrails AI Hub Validator Setup")
    print("=" * 50)

    check_guardrails_installed()
    configure_guardrails()
    install_validators()

    print("=" * 50)
    print("Setup Complete!")
    print("=" * 50)
    print("\nInstalled validators:")
    print("  - toxic_language: Detects harmful or inappropriate language")
    print("  - detect_pii: Detects personally identifiable information")
    print("  - bias_check: Detects biased language and content")
    print("\nNote: The system includes fallback validation methods, so it will")
    print("      work even if Hub validators are not installed.\n")


if __name__ == "__main__":
    main()
