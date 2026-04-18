#!/usr/bin/env python3
"""
api_check.py — Pre-dispatch API verification for task specs.

Catches plan-time API hallucinations before MiniMax burns cycles on
non-existent calls. Reads a task spec, walks the instruction text for
referenced symbols (Class.method, module.func), resolves each against
the modules listed in files_to_read + files_to_modify, and fails if
any reference does not exist.

Skips task_type in {"research", "audit"} — those are fact-finding lanes
where API verification is meaningless.

Usage:
    python3 scripts/api_check.py .rsi/tasks/TASK-NNN.json
    python3 scripts/api_check.py .rsi/tasks/TASK-NNN.json --strict   # also verify kwargs
    python3 scripts/api_check.py .rsi/tasks/TASK-NNN.json --json     # machine-readable

Exit codes:
    0  all referenced symbols exist
    1  one or more references unresolved (would-be hallucinations)
    2  spec malformed or unreadable
"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()

SKIP_TYPES = {"research", "audit"}

REF_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\(")

STDLIB_PREFIXES = {
    "os",
    "sys",
    "re",
    "json",
    "math",
    "time",
    "datetime",
    "pathlib",
    "subprocess",
    "argparse",
    "logging",
    "collections",
    "itertools",
    "functools",
    "typing",
    "dataclasses",
    "enum",
    "abc",
    "io",
    "string",
    "ast",
    "inspect",
    "importlib",
    "shutil",
    "tempfile",
    "uuid",
    "hashlib",
    "base64",
    "asyncio",
    "concurrent",
    "threading",
    "multiprocessing",
    "queue",
    "socket",
    "struct",
    "copy",
    "warnings",
    "weakref",
    "contextlib",
    "operator",
    "random",
    "decimal",
    "fractions",
    "statistics",
    "csv",
    "sqlite3",
    "urllib",
    "http",
    "self",
    "cls",
    "super",
    "print",
    "len",
    "range",
    "list",
    "dict",
    "set",
    "tuple",
    "str",
    "int",
    "float",
    "bool",
    "bytes",
    "object",
    "type",
    "isinstance",
    "hasattr",
    "getattr",
    "setattr",
    "callable",
}


def green(msg: str) -> str:
    return f"\033[92m{msg}\033[0m"


def red(msg: str) -> str:
    return f"\033[91m{msg}\033[0m"


def yellow(msg: str) -> str:
    return f"\033[93m{msg}\033[0m"


def parse_module_symbols(file_path: Path) -> dict:
    """Extract top-level classes (with methods) and functions from a Python file.

    Returns:
        {
            "classes": {ClassName: {method_names: set, has_init_kwargs: list}},
            "functions": {func_name: kwarg_list},
            "imports": {alias: full_module_path},
        }
    """
    out = {"classes": {}, "functions": {}, "imports": {}}
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return out

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = set()
            init_kwargs: list[str] = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.add(item.name)
                    if item.name == "__init__":
                        for arg in item.args.args:
                            if arg.arg != "self":
                                init_kwargs.append(arg.arg)
                        for arg in item.args.kwonlyargs:
                            init_kwargs.append(arg.arg)
            out["classes"][node.name] = {
                "methods": methods,
                "init_kwargs": init_kwargs,
            }
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kwargs = [a.arg for a in node.args.args]
            kwargs.extend(a.arg for a in node.args.kwonlyargs)
            out["functions"][node.name] = kwargs
        elif isinstance(node, ast.Import):
            for n in node.names:
                alias = n.asname or n.name.split(".")[0]
                out["imports"][alias] = n.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for n in node.names:
                alias = n.asname or n.name
                out["imports"][alias] = f"{mod}.{n.name}" if mod else n.name

    return out


def collect_known_symbols(file_paths: list[str]) -> dict:
    """Aggregate class/function symbols across all referenced Python files."""
    aggregated = {"classes": {}, "functions": {}, "method_owners": {}}
    for fp_str in file_paths:
        # strip line-range suffix (delegate.py supports "src/foo.py:100-200")
        clean = fp_str.split(":")[0]
        fp = PROJECT_ROOT / clean
        if not fp.exists() or fp.suffix != ".py":
            continue
        sym = parse_module_symbols(fp)
        for cls_name, cls_info in sym["classes"].items():
            aggregated["classes"][cls_name] = cls_info
            for m in cls_info["methods"]:
                aggregated["method_owners"].setdefault(m, set()).add(cls_name)
        for fn_name, kwargs in sym["functions"].items():
            aggregated["functions"][fn_name] = kwargs
    return aggregated


def extract_references(instruction: str) -> list[tuple[str, str]]:
    """Find all `Owner.attr(` references in instruction text."""
    matches = REF_PATTERN.findall(instruction)
    seen = set()
    out = []
    for owner, attr in matches:
        if owner in STDLIB_PREFIXES:
            continue
        key = (owner, attr)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def verify_references(refs: list[tuple[str, str]], known: dict) -> list[dict]:
    """Return list of unresolved references."""
    problems = []
    classes = known["classes"]
    functions = known["functions"]
    method_owners = known["method_owners"]

    for owner, attr in refs:
        # Case 1: owner is a known class -> attr should be a method
        if owner in classes:
            if attr not in classes[owner]["methods"]:
                problems.append(
                    {
                        "ref": f"{owner}.{attr}",
                        "reason": f"class {owner} has no method '{attr}'",
                    }
                )
            continue

        # Case 2: owner looks like an instance variable (lowercase) — try to
        # match attr against any known method on any class in scope.
        # If attr exists somewhere, accept; else warn.
        if owner[0].islower():
            if attr in method_owners or attr in functions:
                continue
            # also tolerate constructor-style calls e.g. ClassName(...)
            problems.append(
                {
                    "ref": f"{owner}.{attr}",
                    "reason": f"no class in scope defines method '{attr}'",
                }
            )
            continue

        # Case 3: owner is a TitleCase identifier we don't know — likely an
        # imported class from a third-party lib; cannot verify, skip.
        continue

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pre-dispatch API verification for RSI task specs."
    )
    parser.add_argument("spec", help="Path to task spec JSON")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also verify kwargs against inspect.signature (not yet implemented)",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args()

    spec_path = Path(args.spec)
    if not spec_path.is_absolute():
        spec_path = PROJECT_ROOT / spec_path
    if not spec_path.exists():
        print(red(f"spec not found: {spec_path}"))
        return 2

    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(red(f"spec unreadable: {exc}"))
        return 2

    task_type = spec.get("task_type", "code")
    if task_type in SKIP_TYPES:
        msg = f"task_type={task_type} — API check skipped"
        print(json.dumps({"skipped": True, "reason": msg}) if args.json else green(msg))
        return 0

    instruction = spec.get("instruction", "")
    files = list(spec.get("files_to_read", [])) + list(spec.get("files_to_modify", []))

    known = collect_known_symbols(files)
    refs = extract_references(instruction)
    problems = verify_references(refs, known)

    if args.json:
        print(
            json.dumps(
                {
                    "spec": str(spec_path.relative_to(PROJECT_ROOT)),
                    "refs_checked": len(refs),
                    "problems": problems,
                },
                indent=2,
            )
        )
    else:
        print(f"API check: {spec_path.name}")
        print(f"  refs scanned: {len(refs)}")
        if not problems:
            print(green(f"  + all {len(refs)} reference(s) resolve"))
        else:
            print(red(f"  x {len(problems)} unresolved reference(s):"))
            for p in problems:
                print(f"      {yellow(p['ref'])} — {p['reason']}")
            print()
            print("Likely causes:")
            print("  1. API hallucinated by planner (rename method in spec)")
            print("  2. files_to_read missing the module that defines the symbol")
            print("  3. Symbol exists in a third-party lib not visible to this check")
            print("If (3), add the symbol's prefix to STDLIB_PREFIXES allowlist.")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
