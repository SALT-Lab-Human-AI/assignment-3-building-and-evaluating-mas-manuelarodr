# Setup script for Guardrails AI Hub validators (PowerShell)
# This script installs validators from the Guardrails Hub for enhanced safety checks

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Guardrails AI Hub Validator Setup" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if guardrails-ai is installed
try {
    $null = Get-Command guardrails -ErrorAction Stop
    Write-Host "✅ Guardrails AI is installed" -ForegroundColor Green
} catch {
    Write-Host "❌ Error: guardrails-ai is not installed." -ForegroundColor Red
    Write-Host "   Please install it first: pip install guardrails-ai" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Configure Guardrails Hub (optional)
Write-Host "Step 1: Configuring Guardrails Hub..." -ForegroundColor Yellow
Write-Host "   (You can skip API key if not using remote inference)" -ForegroundColor Gray
$configureChoice = Read-Host "   Do you want to configure Guardrails Hub now? (y/n)"

if ($configureChoice -eq "y" -or $configureChoice -eq "Y") {
    guardrails configure
} else {
    Write-Host "   Skipping configuration. You can run 'guardrails configure' later if needed." -ForegroundColor Gray
}

Write-Host ""
Write-Host "Step 2: Installing validators from Guardrails Hub..." -ForegroundColor Yellow
Write-Host ""

# Validators to install
$validators = @(
    "hub://guardrails/toxic_language",
    "hub://guardrails/detect_pii",
    "hub://guardrails/bias_check"
)

foreach ($validator in $validators) {
    Write-Host "Installing $validator..." -ForegroundColor Cyan
    $result = guardrails hub install $validator 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "   ✅ Successfully installed $validator" -ForegroundColor Green
    } else {
        Write-Host "   ⚠️  Warning: Failed to install $validator (may already be installed or not available)" -ForegroundColor Yellow
    }
    Write-Host ""
}

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Installed validators:" -ForegroundColor Yellow
Write-Host "  - toxic_language: Detects harmful or inappropriate language"
Write-Host "  - detect_pii: Detects personally identifiable information"
Write-Host "  - bias_check: Detects biased language and content"
Write-Host ""
Write-Host "Note: The system includes fallback validation methods, so it will" -ForegroundColor Gray
Write-Host "      work even if Hub validators are not installed." -ForegroundColor Gray
Write-Host ""
