#!/usr/bin/env python3
"""
shape.py — Compact file skeletons for the overlord.

The overlord burns context reading 1000-line files just to write task specs
that name a class and a few signatures. `shape` does that with ~20 lines:
imports, top-level classes/defs with line numbers and signatures, and
shallow docstring summary.

Output is plain text designed to fit in a single tool result without
pushing real source into the overlord's context window.

Usage:
    python scripts/shape.py src/foo.py                # one file
    python scripts/shape.py src/foo.py scripts/bar.py # many
    python scripts/shape.py --json src/foo.py         # JSON output
    python scripts/shape.py --pattern "scripts/*.py"  # glob

Limits:
    Python (.py)  -> AST-based extraction
    Other         -> first-line summary + line count fallback
"""

import argparse
import ast
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()


def _safe_path(filepath: str) -> Path | None:
    """Resolve under PROJECT_ROOT; refuse anything that escapes."""
    p = Path(filepath)
    if p.is_absolute() or (len(filepath) >= 2 and filepath[1] == ":"):
        return None
    candidate = (PROJECT_ROOT / p).resolve()
    try:
        candidate.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return None
    return candidate


def _shape_python(source: str) -> dict:
    """AST-extract a Python file into a compact dict."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {"error": f"SyntaxError line {exc.lineno}: {exc.msg}"}

    imports: list[str] = []
    symbols: list[dict] = []

    for node in tree.body:
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.append(f"import {n.name}" + (f" as {n.asname}" if n.asname else ""))
        elif isinstance(node, ast.ImportFrom):
            mod = ("." * (node.level or 0)) + (node.module or "")
            names = ", ".join(
                n.name + (f" as {n.asname}" if n.asname else "") for n in node.names
            )
            imports.append(f"from {mod} import {names}")
        elif isinstance(node, ast.ClassDef):
            symbols.append(_shape_class(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(_shape_func(node, prefix=""))
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id.isupper():
                    symbols.append(
                        {"kind": "const", "name": tgt.id, "line": node.lineno}
                    )

    return {"imports": imports, "symbols": symbols}


def _shape_func(node: ast.FunctionDef | ast.AsyncFunctionDef, prefix: str) -> dict:
    args = []
    a = node.args
    for arg in a.args:
        ann = ast.unparse(arg.annotation) if arg.annotation else ""
        args.append(f"{arg.arg}: {ann}" if ann else arg.arg)
    if a.vararg:
        args.append(f"*{a.vararg.arg}")
    for arg in a.kwonlyargs:
        ann = ast.unparse(arg.annotation) if arg.annotation else ""
        args.append(f"{arg.arg}: {ann}" if ann else arg.arg)
    if a.kwarg:
        args.append(f"**{a.kwarg.arg}")
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    kind = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    doc = ast.get_docstring(node)
    short_doc = doc.split("\n", 1)[0].strip() if doc else ""
    return {
        "kind": "method" if prefix else "func",
        "name": (prefix + node.name) if prefix else node.name,
        "line": node.lineno,
        "sig": f"{kind} {node.name}({', '.join(args)}){ret}",
        "doc": short_doc[:80],
    }


def _shape_class(node: ast.ClassDef) -> dict:
    bases = ", ".join(ast.unparse(b) for b in node.bases)
    methods = []
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.append(_shape_func(item, prefix=""))
    doc = ast.get_docstring(node)
    short_doc = doc.split("\n", 1)[0].strip() if doc else ""
    return {
        "kind": "class",
        "name": node.name,
        "line": node.lineno,
        "sig": f"class {node.name}" + (f"({bases})" if bases else ""),
        "doc": short_doc[:80],
        "methods": methods,
    }


def _shape_other(source: str, suffix: str) -> dict:
    """Fallback for non-Python files: first comment line + total lines."""
    lines = source.split("\n")
    first = ""
    for line in lines[:20]:
        s = line.strip()
        if s and not s.startswith(("#!", "//", "/*")):
            first = s.lstrip("# ").lstrip("/").strip()
            break
    return {"summary": first[:120], "lines": len(lines), "suffix": suffix}


def shape_file(filepath: str) -> dict:
    """Return compact shape for one file."""
    safe = _safe_path(filepath)
    if safe is None:
        return {"path": filepath, "error": "path escapes project root"}
    if not safe.exists():
        return {"path": filepath, "error": "not found"}
    if safe.is_dir():
        return {"path": filepath, "error": "is a directory"}

    try:
        source = safe.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return {"path": filepath, "error": f"read failed: {exc}"}

    line_count = source.count("\n") + 1
    out: dict = {"path": filepath, "lines": line_count}

    if safe.suffix == ".py":
        out.update(_shape_python(source))
    else:
        out.update(_shape_other(source, safe.suffix))
    return out


def format_text(shapes: list[dict]) -> str:
    """Render shapes as compact text. Designed to be readable + tiny."""
    out: list[str] = []
    for sh in shapes:
        path = sh.get("path", "?")
        lines = sh.get("lines", "?")
        out.append(f"=== {path}  ({lines} lines)")
        if "error" in sh:
            out.append(f"  ERROR: {sh['error']}")
            continue
        if "summary" in sh:  # non-Python fallback
            out.append(f"  [{sh.get('suffix', '?')}] {sh['summary']}")
            continue
        imports = sh.get("imports", [])
        if imports:
            out.append(f"  imports ({len(imports)}):")
            for imp in imports[:15]:
                out.append(f"    {imp}")
            if len(imports) > 15:
                out.append(f"    ... and {len(imports) - 15} more")
        for sym in sh.get("symbols", []):
            kind = sym["kind"]
            if kind == "const":
                out.append(f"  L{sym['line']:>4}  {sym['name']}")
                continue
            doc = f"  # {sym['doc']}" if sym.get("doc") else ""
            out.append(f"  L{sym['line']:>4}  {sym['sig']}{doc}")
            if kind == "class":
                for m in sym.get("methods", []):
                    mdoc = f"  # {m['doc']}" if m.get("doc") else ""
                    out.append(f"  L{m['line']:>4}      {m['sig']}{mdoc}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compact AST skeletons. Use instead of Read for spec writing."
    )
    parser.add_argument("files", nargs="*", help="File path(s) to shape")
    parser.add_argument("--pattern", help="Glob pattern (e.g. 'scripts/*.py')")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    targets: list[str] = list(args.files)
    if args.pattern:
        targets.extend(str(p.relative_to(PROJECT_ROOT)) for p in PROJECT_ROOT.glob(args.pattern))

    if not targets:
        parser.print_help()
        sys.exit(0)

    shapes = [shape_file(f) for f in targets]
    if args.json:
        print(json.dumps(shapes, indent=2, ensure_ascii=False))
    else:
        print(format_text(shapes), end="")


if __name__ == "__main__":
    main()
