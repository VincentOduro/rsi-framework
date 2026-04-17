#!/usr/bin/env python3
"""
backlog.py — RSI Framework lightweight backlog manager.

Manages a markdown-based backlog (backlog.md) with standard task format.
All operations are file-based; no external tools required.

Usage:
    python3 scripts/backlog.py add --type bug --title "Fix auth token" --priority HIGH
    python3 scripts/backlog.py list
    python3 scripts/backlog.py list --status todo
    python3 scripts/backlog.py show TSK-001
    python3 scripts/backlog.py update TSK-001 --status done --completed 2026-04-15
    python3 scripts/backlog.py stats
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
BACKLOG_FILE = PROJECT_ROOT / ".memory" / "backlog.md"
SECTIONS = ["in-progress", "blocked", "todo", "done"]

VALID_TYPES = {"feature", "bug", "refactor", "chore", "spike", "docs"}
VALID_STATUSES = {"todo", "in-progress", "blocked", "done"}
VALID_PRIORITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
VALID_ESTIMATES = {"xs", "s", "m", "l", "xl"}


def green(msg: str) -> str:
    return f"\033[92m{msg}\033[0m"


def red(msg: str) -> str:
    return f"\033[91m{msg}\033[0m"


def yellow(msg: str) -> str:
    return f"\033[93m{msg}\033[0m"


def cyan(msg: str) -> str:
    return f"\033[96m{msg}\033[0m"


def _read_backlog() -> str:
    if not BACKLOG_FILE.exists():
        print(f"{red('ERROR:')} No backlog found at {BACKLOG_FILE}")
        print("Copy MEMORY_TEMPLATE/backlog.md to .memory/backlog.md first.")
        sys.exit(1)
    return BACKLOG_FILE.read_text(encoding="utf-8")


def _write_backlog(content: str) -> None:
    BACKLOG_FILE.write_text(content, encoding="utf-8")


def _parse_tasks(content: str) -> list[dict]:
    """Parse all tasks from backlog.md content."""
    tasks = []
    # Match task entries: ### TSK-XXX: title
    pattern = r"### (TSK-\d+): (.+)"
    for match in re.finditer(pattern, content):
        task_id = match.group(1)
        title = match.group(2).strip()

        # Find the full task block (from ### line to next ### or end)
        start = match.start()
        next_match = re.search(r"### TSK-\d+:", content[start + 1 :])
        if next_match:
            end = start + 1 + next_match.start()
        else:
            end = len(content)

        block = content[start:end]

        task = {
            "id": task_id,
            "title": title,
            "type": _extract_field(block, "type"),
            "status": _extract_field(block, "status"),
            "priority": _extract_field(block, "priority"),
            "estimate": _extract_field(block, "estimate"),
            "assignee": _extract_field(block, "assignee"),
            "created": _extract_field(block, "created"),
            "updated": _extract_field(block, "updated"),
            "completed": _extract_field(block, "completed"),
            "related": _extract_field(block, "related"),
            "notes": _extract_field(block, "notes", multi_line=True),
            "blocked_by": _extract_field(block, "blocked-by"),
        }
        tasks.append(task)
    return tasks


def _extract_field(block: str, field: str, multi_line: bool = False) -> str:
    """Extract field value from task block."""
    pattern = rf"\*\*{field}:\*\* (.+?)(?=\n\*\*|\n###|$)"
    match = re.search(pattern, block, re.DOTALL | re.IGNORECASE)
    if match:
        value = match.group(1).strip()
        if multi_line:
            return value
        return value.split("\n")[0].strip()
    return ""


def _build_task_block(task: dict) -> str:
    """Build a task block from task dict."""
    lines = [f"### {task['id']}: {task['title']}"]
    for field, value in [
        ("type", task.get("type")),
        ("status", task.get("status")),
        ("priority", task.get("priority")),
        ("estimate", task.get("estimate")),
        ("assignee", task.get("assignee")),
        ("created", task.get("created")),
        ("updated", task.get("updated")),
        ("completed", task.get("completed")),
        ("related", task.get("related")),
        ("blocked-by", task.get("blocked_by")),
        ("notes", task.get("notes")),
    ]:
        if value:
            display_field = field.replace("_", "-") if field != "type" else field
            lines.append(f"**{display_field}:** {value}")
    return "\n".join(lines) + "\n"


def _section_for_status(status: str) -> str:
    if status == "in-progress":
        return "in-progress"
    if status == "blocked":
        return "blocked"
    if status == "done":
        return "done"
    return "todo"


def _status_for_section(section: str) -> str:
    if section == "in-progress":
        return "in-progress"
    if section == "blocked":
        return "blocked"
    if section == "done":
        return "done"
    return "todo"


def _build_table_header() -> str:
    return "| id | type | title | priority | estimate | assignee |\n|---|---|---|---|---|---|"


def _build_row(task: dict, show_blocked_by: bool = False) -> str:
    row = f"| {task['id']} | {task['type'] or ''} | {task['title']} | {task['priority'] or ''} | {task['estimate'] or ''} | {task.get('assignee', '') or ''} |"
    if show_blocked_by:
        row = row[:-2] + f" | {task.get('blocked_by', '') or ''} |"
    return row


def _update_stats(content: str) -> str:
    """Update the Stats table in backlog.md."""
    tasks = _parse_tasks(content)
    total = len(tasks)
    todo = sum(1 for t in tasks if t.get("status") == "todo")
    in_progress = sum(1 for t in tasks if t.get("status") == "in-progress")
    blocked = sum(1 for t in tasks if t.get("status") == "blocked")
    done = sum(1 for t in tasks if t.get("status") == "done")

    stats_lines = f"""| Metric | Count |
|---|---|
| Total | {total} |
| Todo | {todo} |
| In Progress | {in_progress} |
| Blocked | {blocked} |
| Done | {done} |
"""
    # Replace the stats table
    pattern = r"\| Metric \| Count \|.*?\|---\|"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        content = content[: match.start()] + stats_lines + content[match.end() :]
    return content


def _next_task_id(tasks: list[dict]) -> str:
    """Generate next sequential task ID."""
    max_id = 0
    for task in tasks:
        m = re.search(r"TSK-(\d+)", task["id"])
        if m:
            max_id = max(max_id, int(m.group(1)))
    return f"TSK-{max_id + 1:03d}"


def _insert_task_into_section(content: str, task: dict, status: str) -> str:
    """Insert task into the correct section table."""
    section = _section_for_status(status)
    # Find the section header and its table
    section_pattern = rf"(## {section.replace('-', ' ').title()}\n\n\| id \| type \| title \| priority \| estimate \| assignee \|.*?\n)((\|.*?\n)*)"
    match = re.search(section_pattern, content, re.DOTALL | re.IGNORECASE)
    if match:
        table_start = match.group(1)
        table_rows = match.group(2)
        new_row = _build_row(task, show_blocked_by=(section == "blocked")) + "\n"
        # Insert in priority order (CRITICAL > HIGH > MEDIUM > LOW)
        rows = [r for r in table_rows.strip().split("\n") if r] + [new_row]
        # Sort by priority
        priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "": 4}
        rows.sort(key=lambda r: priority_order.get(r.split("|")[4].strip(), 4))
        new_table = table_start + "\n".join(rows) + "\n"
        content = content[: match.start()] + new_table + content[match.end() :]
    return content


def _remove_task_from_sections(content: str, task_id: str) -> str:
    """Remove a task row from all section tables."""
    for section in SECTIONS:
        pattern = rf"(\| {task_id} \|.*?\n)"
        content = re.sub(pattern, "", content, flags=re.MULTILINE)
    return content


def cmd_add(args) -> None:
    """Add a new task to the backlog."""
    content = _read_backlog()
    tasks = _parse_tasks(content)

    task_id = _next_task_id(tasks)
    today = date.today().isoformat()

    task = {
        "id": task_id,
        "title": args.title,
        "type": args.type,
        "status": args.status,
        "priority": args.priority,
        "estimate": args.estimate,
        "assignee": args.assignee or "",
        "created": today,
        "updated": today,
        "completed": "",
        "related": args.related or "",
        "notes": args.notes or "",
        "blocked_by": args.blocked_by or "",
    }

    # Add task entry
    new_entry = "\n" + _build_task_block(task)
    content += new_entry

    # Insert into section table
    content = _insert_task_into_section(content, task, args.status)

    # Update stats
    content = _update_stats(content)

    _write_backlog(content)
    print(f"{green('Added')} {task_id}: {args.title} [{args.type}] [{args.priority}]")


def cmd_list(args) -> None:
    """List tasks, optionally filtered by status or priority."""
    content = _read_backlog()
    tasks = _parse_tasks(content)

    if args.status:
        tasks = [t for t in tasks if t.get("status") == args.status]
    if args.priority:
        tasks = [t for t in tasks if t.get("priority") == args.priority.upper()]
    if args.type:
        tasks = [t for t in tasks if t.get("type") == args.type]

    if not tasks:
        status_msg = f" with status={args.status}" if args.status else ""
        priority_msg = f" with priority={args.priority}" if args.priority else ""
        type_msg = f" with type={args.type}" if args.type else ""
        print(f"{yellow('No tasks found')}{status_msg}{priority_msg}{type_msg}")
        return

    print(f"\n{'=' * 70}")
    print(f"BACKLOG — {len(tasks)} task(s)")
    if args.status:
        print(f"Status: {args.status}")
    if args.priority:
        print(f"Priority: {args.priority.upper()}")
    print(f"{'=' * 70}\n")

    for task in tasks:
        status_color = {
            "todo": "",
            "in-progress": cyan,
            "blocked": red,
            "done": green,
        }.get(task.get("status"), "")

        print(f"  {task['id']}  {task['type'] or '?'}  {task['title']}")
        meta = []
        if task.get("priority"):
            meta.append(task["priority"])
        if task.get("estimate"):
            meta.append(task["estimate"])
        if task.get("assignee"):
            meta.append(task["assignee"])
        if meta:
            print(f"           {' | '.join(meta)}")
        if task.get("blocked_by"):
            print(f"           BLOCKED BY: {task['blocked_by']}")
        print()


def cmd_show(args) -> None:
    """Show full details of a task."""
    content = _read_backlog()
    tasks = _parse_tasks(content)

    task = next((t for t in tasks if t["id"] == args.task_id.upper()), None)
    if not task:
        print(f"{red('ERROR:')} Task {args.task_id} not found")
        sys.exit(1)

    print(f"\n{'=' * 70}")
    print(f"{task['id']}: {task['title']}")
    print(f"{'=' * 70}\n")

    for field, label in [
        ("type", "Type"),
        ("status", "Status"),
        ("priority", "Priority"),
        ("estimate", "Estimate"),
        ("assignee", "Assignee"),
        ("created", "Created"),
        ("updated", "Updated"),
        ("completed", "Completed"),
        ("related", "Related"),
        ("blocked_by", "Blocked By"),
    ]:
        value = task.get(field)
        if value:
            print(f"  {label:<12} {value}")

    if task.get("notes"):
        print("\n  Notes:")
        for line in task["notes"].split("\n"):
            print(f"    {line}")

    print()


def cmd_update(args) -> None:
    """Update task fields."""
    content = _read_backlog()
    tasks = _parse_tasks(content)

    task = next((t for t in tasks if t["id"] == args.task_id.upper()), None)
    if not task:
        print(f"{red('ERROR:')} Task {args.task_id} not found")
        sys.exit(1)

    old_status = task.get("status", "")
    today = date.today().isoformat()

    updates = []
    for field, value in [
        ("title", args.title),
        ("type", args.type),
        ("status", args.status),
        ("priority", args.priority),
        ("estimate", args.estimate),
        ("assignee", args.assignee),
        ("completed", args.completed),
        ("related", args.related),
        ("blocked_by", args.blocked_by),
        ("notes", args.notes),
    ]:
        if value is not None:
            task[field] = value
            if field == "status" and value == "done" and not task.get("completed"):
                task["completed"] = today
            updates.append(field)

    task["updated"] = today

    # Rebuild the task block in content
    old_block_match = re.search(rf"### {task['id']}:.*?(?=\n### |\Z)", content, re.DOTALL)
    if old_block_match:
        content = (
            content[: old_block_match.start()]
            + _build_task_block(task)
            + content[old_block_match.end() :]
        )

    # If status changed, move task row between sections
    if old_status != task.get("status"):
        content = _remove_task_from_sections(content, task["id"])
        content = _insert_task_into_section(content, task, task.get("status", "todo"))

    # Update stats
    content = _update_stats(content)

    _write_backlog(content)
    print(f"{green('Updated')} {task['id']}: {', '.join(updates)}")


def cmd_stats(args) -> None:
    """Show backlog statistics."""
    content = _read_backlog()
    tasks = _parse_tasks(content)

    total = len(tasks)
    by_status = {}
    by_priority = {}
    by_type = {}

    for task in tasks:
        s = task.get("status", "todo")
        p = task.get("priority", "MEDIUM")
        t = task.get("type", "unknown")
        by_status[s] = by_status.get(s, 0) + 1
        by_priority[p] = by_priority.get(p, 0) + 1
        by_type[t] = by_type.get(t, 0) + 1

    print(f"\n{'=' * 50}")
    print("BACKLOG STATS")
    print(f"{'=' * 50}\n")
    print(f"  Total tasks:  {total}")
    print("\n  By Status:")
    for s in ["in-progress", "blocked", "todo", "done"]:
        count = by_status.get(s, 0)
        bar = "#" * count + "." * max(0, 10 - count)
        print(f"    {s:<12} {bar} {count}")
    print("\n  By Priority:")
    for p in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        count = by_priority.get(p, 0)
        bar = "#" * count + "." * max(0, 10 - count)
        print(f"    {p:<12} {bar} {count}")
    print("\n  By Type:")
    for t, count in sorted(by_type.items()):
        bar = "#" * count + "." * max(0, 10 - count)
        print(f"    {t:<12} {bar} {count}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="RSI Backlog Manager — lightweight markdown-based task tracking"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # add
    add_parser = subparsers.add_parser("add", help="Add a new task")
    add_parser.add_argument("--type", required=True, choices=sorted(VALID_TYPES), help="Task type")
    add_parser.add_argument("--title", required=True, help="Task title")
    add_parser.add_argument(
        "--status",
        default="todo",
        choices=sorted(VALID_STATUSES),
        help="Task status (default: todo)",
    )
    add_parser.add_argument(
        "--priority",
        default="MEDIUM",
        choices=sorted(VALID_PRIORITIES),
        help="Task priority (default: MEDIUM)",
    )
    add_parser.add_argument("--estimate", choices=sorted(VALID_ESTIMATES), help="Estimated effort")
    add_parser.add_argument("--assignee", help="Assignee")
    add_parser.add_argument("--related", help="Related tasks or FAIL-IDs")
    add_parser.add_argument("--blocked-by", help="Task(s) blocking this task")
    add_parser.add_argument("--notes", help="Free-form notes")

    # list
    list_parser = subparsers.add_parser("list", help="List tasks")
    list_parser.add_argument("--status", choices=sorted(VALID_STATUSES), help="Filter by status")
    list_parser.add_argument(
        "--priority", choices=sorted(VALID_PRIORITIES), help="Filter by priority"
    )
    list_parser.add_argument("--type", choices=sorted(VALID_TYPES), help="Filter by type")

    # show
    show_parser = subparsers.add_parser("show", help="Show task details")
    show_parser.add_argument("task_id", help="Task ID (e.g., TSK-001)")

    # update
    update_parser = subparsers.add_parser("update", help="Update task fields")
    update_parser.add_argument("task_id", help="Task ID (e.g., TSK-001)")
    update_parser.add_argument("--title", help="New title")
    update_parser.add_argument("--type", choices=sorted(VALID_TYPES), help="New type")
    update_parser.add_argument("--status", choices=sorted(VALID_STATUSES), help="New status")
    update_parser.add_argument("--priority", choices=sorted(VALID_PRIORITIES), help="New priority")
    update_parser.add_argument("--estimate", choices=sorted(VALID_ESTIMATES), help="New estimate")
    update_parser.add_argument("--assignee", help="New assignee")
    update_parser.add_argument("--completed", help="Completion date (YYYY-MM-DD)")
    update_parser.add_argument("--related", help="Related tasks")
    update_parser.add_argument("--blocked-by", help="Blocking task(s)")
    update_parser.add_argument("--notes", help="New notes")

    # stats
    subparsers.add_parser("stats", help="Show backlog statistics")

    args = parser.parse_args()

    if args.command == "add":
        cmd_add(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "update":
        cmd_update(args)
    elif args.command == "stats":
        cmd_stats(args)


if __name__ == "__main__":
    main()
