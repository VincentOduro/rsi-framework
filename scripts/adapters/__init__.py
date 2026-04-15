"""RSI Framework — AI Model Adapters

This package contains integration adapters for different AI models.
Each adapter translates model-specific hook mechanisms into calls
to the core RSI hook logic in scripts/hooks.py.

Usage:
    from scripts.adapters.shell_integrator import ShellIntegrator
    integrator = ShellIntegrator()
    integrator.record_read("src/main.py")
"""

from scripts.adapters.shell_integrator import ShellIntegrator

__all__ = ["ShellIntegrator"]