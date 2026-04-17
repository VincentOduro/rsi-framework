#!/usr/bin/env python3
"""
5-Whys Root Cause Analysis — structured problem investigation.

Toyota Principle 14: Hansei — reflection after failure.

When a defect is found, "what could prove this wrong" is not enough.
You need structured root cause analysis to find the systemic issue
and create a countermeasure that prevents recurrence.

This is the difference between fixing a bug and fixing the system.

Storage: .memory/technical/root-causes.md (append-only markdown)
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
MEMORY_ROOT = PROJECT_ROOT / ".memory"
ROOT_CAUSES_FILE = MEMORY_ROOT / "technical" / "root-causes.md"
FAIL_INDEX_FILE = MEMORY_ROOT / "technical" / "FAIL-index.md"


def _ensure_file() -> None:
    ROOT_CAUSES_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not ROOT_CAUSES_FILE.exists():
        ROOT_CAUSES_FILE.write_text("# Root Cause Analyses (5-Whys)\n\n", encoding="utf-8")


def _load_analyses() -> list[dict]:
    """Parse existing analyses from root-causes.md."""
    if not ROOT_CAUSES_FILE.exists():
        return []
    content = ROOT_CAUSES_FILE.read_text(encoding="utf-8")
    analyses = []
    parts = content.split("\n## RCA-")
    for part in parts[1:]:
        lines = part.strip().split("\n")
        if not lines:
            continue
        header = lines[0]
        rca_id = f"RCA-{header.split(':')[0].strip()}"
        title = header.split(":", 1)[1].strip() if ":" in header else header

        whys = []
        countermeasure = ""
        fail_id = ""
        status = "open"

        for line in lines[1:]:
            stripped = line.strip()
            if stripped.startswith("**Why"):
                why_text = stripped.split("**", 2)[-1].strip().lstrip(": ")
                whys.append(why_text)
            elif stripped.startswith("**Countermeasure:**"):
                countermeasure = stripped.replace("**Countermeasure:**", "").strip()
            elif stripped.startswith("**FAIL-ID:**"):
                fail_id = stripped.replace("**FAIL-ID:**", "").strip()
            elif stripped.startswith("**Status:**"):
                status = stripped.replace("**Status:**", "").strip().lower()

        analyses.append(
            {
                "id": rca_id,
                "title": title,
                "whys": whys,
                "countermeasure": countermeasure,
                "fail_id": fail_id,
                "status": status,
            }
        )
    return analyses


def _next_id() -> str:
    analyses = _load_analyses()
    max_num = 0
    for a in analyses:
        m = re.search(r"RCA-(\d+)", a.get("id", ""))
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"RCA-{max_num + 1:03d}"


def _next_fail_id() -> str:
    """Get next FAIL-ID from the FAIL-index."""
    if not FAIL_INDEX_FILE.exists():
        return "FAIL-001"
    content = FAIL_INDEX_FILE.read_text(encoding="utf-8")
    max_num = 0
    for m in re.finditer(r"FAIL-(\d+)", content):
        max_num = max(max_num, int(m.group(1)))
    return f"FAIL-{max_num + 1:03d}"


# ---------------------------------------------------------------------------
# Analysis creation
# ---------------------------------------------------------------------------


def create_analysis(
    title: str,
    whys: list[str],
    countermeasure: str,
    defect_description: str = "",
    task: str = "",
    files: list[str] | None = None,
    add_to_fail_index: bool = False,
) -> dict:
    """Create a structured 5-Whys analysis.

    Args:
        title: Short description of the defect
        whys: List of 3-5 "why" answers, each building on the previous
        countermeasure: Specific action to prevent recurrence
        defect_description: Detailed description of what went wrong
        task: Related task ID
        files: Related files
        add_to_fail_index: If True, also creates a FAIL-index entry
    """
    _ensure_file()

    rca_id = _next_id()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    fail_id = ""

    if add_to_fail_index:
        fail_id = _next_fail_id()
        _add_to_fail_index(fail_id, title, countermeasure)

    # Build the analysis entry
    entry = f"""
## {rca_id}: {title}

**Date:** {timestamp}
**Task:** {task or "(none)"}
**Files:** {", ".join(files) if files else "(none)"}
**Status:** open

**Defect:** {defect_description or title}

"""
    for i, why in enumerate(whys, 1):
        entry += f"**Why {i}?** {why}\n"

    entry += f"""
**Root cause:** {whys[-1] if whys else "(not identified)"}

**Countermeasure:** {countermeasure}
"""
    if fail_id:
        entry += f"**FAIL-ID:** {fail_id}\n"

    entry += "\n---\n"

    # Append to file
    content = ROOT_CAUSES_FILE.read_text(encoding="utf-8")
    ROOT_CAUSES_FILE.write_text(content.rstrip() + "\n" + entry, encoding="utf-8")

    # Record in metrics
    try:
        from scripts.metrics import record_defect

        record_defect(task=task, severity="HIGH", found_by="5-whys", description=title)
    except ImportError:
        pass

    return {
        "id": rca_id,
        "title": title,
        "whys": whys,
        "countermeasure": countermeasure,
        "fail_id": fail_id,
        "status": "open",
    }


def _add_to_fail_index(fail_id: str, failure_mode: str, preventive_rule: str) -> None:
    """Add an entry to the FAIL-index."""
    FAIL_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not FAIL_INDEX_FILE.exists():
        FAIL_INDEX_FILE.write_text(
            """# FAIL-index — Behavioral Failure Modes

| ID | Failure Mode | Preventive Rule | Times Cited | Last Cited |
|---|---|---|---|---|
""",
            encoding="utf-8",
        )

    content = FAIL_INDEX_FILE.read_text(encoding="utf-8")
    today = datetime.now().strftime("%Y-%m-%d")
    new_row = f"| {fail_id} | {failure_mode} | {preventive_rule} | 0 | {today} |\n"

    # Append before the end of the table
    if content.rstrip().endswith("|"):
        content = content.rstrip() + "\n" + new_row
    else:
        content = content.rstrip() + "\n" + new_row

    FAIL_INDEX_FILE.write_text(content, encoding="utf-8")


def close_analysis(rca_id: str, verified: bool = False, notes: str = "") -> bool:
    """Mark an analysis as closed (countermeasure implemented)."""
    if not ROOT_CAUSES_FILE.exists():
        return False
    content = ROOT_CAUSES_FILE.read_text(encoding="utf-8")
    old = "**Status:** open"
    status = "verified" if verified else "closed"
    # Find the right RCA section and update its status
    pattern = rf"(## {rca_id}:.*?)\*\*Status:\*\* open"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        content = content[: match.end() - len("open")] + status + content[match.end() :]
        if notes:
            content = content.replace(
                f"**Status:** {status}",
                f"**Status:** {status}\n**Closure notes:** {notes}",
                1,
            )
        ROOT_CAUSES_FILE.write_text(content, encoding="utf-8")
        return True
    return False


# ---------------------------------------------------------------------------
# Interactive 5-Whys
# ---------------------------------------------------------------------------


def interactive_five_whys() -> dict | None:
    """Guide the user through a 5-Whys analysis interactively."""
    from scripts.colors import cyan, green, header, red, yellow

    print(header("5-WHYS ROOT CAUSE ANALYSIS"))
    print("\nThis analysis traces a defect to its systemic root cause.")
    print("Each 'Why?' should dig deeper than the previous answer.\n")

    title = input("Defect title (short): ").strip()
    if not title:
        print(f"{red('Cancelled — title required')}")
        return None

    description = input("Detailed description: ").strip()
    task = input("Related task ID (optional): ").strip()
    files_str = input("Related files (comma-separated, optional): ").strip()
    files = [f.strip() for f in files_str.split(",") if f.strip()] if files_str else []

    print(f"\n{yellow('Now answer WHY this defect occurred.')}")
    print("Each answer should explain the PREVIOUS answer.\n")

    whys = []
    for i in range(1, 6):
        if i == 1:
            prompt = f"Why did '{title}' happen?"
        else:
            prompt = f"Why? (building on: '{whys[-1][:50]}...')"

        print(f"{cyan(f'Why {i}?')} {prompt}")
        answer = input("  > ").strip()
        if not answer:
            if i < 3:
                print(f"{red('Minimum 3 whys required. Keep going.')}")
                answer = input("  > ").strip()
                if not answer:
                    break
            else:
                break
        whys.append(answer)

        if i >= 3:
            go_deeper = input("  Go deeper? (y/N): ").strip().lower()
            if go_deeper != "y":
                break

    if len(whys) < 3:
        print(f"{red('Analysis abandoned — minimum 3 whys required')}")
        return None

    print(f"\n{yellow('Root cause identified:')} {whys[-1]}")
    countermeasure = input("\nCountermeasure (specific action to prevent recurrence): ").strip()
    if not countermeasure:
        print(f"{red('Countermeasure required')}")
        return None

    add_fail = input("Add to FAIL-index? (y/N): ").strip().lower() == "y"

    result = create_analysis(
        title=title,
        whys=whys,
        countermeasure=countermeasure,
        defect_description=description,
        task=task,
        files=files,
        add_to_fail_index=add_fail,
    )

    print(f"\n{green('Analysis saved:')} {result['id']}")
    if result.get("fail_id"):
        print(f"{green('FAIL-index entry:')} {result['fail_id']}")

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    from scripts.colors import green, red, yellow

    parser = argparse.ArgumentParser(description="RSI 5-Whys Root Cause Analysis")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("interactive", help="Guided 5-Whys analysis")
    sub.add_parser("list", help="List all analyses")

    create_p = sub.add_parser("create", help="Create analysis non-interactively")
    create_p.add_argument("--title", required=True)
    create_p.add_argument("--whys", nargs="+", required=True, help="3-5 why answers in order")
    create_p.add_argument("--countermeasure", required=True)
    create_p.add_argument("--description", default="")
    create_p.add_argument("--task", default="")
    create_p.add_argument("--files", nargs="*")
    create_p.add_argument("--add-to-fail-index", action="store_true")

    close_p = sub.add_parser("close", help="Close an analysis")
    close_p.add_argument("rca_id", help="RCA ID (e.g., RCA-001)")
    close_p.add_argument("--verified", action="store_true")
    close_p.add_argument("--notes", default="")

    args = parser.parse_args()

    if args.cmd == "interactive":
        interactive_five_whys()
    elif args.cmd == "list":
        analyses = _load_analyses()
        if not analyses:
            print("No root cause analyses found.")
            return
        for a in analyses:
            status_color = green if a["status"] in ("closed", "verified") else yellow
            print(f"  {a['id']}  {status_color(a['status'].upper()):<10}  {a['title']}")
            print(f"           Whys: {len(a['whys'])} | Countermeasure: {a['countermeasure'][:40]}")
    elif args.cmd == "create":
        if len(args.whys) < 3:
            print(f"{red('ERROR:')} Minimum 3 whys required")
            sys.exit(1)
        result = create_analysis(
            title=args.title,
            whys=args.whys,
            countermeasure=args.countermeasure,
            defect_description=args.description,
            task=args.task,
            files=args.files,
            add_to_fail_index=args.add_to_fail_index,
        )
        print(f"{green('Created')} {result['id']}: {result['title']}")
    elif args.cmd == "close":
        ok = close_analysis(args.rca_id.upper(), args.verified, args.notes)
        if ok:
            print(f"{green('Closed')} {args.rca_id}")
        else:
            print(f"{red('ERROR:')} Analysis {args.rca_id} not found or already closed")
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
