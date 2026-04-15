# setup.ps1 — Install RSI framework hooks system-wide (Windows PowerShell)
# ONE-TIME SETUP: Run once on a machine. Hooks then work automatically for every clone.
#
# What it does:
# - Installs hooks to $HOME\.git_template\hooks\ (git's template directory)
# - Every `git clone` or `git init` automatically gets these hooks
#
# To undo: Remove-Item -Recurse -Force $HOME\.git_template\hooks

param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# Find project root (parent of scripts/)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$RSIHooksSrc = Join-Path $ProjectRoot "scripts\git-hooks"
$TemplateHooks = Join-Path $HOME ".git_template\hooks"

Write-Host "RSI Framework — System-wide Setup"
Write-Host ""

# Verify hooks exist
if (-not (Test-Path $RSIHooksSrc -PathType Container)) {
    Write-Host "Error: hooks not found at $RSIHooksSrc"
    Write-Host "Run from within the rsi-framework directory."
    exit 1
}

# Create template directory if needed
if (-not (Test-Path (Join-Path $HOME ".git_template"))) {
    New-Item -ItemType Directory -Path (Join-Path $HOME ".git_template") | Out-Null
    Write-Host "  Created ~\ .git_template\"
}

# Install hooks
$Installed = @()
if (Test-Path $RSIHooksSrc) {
    Get-ChildItem $RSIHooksSrc -File | ForEach-Object {
        $Dest = Join-Path $TemplateHooks $_.Name
        Copy-Item $_.FullName -Destination $Dest -Force
        # Ensure executable (add execute permission)
        $Attribs = Get-Item $Dest
        $Attribs.Attributes = $Attribs.Attributes -bor [System.IO.FileAttributes]::Archive
        $Dest | ForEach-Object { if (-not $_.FullName.EndsWith(".ps1")) { icacls $_.FullName /grant Everyone:RX 2>$null } }
        $Installed += $_.Name
    }
}

Write-Host "  ✓ Hooks installed to ~\ .git_template\hooks\"
Write-Host ""
Write-Host "Installed hooks:"
$Installed | Sort-Object | ForEach-Object { Write-Host "  - $_" }
Write-Host ""

# Verify pre-commit exists
$TestHook = Join-Path $TemplateHooks "pre-commit"
if (Test-Path $TestHook) {
    Write-Host "  ✓ pre-commit is installed"
} else {
    Write-Host "  ✗ pre-commit NOT found"
    exit 1
}

Write-Host ""
Write-Host "✓ Setup complete."
Write-Host ""
Write-Host "After this, every new clone will automatically have these hooks:"
Write-Host "  - pre-commit: runs pre-flight + self-verify before commit"
Write-Host "  - commit-msg: blocks commit without memory update"
Write-Host ""
Write-Host "For existing repos, apply hooks manually:"
Write-Host "  git config core.hooksPath ""$TemplateHooks"""
Write-Host ""
Write-Host "To create a new project with hooks:"
Write-Host "  git clone --template=`"$TemplateHooks`" YOUR_REPO_URL"
Write-Host ""
Write-Host "Or clone normally, then in the new repo:"
Write-Host "  git config core.hooksPath ""$TemplateHooks"""
