"""Tests for robust JSON extraction from LLM output — covers MiniMax-M2.7 quirks."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.delegate import _extract_json


def test_clean_json():
    raw = '{"changes": {"test.py": "x = 1"}, "proof_wrong": "might fail", "notes": ""}'
    result = _extract_json(raw)
    assert result is not None
    assert result["changes"]["test.py"] == "x = 1"


def test_json_in_markdown_fence():
    raw = '''Here is my response:
```json
{"changes": {"test.py": "x = 1"}, "proof_wrong": "test", "notes": ""}
```
'''
    result = _extract_json(raw)
    assert result is not None
    assert "changes" in result


def test_json_in_plain_fence():
    raw = '''```
{"changes": {}, "proof_wrong": "test", "notes": "done"}
```'''
    result = _extract_json(raw)
    assert result is not None
    assert result["proof_wrong"] == "test"


def test_json_with_commentary_before():
    raw = '''I'll implement the changes now.

{"changes": {"src/auth.py": "def login(): pass"}, "proof_wrong": "if token expires", "notes": "added login"}'''
    result = _extract_json(raw)
    assert result is not None
    assert "src/auth.py" in result["changes"]


def test_json_with_commentary_after():
    raw = '''{"changes": {"test.py": "assert True"}, "proof_wrong": "edge case", "notes": ""}

I hope this helps! Let me know if you need changes.'''
    result = _extract_json(raw)
    assert result is not None
    assert result["proof_wrong"] == "edge case"


def test_json_with_trailing_comma():
    raw = '{"changes": {"test.py": "x = 1",}, "proof_wrong": "test",}'
    result = _extract_json(raw)
    assert result is not None
    assert "test.py" in result["changes"]


def test_json_truncated_closing_brace():
    raw = '{"changes": {"test.py": "x = 1"}, "proof_wrong": "test"'
    result = _extract_json(raw)
    assert result is not None
    assert result["proof_wrong"] == "test"


def test_json_in_xml_tags():
    raw = '<json>{"changes": {}, "proof_wrong": "test", "notes": ""}</json>'
    result = _extract_json(raw)
    assert result is not None


def test_multiple_json_blocks_picks_changes():
    raw = '''{"status": "thinking"}

Some commentary here.

{"changes": {"api.py": "code here"}, "proof_wrong": "might break", "notes": "done"}'''
    result = _extract_json(raw)
    assert result is not None
    assert "changes" in result


def test_empty_input():
    assert _extract_json("") is None
    assert _extract_json("   ") is None
    assert _extract_json(None) is None


def test_no_json_at_all():
    result = _extract_json("This is just plain text with no JSON whatsoever.")
    assert result is None


def test_nested_json_in_values():
    raw = '{"changes": {"config.json": "{\\"key\\": \\"value\\"}"}, "proof_wrong": "test", "notes": ""}'
    result = _extract_json(raw)
    assert result is not None
    assert "config.json" in result["changes"]


def test_json_with_newlines_in_code():
    raw = '{"changes": {"test.py": "line1\\nline2\\nline3"}, "proof_wrong": "test", "notes": ""}'
    result = _extract_json(raw)
    assert result is not None
    assert "\\n" in result["changes"]["test.py"] or "\n" in result["changes"]["test.py"]
