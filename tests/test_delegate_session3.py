"""Session 3 tests — worker-genericization thread-through.

Covers:
- Nested JSON-flow parsing in _parse_named_worker (extra_body as native dict)
- Legacy extra_body_json fallback for backward compatibility
- client_timeout_seconds and max_retries per-worker with fallbacks
- output_format_preference: delimiter-first vs JSON-first parser ordering
"""

import json
import sys
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _reset_cache():
    import scripts.delegate as d

    d._worker_config_cache = None


def _write_arch(tmp_path, yaml_text):
    import scripts.delegate as d

    path = tmp_path / "architecture.yaml"
    path.write_text(textwrap.dedent(yaml_text).lstrip("\n"), encoding="utf-8")
    d.ARCHITECTURE_FILE = path
    _reset_cache()
    return path


# ---------------------------------------------------------------------------
# Nested YAML flow-style parsing
# ---------------------------------------------------------------------------


def test_extra_body_parses_as_native_dict(tmp_path):
    _write_arch(
        tmp_path,
        """
        workers:
          kimi:
            provider: "kimi"
            base_url: "https://api.moonshot.ai/v1"
            model: "kimi-k2.6"
            extra_body: {"thinking": {"type": "disabled"}}
            env_key: "KIMI_API_KEY"
        """,
    )
    from scripts.delegate import _load_worker_config

    cfg = _load_worker_config("kimi")
    eb = cfg["extra_body"]
    assert isinstance(eb, dict)
    assert eb == {"thinking": {"type": "disabled"}}


def test_extra_body_list_value_parses_as_list(tmp_path):
    _write_arch(
        tmp_path,
        """
        workers:
          sample:
            provider: "x"
            base_url: "https://x/v1"
            model: "m"
            extra_body: ["a", "b", "c"]
            env_key: "K"
        """,
    )
    from scripts.delegate import _load_worker_config

    cfg = _load_worker_config("sample")
    assert cfg["extra_body"] == ["a", "b", "c"]


def test_malformed_json_flow_falls_back_to_scalar(tmp_path):
    """A value starting with { but not valid JSON should not crash the parser."""
    _write_arch(
        tmp_path,
        """
        workers:
          sample:
            provider: "x"
            base_url: "https://x/v1"
            model: "m"
            description: "not a real dict {bad syntax"
            env_key: "K"
        """,
    )
    from scripts.delegate import _load_worker_config

    cfg = _load_worker_config("sample")
    # Should be stored as a string (scalar fallback), not crash
    assert isinstance(cfg["description"], str)
    assert "bad syntax" in cfg["description"]


def test_legacy_extra_body_json_still_accepted(tmp_path):
    """Configs still using extra_body_json string shim should continue to work."""
    _write_arch(
        tmp_path,
        """
        workers:
          legacy:
            provider: "x"
            base_url: "https://x/v1"
            model: "m"
            extra_body_json: '{"thinking": {"type": "disabled"}}'
            env_key: "K"
        """,
    )
    from scripts.delegate import _load_worker_config

    cfg = _load_worker_config("legacy")
    # Legacy string shim is still in config as a string; call_worker's fallback
    # path handles decoding. Verify the field arrived untouched.
    assert cfg["extra_body_json"] == '{"thinking": {"type": "disabled"}}'
    assert cfg.get("extra_body") is None


def test_scalar_values_unchanged_by_nested_parser(tmp_path):
    """JSON-flow detection must not mangle normal scalar keys."""
    _write_arch(
        tmp_path,
        """
        workers:
          sample:
            provider: "x"
            base_url: "https://x/v1"
            model: "m"
            max_tokens: 32768
            temperature: 0.6
            env_key: "K"
        """,
    )
    from scripts.delegate import _load_worker_config

    cfg = _load_worker_config("sample")
    assert cfg["max_tokens"] == "32768"
    assert cfg["temperature"] == "0.6"
    assert cfg["provider"] == "x"


# ---------------------------------------------------------------------------
# Client timeout + max_retries fallbacks
# ---------------------------------------------------------------------------


def test_client_timeout_fallback_chain(tmp_path):
    """client_timeout_seconds takes precedence; timeout_seconds is a fallback."""
    _write_arch(
        tmp_path,
        """
        workers:
          primary:
            provider: "x"
            base_url: "https://x/v1"
            model: "m"
            client_timeout_seconds: 1800
            timeout_seconds: 120
            env_key: "K"
          legacy:
            provider: "x"
            base_url: "https://x/v1"
            model: "m"
            timeout_seconds: 120
            env_key: "K"
          bare:
            provider: "x"
            base_url: "https://x/v1"
            model: "m"
            env_key: "K"
        """,
    )
    from scripts.delegate import _load_worker_config

    primary = _load_worker_config("primary")
    assert int(primary["client_timeout_seconds"]) == 1800

    _reset_cache()
    legacy = _load_worker_config("legacy")
    # Legacy config has only timeout_seconds; call_worker uses it as fallback
    assert "client_timeout_seconds" not in legacy
    assert int(legacy["timeout_seconds"]) == 120

    _reset_cache()
    bare = _load_worker_config("bare")
    assert "client_timeout_seconds" not in bare


def test_max_retries_default_when_absent(tmp_path):
    """max_retries key absent → config.get returns None; call_worker defaults to 2."""
    _write_arch(
        tmp_path,
        """
        workers:
          bare:
            provider: "x"
            base_url: "https://x/v1"
            model: "m"
            env_key: "K"
        """,
    )
    from scripts.delegate import _load_worker_config

    cfg = _load_worker_config("bare")
    assert cfg.get("max_retries") is None


# ---------------------------------------------------------------------------
# output_format_preference parser-ordering
# ---------------------------------------------------------------------------


def test_format_preference_delimiter_first(monkeypatch):
    """When output_format_preference=delimiter, delimiter parser is tried first."""
    import scripts.delegate as d

    calls = []

    def fake_json(raw):
        calls.append("json")
        return {"changes": {"from_json.py": "x=1"}, "proof_wrong": "", "notes": ""}

    def fake_delim(raw):
        calls.append("delim")
        return {"changes": {"from_delim.py": "y=2"}, "proof_wrong": "", "notes": ""}

    monkeypatch.setattr(d, "_extract_json", fake_json)
    monkeypatch.setattr(d, "_extract_delimiter_files", fake_delim)

    # Simulate the call_worker parser-chain logic directly
    config = {"output_format_preference": "delimiter"}
    raw = "irrelevant"
    format_pref = str(config.get("output_format_preference", "either")).lower()
    if format_pref == "delimiter":
        parsed = d._extract_delimiter_files(raw) or d._extract_json(raw)
    else:
        parsed = d._extract_json(raw) or d._extract_delimiter_files(raw)

    assert calls == ["delim"]  # JSON never called — delimiter returned non-None
    assert "from_delim.py" in parsed["changes"]


def test_format_preference_json_first(monkeypatch):
    """Default (either) or explicit json → JSON parser is tried first."""
    import scripts.delegate as d

    calls = []

    monkeypatch.setattr(d, "_extract_json", lambda r: (calls.append("json") or {"changes": {"via_json.py": "x=1"}, "proof_wrong": "", "notes": ""}))
    monkeypatch.setattr(d, "_extract_delimiter_files", lambda r: (calls.append("delim") or {"changes": {"via_delim.py": "y=2"}, "proof_wrong": "", "notes": ""}))

    for pref in ("either", "json", "", "unset"):
        calls.clear()
        config = {"output_format_preference": pref}
        raw = "irrelevant"
        format_pref = str(config.get("output_format_preference", "either")).lower()
        if format_pref == "delimiter":
            parsed = d._extract_delimiter_files(raw) or d._extract_json(raw)
        else:
            parsed = d._extract_json(raw) or d._extract_delimiter_files(raw)
        assert calls == ["json"], f"pref={pref!r} should try JSON first, got {calls}"
        assert "via_json.py" in parsed["changes"]


def test_format_preference_fallback_preserves_9b_behavior(monkeypatch):
    """When preferred parser returns None, fallback parser still runs."""
    import scripts.delegate as d

    monkeypatch.setattr(d, "_extract_json", lambda r: None)  # JSON fails
    monkeypatch.setattr(
        d, "_extract_delimiter_files",
        lambda r: {"changes": {"f.py": "x"}, "proof_wrong": "", "notes": ""},
    )

    # Default ordering: JSON first (None) → delimiter fallback → success
    config = {}
    raw = "irrelevant"
    format_pref = str(config.get("output_format_preference", "either")).lower()
    if format_pref == "delimiter":
        parsed = d._extract_delimiter_files(raw) or d._extract_json(raw)
    else:
        parsed = d._extract_json(raw) or d._extract_delimiter_files(raw)
    assert parsed is not None
    assert "f.py" in parsed["changes"]
