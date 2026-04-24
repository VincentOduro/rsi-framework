"""Session 3 tests — worker-genericization thread-through.

Covers:
- Nested JSON-flow parsing in _parse_named_worker (extra_body as native dict)
- Legacy extra_body_json fallback for backward compatibility
- client_timeout_seconds and max_retries per-worker with fallbacks
- output_format_preference: delimiter-first vs JSON-first parser ordering
- WorkerProfile dataclass: from_config casts, fallback chains, defaults
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


# ---------------------------------------------------------------------------
# WorkerProfile dataclass
# ---------------------------------------------------------------------------


def test_worker_profile_casts_scalars_from_string_config():
    """_parse_named_worker returns all scalars as strings; from_config casts them."""
    from scripts.delegate import WorkerProfile

    raw = {
        "provider": "x",
        "base_url": "https://x/v1",
        "model": "m",
        "env_key": "K",
        "max_tokens": "32768",
        "temperature": "0.6",
        "max_output_lines": "2000",
        "client_timeout_seconds": "1800",
        "max_retries": "3",
    }
    p = WorkerProfile.from_config("probe", raw)
    assert p.max_tokens == 32768 and isinstance(p.max_tokens, int)
    assert p.temperature == 0.6 and isinstance(p.temperature, float)
    assert p.max_output_lines == 2000 and isinstance(p.max_output_lines, int)
    assert p.client_timeout_seconds == 1800
    assert p.max_retries == 3


def test_worker_profile_defaults_when_fields_absent():
    from scripts.delegate import WorkerProfile

    p = WorkerProfile.from_config(
        "bare",
        {"provider": "x", "base_url": "u", "model": "m", "env_key": "K"},
    )
    assert p.max_tokens == 8192
    assert p.temperature == 0.3
    assert p.max_output_lines == 500
    assert p.client_timeout_seconds == 600
    assert p.max_retries == 2
    assert p.extra_body is None
    assert p.output_format_preference == "either"


def test_worker_profile_client_timeout_falls_back_to_legacy_field():
    from scripts.delegate import WorkerProfile

    p = WorkerProfile.from_config(
        "legacy",
        {
            "provider": "x",
            "base_url": "u",
            "model": "m",
            "env_key": "K",
            "timeout_seconds": "120",  # no client_timeout_seconds
        },
    )
    assert p.client_timeout_seconds == 120


def test_worker_profile_accepts_native_extra_body_dict():
    from scripts.delegate import WorkerProfile

    p = WorkerProfile.from_config(
        "kimi",
        {
            "provider": "x",
            "base_url": "u",
            "model": "m",
            "env_key": "K",
            "extra_body": {"thinking": {"type": "disabled"}},
        },
    )
    assert p.extra_body == {"thinking": {"type": "disabled"}}


def test_worker_profile_accepts_legacy_extra_body_json_shim():
    from scripts.delegate import WorkerProfile

    p = WorkerProfile.from_config(
        "legacy",
        {
            "provider": "x",
            "base_url": "u",
            "model": "m",
            "env_key": "K",
            "extra_body_json": '{"thinking": {"type": "disabled"}}',
        },
    )
    assert p.extra_body == {"thinking": {"type": "disabled"}}


def test_worker_profile_invalid_extra_body_json_leaves_none():
    """Malformed JSON in legacy shim — from_config silently drops; call_worker surfaces it."""
    from scripts.delegate import WorkerProfile

    p = WorkerProfile.from_config(
        "broken",
        {
            "provider": "x",
            "base_url": "u",
            "model": "m",
            "env_key": "K",
            "extra_body_json": "{not valid json",
        },
    )
    assert p.extra_body is None


def test_worker_profile_normalizes_output_format_preference_case():
    from scripts.delegate import WorkerProfile

    p = WorkerProfile.from_config(
        "mixed",
        {
            "provider": "x",
            "base_url": "u",
            "model": "m",
            "env_key": "K",
            "output_format_preference": "DELIMITER",
        },
    )
    assert p.output_format_preference == "delimiter"


def test_worker_profile_non_numeric_values_fall_back_to_defaults():
    from scripts.delegate import WorkerProfile

    p = WorkerProfile.from_config(
        "broken",
        {
            "provider": "x",
            "base_url": "u",
            "model": "m",
            "env_key": "K",
            "max_tokens": "not-a-number",
            "temperature": "hot",
            "max_retries": "many",
        },
    )
    assert p.max_tokens == 8192
    assert p.temperature == 0.3
    assert p.max_retries == 2


def test_worker_profile_top_p_none_when_unset():
    from scripts.delegate import WorkerProfile

    p = WorkerProfile.from_config(
        "bare",
        {"provider": "x", "base_url": "u", "model": "m", "env_key": "K"},
    )
    assert p.top_p is None


def test_worker_profile_top_p_parses_float():
    from scripts.delegate import WorkerProfile

    p = WorkerProfile.from_config(
        "sample",
        {
            "provider": "x",
            "base_url": "u",
            "model": "m",
            "env_key": "K",
            "top_p": "0.95",
        },
    )
    assert p.top_p == 0.95


def test_worker_profile_top_p_invalid_falls_back_to_none():
    from scripts.delegate import WorkerProfile

    p = WorkerProfile.from_config(
        "sample",
        {
            "provider": "x",
            "base_url": "u",
            "model": "m",
            "env_key": "K",
            "top_p": "not-a-number",
        },
    )
    assert p.top_p is None


def test_reasoning_sidecar_writes_content(tmp_path, monkeypatch):
    import scripts.delegate as d

    results = tmp_path / "results"
    monkeypatch.setattr(d, "RESULTS_DIR", results)
    monkeypatch.setattr(d, "REVIEWS_DIR", tmp_path)
    monkeypatch.setattr(d, "PENDING_DIR", tmp_path / "pending")
    monkeypatch.setattr(d, "DELEGATIONS_LOG", tmp_path / "delegations.jsonl")

    reasoning = "Let me think through this.\nStep 1: ...\nStep 2: ..."
    d._write_reasoning_sidecar("TASK-REASON-1", reasoning)
    sidecar = results / "TASK-REASON-1.reasoning.txt"
    assert sidecar.exists()
    assert sidecar.read_text(encoding="utf-8") == reasoning


def test_reasoning_sidecar_separate_from_raw(tmp_path, monkeypatch):
    """Reasoning and raw sidecars are written to distinct files for the same task."""
    import scripts.delegate as d

    results = tmp_path / "results"
    monkeypatch.setattr(d, "RESULTS_DIR", results)
    monkeypatch.setattr(d, "REVIEWS_DIR", tmp_path)
    monkeypatch.setattr(d, "PENDING_DIR", tmp_path / "pending")
    monkeypatch.setattr(d, "DELEGATIONS_LOG", tmp_path / "delegations.jsonl")

    d._write_raw_sidecar("TASK-DUAL-1", "raw output")
    d._write_reasoning_sidecar("TASK-DUAL-1", "reasoning trace")

    raw = results / "TASK-DUAL-1.raw.txt"
    reason = results / "TASK-DUAL-1.reasoning.txt"
    assert raw.exists() and reason.exists()
    assert raw.read_text(encoding="utf-8") == "raw output"
    assert reason.read_text(encoding="utf-8") == "reasoning trace"


def test_kimi_thinking_profile_has_thinking_enabled(tmp_path, monkeypatch):
    """End-to-end verification that the architecture.yaml kimi entry is
    configured for thinking mode."""
    import scripts.delegate as d

    # Point at the real project architecture.yaml rather than writing a test fixture —
    # this test is specifically verifying the shipped config matches operator intent.
    d._worker_config_cache = None
    d.ARCHITECTURE_FILE = PROJECT_ROOT / ".rsi" / "architecture.yaml"
    profile = d._load_worker_profile("kimi")
    assert profile.temperature == 1.0, (
        f"kimi default must be thinking-mode (temp 1.0); got {profile.temperature}"
    )
    assert profile.extra_body == {"thinking": {"type": "enabled"}}
    assert profile.top_p == 0.95


def test_kimi_instant_profile_available_as_opt_out(tmp_path):
    """kimi-instant provides explicit instant-mode routing for surgical tasks."""
    import scripts.delegate as d

    d._worker_config_cache = None
    d.ARCHITECTURE_FILE = PROJECT_ROOT / ".rsi" / "architecture.yaml"
    profile = d._load_worker_profile("kimi-instant")
    assert profile.temperature == 0.6
    assert profile.extra_body == {"thinking": {"type": "disabled"}}
    assert profile.top_p == 0.95


def test_load_worker_profile_end_to_end(tmp_path):
    _write_arch(
        tmp_path,
        """
        workers:
          kimi:
            provider: "kimi"
            base_url: "https://api.moonshot.ai/v1"
            model: "kimi-k2.6"
            temperature: 0.6
            max_output_lines: 2000
            client_timeout_seconds: 1800
            max_retries: 3
            extra_body: {"thinking": {"type": "disabled"}}
            output_format_preference: "either"
            env_key: "KIMI_API_KEY"
        """,
    )
    from scripts.delegate import _load_worker_profile

    p = _load_worker_profile("kimi")
    assert p.name == "kimi"
    assert p.model == "kimi-k2.6"
    assert p.temperature == 0.6
    assert p.max_output_lines == 2000
    assert p.client_timeout_seconds == 1800
    assert p.max_retries == 3
    assert p.extra_body == {"thinking": {"type": "disabled"}}
    assert p.output_format_preference == "either"
