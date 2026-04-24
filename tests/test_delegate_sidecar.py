"""Tests for F6 (raw-response sidecar) and 9b (delimiter parser) in delegate.py.

F6 guarantees billed worker output is recoverable even when parsing fails.
9b adds a delimiter-block fallback for workers that emit `<<<FILE: path>>>`
blocks instead of the JSON wrapper.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# F6 — raw-response sidecar
# ---------------------------------------------------------------------------


def _redirect_results_dir(tmp_path, monkeypatch):
    import scripts.delegate as d

    results = tmp_path / "results"
    monkeypatch.setattr(d, "RESULTS_DIR", results)
    monkeypatch.setattr(d, "REVIEWS_DIR", tmp_path)
    monkeypatch.setattr(d, "PENDING_DIR", tmp_path / "pending")
    monkeypatch.setattr(d, "DELEGATIONS_LOG", tmp_path / "delegations.jsonl")
    return results


def test_sidecar_written_on_successful_parse(tmp_path, monkeypatch):
    import scripts.delegate as d

    results = _redirect_results_dir(tmp_path, monkeypatch)
    raw = '{"changes": {"x.py": "a=1"}, "proof_wrong": "p", "notes": "n"}'
    d._write_raw_sidecar("TASK-F6-1", raw)
    sidecar = results / "TASK-F6-1.raw.txt"
    assert sidecar.exists()
    assert sidecar.read_text(encoding="utf-8") == raw


def test_sidecar_written_on_failed_parse(tmp_path, monkeypatch):
    import scripts.delegate as d

    results = _redirect_results_dir(tmp_path, monkeypatch)
    raw = "this is not parseable and has no delimiters either"
    d._write_raw_sidecar("TASK-F6-2", raw)
    sidecar = results / "TASK-F6-2.raw.txt"
    assert sidecar.exists()
    assert sidecar.read_text(encoding="utf-8") == raw


def test_sidecars_do_not_collide_across_tasks(tmp_path, monkeypatch):
    import scripts.delegate as d

    results = _redirect_results_dir(tmp_path, monkeypatch)
    d._write_raw_sidecar("TASK-A", "alpha")
    d._write_raw_sidecar("TASK-B", "bravo")
    assert (results / "TASK-A.raw.txt").read_text(encoding="utf-8") == "alpha"
    assert (results / "TASK-B.raw.txt").read_text(encoding="utf-8") == "bravo"


def test_sidecar_writes_full_content_without_truncation(tmp_path, monkeypatch):
    import scripts.delegate as d

    results = _redirect_results_dir(tmp_path, monkeypatch)
    big = "x" * 250_000
    d._write_raw_sidecar("TASK-BIG", big)
    sidecar = results / "TASK-BIG.raw.txt"
    assert sidecar.read_text(encoding="utf-8") == big


# ---------------------------------------------------------------------------
# 9b — delimiter-block fallback parser
# ---------------------------------------------------------------------------


def test_delimiter_single_file():
    from scripts.delegate import _extract_delimiter_files

    raw = "<<<FILE: src/foo.py>>>\nprint('hi')\n<<<END FILE>>>"
    result = _extract_delimiter_files(raw)
    assert result is not None
    assert result["changes"] == {"src/foo.py": "print('hi')"}


def test_delimiter_multi_file():
    from scripts.delegate import _extract_delimiter_files

    raw = (
        "<<<FILE: a.py>>>\nx = 1\n<<<END FILE>>>\n"
        "<<<FILE: b.py>>>\ny = 2\n<<<END FILE>>>"
    )
    result = _extract_delimiter_files(raw)
    assert result is not None
    assert result["changes"]["a.py"] == "x = 1"
    assert result["changes"]["b.py"] == "y = 2"


def test_delimiter_handles_windows_newlines():
    from scripts.delegate import _extract_delimiter_files

    raw = "<<<FILE: a.py>>>\r\nx = 1\r\n<<<END FILE>>>"
    result = _extract_delimiter_files(raw)
    assert result is not None
    assert "a.py" in result["changes"]


def test_delimiter_returns_none_when_no_blocks():
    from scripts.delegate import _extract_delimiter_files

    assert _extract_delimiter_files("no delimiters here, just prose") is None


def test_delimiter_returns_none_on_empty_input():
    from scripts.delegate import _extract_delimiter_files

    assert _extract_delimiter_files("") is None


def test_delimiter_ignores_unterminated_block():
    from scripts.delegate import _extract_delimiter_files

    raw = "<<<FILE: half.py>>>\nx = 1\n(no closing marker)"
    assert _extract_delimiter_files(raw) is None


def test_delimiter_preserves_body_whitespace():
    from scripts.delegate import _extract_delimiter_files

    raw = "<<<FILE: a.py>>>\n    indented = True\n<<<END FILE>>>"
    result = _extract_delimiter_files(raw)
    assert result is not None
    assert result["changes"]["a.py"] == "    indented = True"


# ---------------------------------------------------------------------------
# Integration — JSON-first, delimiter-fallback precedence
# ---------------------------------------------------------------------------


def test_json_and_delimiter_together_json_wins():
    """If both formats are present, JSON parser claims it first.

    The fallback is only consulted when _extract_json returns None, so a raw
    response containing both a valid JSON wrapper AND delimiter blocks is
    claimed by JSON — preserving backward-compatible behavior for workers
    that emit both defensively.
    """
    from scripts.delegate import _extract_delimiter_files, _extract_json

    raw = (
        '{"changes": {"via_json.py": "a = 1"}, "proof_wrong": "p", "notes": "n"}\n'
        "<<<FILE: via_delim.py>>>\nb = 2\n<<<END FILE>>>"
    )
    via_json = _extract_json(raw)
    assert via_json is not None
    assert "via_json.py" in via_json["changes"]
    # Delimiter parser would also match if called, but call_worker only falls
    # through to it when _extract_json is None — verify delimiter parsing
    # itself still works on the same input if invoked directly.
    via_delim = _extract_delimiter_files(raw)
    assert via_delim is not None
    assert "via_delim.py" in via_delim["changes"]
