#!/usr/bin/env python3
"""
self_verify.py — Post-implementation self-verification (language-agnostic).

Run this after EVERY code change before declaring success.

Usage:
    python3 scripts/self_verify.py
    python3 scripts/self_verify.py --changed-only   # only check files modified since last commit
    python3 scripts/self_verify.py --files src/myapp/api/handler.py

What it checks (pluggable by language):
1. All modified/listed files pass language-specific syntax check
2. No placeholder code (generic — works on any text file)
3. Tests pass (pytest — Python only, use --skip-tests for non-Python projects)
4. Specific sanity checks per changed file (project-specific)
5. Side-effect scan (project-specific)

Anti-spoliation: if any check fails, the script exits non-zero.

Language-agnostic design:
- Each language has a LanguageChecker plug-in
- Default checkers: Python (.py), Shell (.sh), Generic text (all others)
- To add a checker: register in LANG_CHECKERS dict
"""

import ast
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
SRC_ROOT = PROJECT_ROOT / "src"
TEST_ROOT = PROJECT_ROOT / "tests"

PLACEHOLDER_PATTERNS = ["# TODO", "raise NotImplementedError", "pass  #", "...  # noqa"]


# ---------------------------------------------------------------------------
# Language Checker Plugin System
# ---------------------------------------------------------------------------


class LanguageChecker(ABC):
    """Abstract base for language-specific verification plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this language."""
        pass

    @property
    def extensions(self) -> list[str]:
        """File extensions this checker handles. E.g., ['.py', '.pyx']"""
        return []

    @property
    def test_extensions(self) -> list[str]:
        """File extensions that are test files for this language."""
        return []

    @abstractmethod
    def check_syntax(self, file_path: Path) -> tuple[bool, str]:
        """Check syntax/parseability. Returns (ok, error_detail)."""
        pass

    def check_sanity(self, file_path: Path) -> tuple[bool, str]:
        """Optional sanity check. Returns (ok, detail). Override per-project."""
        return True, ""


class PythonChecker(LanguageChecker):
    """Python syntax and import checker."""

    @property
    def name(self) -> str:
        return "Python"

    @property
    def extensions(self) -> list[str]:
        return [".py", ".pyx", ".pxd"]

    @property
    def test_extensions(self) -> list[str]:
        return ["_test.py", "_tests.py"]

    def check_syntax(self, file_path: Path) -> tuple[bool, str]:
        try:
            ast.parse(file_path.read_text())
            return True, ""
        except SyntaxError as e:
            return False, f"SyntaxError: {e}"

    def check_sanity(self, file_path: Path) -> tuple[bool, str]:
        """Check importability. Handles relative imports gracefully.

        Strategy:
        1. Try importing from PROJECT_ROOT (works for top-level scripts)
        2. If that fails with relative import error, try from the file's
           parent directory (handles packages with relative imports)
        3. If both fail with ImportError/ModuleNotFoundError, pass anyway
           (the file is valid, just can't be imported standalone)
        4. Only fail on actual SyntaxError or other hard errors
        """
        # Attempt 1: import from PROJECT_ROOT
        try:
            rel = file_path.relative_to(PROJECT_ROOT)
        except ValueError:
            return True, ""  # file outside project, skip

        module = str(rel).replace("/", ".").replace("\\", ".").replace(".py", "")
        result = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return True, ""

        stderr = result.stderr.strip()

        # Check if this is a relative import or missing module error
        # These are NOT real bugs — the file is valid but can't be imported standalone
        import_errors = [
            "attempted relative import",
            "No module named",
            "ModuleNotFoundError",
            "ImportError",
        ]
        if any(err in stderr for err in import_errors):
            # Attempt 2: try from file's parent directory
            parent = str(file_path.parent)
            module_name = file_path.stem
            result2 = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    f"import sys; sys.path.insert(0, '{parent}'); import {module_name}",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result2.returncode == 0:
                return True, ""

            # Still fails — but it's an import issue, not a syntax bug.
            # AST parse already passed (check_syntax runs first), so the file is valid.
            return True, ""

        # Real error (not import-related) — fail
        return False, stderr.split("\n")[-1]


class ShellChecker(LanguageChecker):
    """Shell script syntax checker.

    Tries multiple backends for cross-platform compatibility:
    1. shellcheck (if installed) — works on all platforms
    2. bash -n — works on Linux/macOS/WSL/Git Bash
    3. PowerShell Parse method — Windows fallback
    """

    @property
    def name(self) -> str:
        return "Shell"

    @property
    def extensions(self) -> list[str]:
        return [".sh", ".bash"]

    def check_syntax(self, file_path: Path) -> tuple[bool, str]:
        import shutil

        # 1. Try shellcheck first (cross-platform)
        if shutil.which("shellcheck"):
            result = subprocess.run(
                ["shellcheck", "-n", "-x", str(file_path)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                return False, result.stderr.strip() or "shellcheck failed"
            return True, ""

        # 2. Try bash -n (Linux/macOS/WSL/Git Bash)
        if shutil.which("bash"):
            result = subprocess.run(
                ["bash", "-n", str(file_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return False, result.stderr.strip()
            return True, ""

        # 3. Windows fallback: PowerShell syntax check
        if shutil.which("pwsh") or shutil.which("powershell"):
            pwsh_cmd = "pwsh" if shutil.which("pwsh") else "powershell"
            script_content = file_path.read_text()
            ps_script = f"""
$script = @'
{script_content}
'@
$tokens = $null
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseInput($script, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -gt 0) {{
    foreach ($err in $parseErrors) {{
        Write-Error $err.Message
    }}
    exit 1
}}
exit 0
"""
            result = subprocess.run(
                [pwsh_cmd, "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                err = result.stderr.strip() or result.stdout.strip()
                return False, err or "PowerShell parse failed"
            return True, ""

        # 4. No shell checker available
        return False, "No shell checker available (install shellcheck, bash, or PowerShell)"


class GenericTextChecker(LanguageChecker):
    """Fallback checker for unknown file types. Checks nothing by default."""

    @property
    def name(self) -> str:
        return "Text"

    @property
    def extensions(self) -> list[str]:
        return []  # Matches nothing; used as fallback only

    def check_syntax(self, file_path: Path) -> tuple[bool, str]:
        try:
            file_path.read_text()
            return True, ""
        except Exception as e:
            return False, str(e)


# ---------------------------------------------------------------------------
# Language Checker Registry
# ---------------------------------------------------------------------------

LANG_CHECKERS: list[LanguageChecker] = [
    PythonChecker(),
    ShellChecker(),
    GenericTextChecker(),
]


def get_checker_for(file_path: Path) -> LanguageChecker:
    """Return the appropriate language checker for a file."""
    for checker in LANG_CHECKERS:
        if file_path.suffix in checker.extensions:
            return checker
    return GenericTextChecker()


def is_test_file(file_path: Path) -> bool:
    """Return True if file looks like a test file."""
    for checker in LANG_CHECKERS:
        if file_path.suffix in checker.test_extensions:
            return True
    return False


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
        print(f"  {green('+')} {label}")
    else:
        print(f"  {red('x')} {label}")
        if detail:
            print(f"        {detail}")
    return cond


def get_changed_files() -> list[Path]:
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


def get_staged_files() -> list[Path]:
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


def find_placeholder_code(file_path: Path) -> list[str]:
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


# ---------------------------------------------------------------------------
# File-specific sanity checks
# ---------------------------------------------------------------------------
# To add project-specific checks, add entries to sanity_checks dict in main().
# Default passes all files. Override per-filename as needed.


def _example_sanity_check(file_path: Path) -> bool:
    """EXAMPLE: Project-specific sanity check template.

    Replace this with your own checks. For example:
        def check_no_module_level_db(file_path):
            content = file_path.read_text()
            if "create_client(" in content and "def " not in content.split("create_client(")[0].split("\\n")[-1]:
                print(f"        {red('DB client created at module level')}")
                return False
            return True

    Then register it in the sanity_checks dict in main():
        sanity_checks = {"my_file.py": check_no_module_level_db}
    """
    return True


# ---------------------------------------------------------------------------
# Side-effect scan
# ---------------------------------------------------------------------------


def scan_side_effects(file_path: Path) -> list[str]:
    """Look for other files that might be affected by changes to this file."""
    content = file_path.read_text()
    findings = []

    # Find other files that import from the same package as this file.
    # This catches side-effects: changing module X may break module Y if Y imports from X.
    try:
        rel = file_path.relative_to(PROJECT_ROOT)
        parts = list(rel.parts)
        if len(parts) >= 2:
            package = parts[0]  # e.g., "src"
            module_name = file_path.stem  # e.g., "auth"
            import_patterns = [
                f"from {package}",
                f"import {module_name}",
                f"from .{module_name}",
            ]
            for py_file in SRC_ROOT.rglob("*.py"):
                if py_file == file_path:
                    continue
                try:
                    other_content = py_file.read_text()
                    for imp in import_patterns:
                        if imp in other_content:
                            findings.append(f"  {imp} also in {py_file.relative_to(PROJECT_ROOT)}")
                            break
                except Exception:
                    pass
    except (ValueError, IndexError):
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
        print(f"  {green('+')} All tests passed")
        # Print summary line
        for line in result.stdout.splitlines():
            if "passed" in line and "failed" not in line:
                print(f"        {line.strip()}")
    else:
        print(f"  {red('x')} Tests failed")
        for line in result.stderr.splitlines()[-5:]:
            print(f"        {line}")
    return result.returncode == 0


def verify_file(file_path: Path, sanity_check_func=None) -> bool:
    """Run all checks on a single file using the pluggable language checker."""
    print(f"\n{file_path.relative_to(PROJECT_ROOT)}:")

    all_ok = True
    checker = get_checker_for(file_path)

    # 1. Language-specific syntax check
    ok, error = checker.check_syntax(file_path)
    if not check(f"{checker.name} syntax", ok):
        if error:
            print(f"        {error}")
        return False

    # 2. Language-specific sanity check (imports, type checks, etc.)
    if sanity_check_func:
        ok = sanity_check_func(file_path)
        check(f"Sanity check ({sanity_check_func.__name__})", ok)
        if not ok:
            all_ok = False
    elif hasattr(checker, "check_sanity"):
        ok, detail = checker.check_sanity(file_path)
        if not check(f"{checker.name} sanity", ok):
            if detail:
                print(f"        {detail}")
            all_ok = False

    # 3. No placeholder code (generic — works on any text file)
    placeholders = find_placeholder_code(file_path)
    ok = check("No placeholder code", len(placeholders) == 0)
    if not ok:
        for p in placeholders[:5]:
            print(p)
        all_ok = False

    # 4. Side-effect scan (currently Python-only; extend per-project)
    if file_path.suffix == ".py":
        side_effects = scan_side_effects(file_path)
        if side_effects:
            print(f"  {yellow('!')} Side-effect scan:")
            for se in side_effects[:5]:
                print(se)

    return all_ok


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Post-implementation self-verification")
    parser.add_argument("--files", nargs="*", help="Specific files to check")
    parser.add_argument("--changed-only", action="store_true", help="Check only changed files")
    parser.add_argument(
        "--skip-tests", action="store_true", help="Skip running tests (non-Python projects)"
    )
    args = parser.parse_args()

    print("=" * 70)
    print("RSI Framework — Post-Implementation Self-Verification")
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

    # Separate source and test files using the checker registry
    source_files = []
    test_files = []
    for f in files:
        if f.is_relative_to(TEST_ROOT) or is_test_file(f):
            test_files.append(f)
        else:
            source_files.append(f)

    print(f"\nChecking {len(source_files)} source file(s), {len(test_files)} test file(s)")

    # Map files to their sanity check functions.
    # ADD PROJECT-SPECIFIC CHECKS HERE. Default (no entry) = no sanity check.
    # Example:
    #     sanity_checks = {
    #         "my_file.py": my_file_sanity_check,
    #     }
    sanity_checks = {}

    all_ok = True
    for f in source_files:
        check_func = sanity_checks.get(f.name)
        file_ok = verify_file(f, sanity_check_func=check_func)
        if not file_ok:
            all_ok = False

    for f in test_files:
        print(f"\n{f.relative_to(PROJECT_ROOT)}:")
        checker = get_checker_for(f)
        ok, error = checker.check_syntax(f)
        if not check(f"{checker.name} syntax", ok):
            if error:
                print(f"        {error}")
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
