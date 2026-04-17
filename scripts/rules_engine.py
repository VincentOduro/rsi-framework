#!/usr/bin/env python3
"""
rules_engine.py -- Declarative enforcement rules evaluator.

Inspired by AgentSpec (ICSE 2026): trigger -> condition -> action rules
defined in YAML, evaluated at runtime by hooks.py.

Adding a new rule = editing .rsi/rules.yaml, not Python code.

Usage:
    from scripts.rules_engine import RuleEngine
    engine = RuleEngine()
    allowed, messages = engine.evaluate("pre_edit", context)
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
RULES_FILE = PROJECT_ROOT / ".rsi" / "rules.yaml"

# Cache
_rules_cache: list[dict] | None = None
_rules_mtime: float = 0.0


def _load_rules() -> list[dict]:
    """Load rules from .rsi/rules.yaml. Cached by mtime."""
    global _rules_cache, _rules_mtime

    if not RULES_FILE.exists():
        return []

    current_mtime = RULES_FILE.stat().st_mtime
    if _rules_cache is not None and current_mtime == _rules_mtime:
        return _rules_cache

    content = RULES_FILE.read_text(encoding="utf-8")
    rules = _parse_rules_yaml(content)
    _rules_cache = rules
    _rules_mtime = current_mtime
    return rules


def _parse_rules_yaml(content: str) -> list[dict]:
    """Parse rules from YAML without requiring PyYAML.

    Handles the specific structure in rules.yaml.
    """
    rules = []
    current_rule: dict | None = None

    for line in content.split("\n"):
        stripped = line.strip()

        # Skip comments and empty
        if not stripped or stripped.startswith("#"):
            continue

        # New rule starts with "- id:"
        if stripped.startswith("- id:"):
            if current_rule:
                rules.append(current_rule)
            current_rule = {"id": stripped.split(":", 1)[1].strip().strip('"')}
            continue

        # Rule fields
        if current_rule is not None and ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            # Strip outer YAML quotes only (not inner content quotes)
            if (val.startswith('"') and val.endswith('"')) or (
                val.startswith("'") and val.endswith("'")
            ):
                val = val[1:-1]
            if key in ("name", "trigger", "condition", "action", "message"):
                current_rule[key] = val

    if current_rule:
        rules.append(current_rule)

    return rules


# ---------------------------------------------------------------------------
# Condition evaluator
# ---------------------------------------------------------------------------


def _eval_condition(condition: str, context: dict) -> bool:
    """Evaluate a rule condition against the current context.

    Supports conditions used in .rsi/rules.yaml:
    - Variable names (looked up in context as bool)
    - 'and', 'or', 'not' operators
    - '==' comparison
    - 'in' containment: "'str' in variable" or "variable in ('a', 'b')"
    - Parentheses for grouping
    - String literals in single quotes

    Safe evaluator — no exec/eval. Handles the specific patterns in rules.yaml.
    """
    if not condition:
        return False

    # Pre-process: handle "X in ('a', 'b', 'c')" patterns
    # Convert to direct Python-safe evaluation
    try:
        return _eval_expr(condition.strip(), context)
    except Exception:
        return False


def _eval_expr(expr: str, ctx: dict) -> bool:
    """Recursively evaluate a boolean expression."""
    expr = expr.strip()
    if not expr:
        return False

    # Handle 'or' (lowest precedence)
    # Split on ' or ' but not inside quotes or parens
    parts = _split_outside(expr, " or ")
    if len(parts) > 1:
        return any(_eval_expr(p, ctx) for p in parts)

    # Handle 'and'
    parts = _split_outside(expr, " and ")
    if len(parts) > 1:
        return all(_eval_expr(p, ctx) for p in parts)

    # Handle 'not'
    if expr.startswith("not "):
        return not _eval_expr(expr[4:], ctx)

    # Handle parenthesized group
    if expr.startswith("(") and expr.endswith(")"):
        # Check it's a complete group, not "('a', 'b')"
        depth = 0
        for i, c in enumerate(expr):
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            if depth == 0 and i < len(expr) - 1:
                break  # Not a complete group
        else:
            return _eval_expr(expr[1:-1], ctx)

    # Handle '==' comparison
    if " == " in expr:
        left, right = expr.split(" == ", 1)
        return _resolve(left.strip(), ctx) == _resolve(right.strip(), ctx)

    # Handle '!=' comparison
    if " != " in expr:
        left, right = expr.split(" != ", 1)
        return _resolve(left.strip(), ctx) != _resolve(right.strip(), ctx)

    # Handle 'in' containment: "'str' in var" or "var in ('a', 'b')"
    if " in " in expr:
        left, right = expr.split(" in ", 1)
        left_val = _resolve(left.strip(), ctx)
        right_val = _resolve(right.strip(), ctx)
        if isinstance(right_val, (list, tuple, set)):
            return left_val in right_val
        elif isinstance(right_val, str):
            return str(left_val) in right_val
        return False

    # Simple value — resolve and coerce to bool
    return bool(_resolve(expr, ctx))


def _resolve(token: str, ctx: dict):
    """Resolve a token to its value."""
    token = token.strip()

    # String literal
    if (token.startswith("'") and token.endswith("'")) or (
        token.startswith('"') and token.endswith('"')
    ):
        return token[1:-1]

    # Tuple literal: ('a', 'b', 'c')
    if token.startswith("(") and token.endswith(")"):
        inner = token[1:-1]
        items = []
        for item in inner.split(","):
            item = item.strip().strip("'").strip('"')
            if item:
                items.append(item)
        return tuple(items)

    # Boolean literals
    if token.lower() == "true":
        return True
    if token.lower() == "false":
        return False

    # Context variable
    if token in ctx:
        return ctx[token]

    return False


def _split_outside(expr: str, sep: str) -> list[str]:
    """Split expression on separator, but not inside quotes or parentheses."""
    parts = []
    depth = 0
    in_quote = False
    quote_char = ""
    current = []
    i = 0

    while i < len(expr):
        c = expr[i]

        if in_quote:
            current.append(c)
            if c == quote_char:
                in_quote = False
        elif c in ("'", '"'):
            in_quote = True
            quote_char = c
            current.append(c)
        elif c == "(":
            depth += 1
            current.append(c)
        elif c == ")":
            depth -= 1
            current.append(c)
        elif depth == 0 and not in_quote and expr[i : i + len(sep)] == sep:
            parts.append("".join(current))
            current = []
            i += len(sep)
            continue
        else:
            current.append(c)

        i += 1

    parts.append("".join(current))
    return [p for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# Rule engine
# ---------------------------------------------------------------------------


class RuleEngine:
    """Evaluates declarative rules from .rsi/rules.yaml."""

    def __init__(self, rules_file: Path | None = None):
        if rules_file:
            global RULES_FILE
            RULES_FILE = rules_file

    def evaluate(self, trigger: str, context: dict) -> tuple[bool, list[str]]:
        """Evaluate all rules for a trigger.

        Returns:
            (allowed, messages)
            allowed: False if any rule with action=block matched
            messages: list of messages from matched rules
        """
        rules = _load_rules()
        messages = []
        blocked = False

        for rule in rules:
            if rule.get("trigger") != trigger:
                continue

            condition = rule.get("condition", "")
            if _eval_condition(condition, context):
                action = rule.get("action", "warn")
                msg = rule.get("message", rule.get("name", "Rule triggered"))

                # Format message with context variables
                try:
                    msg = msg.format(**context)
                except (KeyError, IndexError):
                    pass

                if action == "block":
                    messages.append(f"[RSI {rule.get('id', '?')}] BLOCKED: {msg}")
                    blocked = True
                    break  # First blocking rule wins
                elif action == "warn":
                    messages.append(f"[RSI {rule.get('id', '?')}] {msg}")

        return not blocked, messages


# Singleton
_engine: RuleEngine | None = None


def get_engine() -> RuleEngine:
    global _engine
    if _engine is None:
        _engine = RuleEngine()
    return _engine
