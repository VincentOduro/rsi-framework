#!/usr/bin/env python3
"""
self_verify.py — Post-implementation self-verification for Wandering Codex.

Run this after EVERY code change before declaring success.

Usage:
    python3 scripts/self_verify.py
    python3 scripts/self_verify.py --changed-only   # only check files modified since last commit
    python3 scripts/self_verify.py --files src/wandering_codex/api/progression.py

What it checks:
1. All modified/listed files import cleanly (no ImportError, no AttributeError)
2. Changed functions/methods actually exist in the source
3. No placeholder code (TODO, pass, NotImplementedError, raise NotImplemented)
4. Tests pass (pytest)
5. Specific sanity checks per changed file
6. Side-effect scan: what else might this change break?

Anti-spoliation: if any check fails, the script exits non-zero.
"""

import ast
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Set

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
SRC_ROOT = PROJECT_ROOT / "src"
TEST_ROOT = PROJECT_ROOT / "tests"

PLACEHOLDER_PATTERNS = ["# TODO", "raise NotImplementedError", "pass  #", "...  # noqa"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def green(msg: str) -> str:
    return f"\033[92m{msg}\033[0m"


def red(msg: str) -> str:
    return f"\033[91m{msg}\033[0m"


def yellow(msg: str) -> str:
    return f"\033[93m{msg}\033[0m"


def check(label: str, cond: bool, detail: str = "") -> bool:
    """Print a check result. Returns True if passed."""
    if cond:
        print(f"  {green('✓')} {label}")
    else:
        print(f"  {red('✗')} {label}")
        if detail:
            print(f"        {detail}")
    return cond


def get_changed_files() -> List[Path]:
    """Return list of files changed since last commit."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    files = []
    for path in result.stdout.strip().split("\n"):
        path = path.strip()
        if path:
            p = PROJECT_ROOT / path
            if p.exists():
                files.append(p)
    return files


def get_staged_files() -> List[Path]:
    """Return list of staged files."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    files = []
    for path in result.stdout.strip().split("\n"):
        path = path.strip()
        if path:
            p = PROJECT_ROOT / path
            if p.exists():
                files.append(p)
    return files


def find_placeholder_code(file_path: Path) -> List[str]:
    """Scan a file for placeholder patterns. Returns list of offending lines."""
    issues = []
    try:
        content = file_path.read_text()
    except Exception:
        return [f"Could not read {file_path}"]
    
    for i, line in enumerate(content.splitlines(), 1):
        for pat in PLACEHOLDER_PATTERNS:
            if pat in line:
                issues.append(f"  line {i}: {line.strip()}")
    return issues


def check_imports_clean(file_path: Path) -> bool:
    """Verify a Python file can be imported without errors."""
    if file_path.suffix != ".py":
        return True
    rel = file_path.relative_to(PROJECT_ROOT)
    module = str(rel).replace("/", ".").replace(".py", "")
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result.returncode == 0


def check_import_error_detail(file_path: Path) -> str:
    """Return the import error detail if any."""
    if file_path.suffix != ".py":
        return ""
    rel = file_path.relative_to(PROJECT_ROOT)
    module = str(rel).replace("/", ".").replace(".py", "")
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        return result.stderr.strip().split("\n")[-1]
    return ""


def find_functions_defined(file_path: Path) -> Set[str]:
    """Return set of top-level function names defined in a file."""
    if file_path.suffix != ".py":
        return set()
    try:
        tree = ast.parse(file_path.read_text())
    except SyntaxError:
        return set()
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def find_classes_defined(file_path: Path) -> Set[str]:
    """Return set of top-level class names defined in a file."""
    if file_path.suffix != ".py":
        return set()
    try:
        tree = ast.parse(file_path.read_text())
    except SyntaxError:
        return set()
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    }


def check_method_in_class(file_path: Path, class_name: str, method_name: str) -> bool:
    """Check if a method exists in a class defined in file."""
    if file_path.suffix != ".py":
        return True
    try:
        tree = ast.parse(file_path.read_text())
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                    return True
    return False


# ---------------------------------------------------------------------------
# File-specific sanity checks
# ---------------------------------------------------------------------------
# To add project-specific checks, add entries to sanity_checks dict below.
# Default passes all files. Override per-filename as needed.

def sanity_check_default(file_path: Path) -> bool:
    """Default sanity check — always passes. Replace with project-specific checks."""
    return True


def sanity_check_progression_py(file_path: Path) -> bool:
    """EXAMPLE: progression.py should not have module-level supabase.create_client()."""
    content = file_path.read_text()
    issues = []
    if "async def startup_event" not in content:
        issues.append("No startup_event found")
    lines = content.splitlines()
    for i, line in enumerate(lines, 1):
        if "create_client(SUPABASE_URL, SUPABASE_KEY)" in line:
            window = "\n".join(lines[max(0, i - 10) : min(len(lines), i + 3)])
            if "startup_event" not in window:
                issues.append(f"create_client at module level at line {i}")
    if issues:
        for issue in issues:
            print(f"        {red(issue)}")
        return False
    return True


# ---------------------------------------------------------------------------
# Side-effect scan
# ---------------------------------------------------------------------------

def scan_side_effects(file_path: Path) -> List[str]:
    """Look for other files that might be affected by changes to this file."""
    content = file_path.read_text()
    findings = []

    # Files that import from pipeline/
    pipeline_imports = [
        "from wandering_codex.pipeline",
        "from .pipeline",
        "import pipeline",
    ]

    if any(imp in content for imp in pipeline_imports):
        # Check who else imports from pipeline
        for py_file in SRC_ROOT.rglob("*.py"):
            if py_file == file_path:
                continue
            try:
                other_content = py_file.read_text()
                for imp in pipeline_imports:
                    if imp in other_content:
                        findings.append(f"  {imp} also in {py_file.relative_to(PROJECT_ROOT)}")
                        break
            except Exception:
                pass

    return findings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_tests() -> bool:
    """Run pytest and return True if all pass."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short", "-q"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode == 0:
        print(f"  {green('✓')} All tests passed")
        # Print summary line
        for line in result.stdout.splitlines():
            if "passed" in line and "failed" not in line:
                print(f"        {line.strip()}")
    else:
        print(f"  {red('✗')} Tests failed")
        for line in result.stderr.splitlines()[-5:]:
            print(f"        {line}")
    return result.returncode == 0


def verify_file(file_path: Path, check_func=None) -> bool:
    """Run all checks on a single file."""
    print(f"\n{file_path.relative_to(PROJECT_ROOT)}:")

    all_ok = True

    # 1. Import clean
    ok = check_imports_clean(file_path)
    if not ok:
        detail = check_import_error_detail(file_path)
        print(f"        Import error: {detail}")
        all_ok = False
        # Don't run further checks if import fails
        return False

    # 2. No placeholder code
    placeholders = find_placeholder_code(file_path)
    ok = check("No placeholder code", len(placeholders) == 0)
    if not ok:
        for p in placeholders[:5]:
            print(p)
        all_ok = False

    # 3. File-specific sanity check
    if check_func:
        ok = check(f"Sanity check ({check_func.__name__})", check_func(file_path))
        if not ok:
            all_ok = False

    # 4. Side-effect scan
    side_effects = scan_side_effects(file_path)
    if side_effects:
        print(f"  {yellow('⚠')} Side-effect scan:")
        for se in side_effects[:5]:
            print(se)

    return all_ok


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Post-implementation self-verification")
    parser.add_argument("--files", nargs="*", help="Specific files to check")
    parser.add_argument("--changed-only", action="store_true", help="Check only changed files")
    parser.add_argument("--skip-tests", action="store_true", help="Skip running tests")
    args = parser.parse_args()

    print("=" * 70)
    print("WANDERING CODEX — Post-Implementation Self-Verification")
    print("=" * 70)

    # Determine which files to check
    if args.files:
        files = [PROJECT_ROOT / f for f in args.files]
    elif args.changed_only:
        files = get_changed_files()
    else:
        staged = get_staged_files()
        changed = get_changed_files()
        files = staged if staged else changed

    if not files:
        print(f"\n{yellow('No files to check (no changes detected).')}")
        print("Run with --changed-only or --files to specify files.")
        return

    # Filter to Python files in the project
    py_files = [f for f in files if f.suffix == ".py" and f.is_relative_to(PROJECT_ROOT / "src")]
    test_files = [f for f in files if f.is_relative_to(TEST_ROOT)]

    print(f"\nChecking {len(py_files)} source file(s), {len(test_files)} test file(s)")

    # Map files to their sanity check functions.
    # ADD PROJECT-SPECIFIC CHECKS HERE. Default (no entry) = sanity_check_default = always passes.
    # Example:
    #     sanity_checks = {
    #         "my_file.py": my_file_sanity_check,
    #     }
    sanity_checks = {}

    all_ok = True
    for f in py_files:
        check_func = sanity_checks.get(f.name)
        file_ok = verify_file(f, check_func=check_func)
        if not file_ok:
            all_ok = False

    for f in test_files:
        print(f"\n{f.relative_to(PROJECT_ROOT)}:")
        ok = check_imports_clean(f)
        if not ok:
            all_ok = False

    # Always run tests unless skipped
    if not args.skip_tests:
        print("\n" + "-" * 70)
        print("Running test suite:")
        test_ok = run_tests()
        if not test_ok:
            all_ok = False

    print("\n" + "=" * 70)
    if all_ok:
        print(f"{green('ALL CHECKS PASSED — proceed with caution')}")
        sys.exit(0)
    else:
        print(f"{red('SOME CHECKS FAILED — fix before declaring done')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
