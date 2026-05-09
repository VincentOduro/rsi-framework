"""Tests for F5 (per-worker temperature) and F9 (per-worker max_output_lines.

Worker-specific knobs previously hardcoded in delegate.py must now be read from
architecture.yaml workers.<name> entries, with documented defaults preserving
prior MiniMax-calibrated behavior when the fields are omitted.
"""

import sys
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _reset_worker_cache():
    import scripts.delegate as d

    d._worker_config_cache = None


def _write_arch(tmp_path, yaml_text):
    import scripts.delegate as d

    path = tmp_path / "architecture.yaml"
    path.write_text(textwrap.dedent(yaml_text).lstrip("\n"), encoding="utf-8")
    d.ARCHITECTURE_FILE = path
    _reset_worker_cache()
    return path


# ---------------------------------------------------------------------------
# F5 — per-worker temperature
# ---------------------------------------------------------------------------


def test_worker_with_explicit_temperature_reads_value(tmp_path, monkeypatch):
    _write_arch(
        tmp_path,
        """
        workers:
          kimi:
            provider: "kimi"
            base_url: "https://api.moonshot.cn/v1"
            model: "moonshot-v1-128k"
            temperature: 0.6
            env_key: "KIMI_API_KEY"
        """,
    )
    from scripts.delegate import _load_worker_config

    config = _load_worker_config("kimi")
    assert float(config["temperature"]) == 0.6


def test_worker_extra_body_json_parses_valid_nested(tmp_path, monkeypatch):
    _write_arch(
        tmp_path,
        """
        workers:
          kimi:
            provider: "kimi"
            base_url: "https://api.moonshot.ai/v1"
            model: "kimi-k2.6"
            temperature: 0.6
            extra_body_json: '{"thinking": {"type": "disabled"}}'
            env_key: "KIMI_API_KEY"
        """,
    )
    import json

    from scripts.delegate import _load_worker_config

    cfg = _load_worker_config("kimi")
    parsed = json.loads(cfg["extra_body_json"])
    assert parsed == {"thinking": {"type": "disabled"}}


def test_worker_without_temperature_defaults_to_0_3(tmp_path, monkeypatch):
    _write_arch(
        tmp_path,
        """
        workers:
          legacy:
            provider: "minimax"
            base_url: "https://api.minimaxi.chat/v1"
            model: "MiniMax-M2.7"
            env_key: "MINIMAX_API_KEY"
        """,
    )
    from scripts.delegate import _load_worker_config

    config = _load_worker_config("legacy")
    assert float(config["temperature"]) == 0.3


# ---------------------------------------------------------------------------
# F9 — per-worker max_output_lines
# ---------------------------------------------------------------------------


def _task(files_to_modify, worker=None):
    spec = {
        "id": "TASK-F9",
        "description": "probe",
        "instruction": "probe",
        "files_to_read": [],
        "files_to_modify": files_to_modify,
        "acceptance_criteria": ["passes"],
        "proof_wrong": "might truncate",
        "constraints": [],
    }
    if worker:
        spec["worker"] = worker
    return spec


def test_worker_with_raised_max_output_lines_accepts_larger_files(tmp_path, monkeypatch):
    # arch with kimi at 2000-line threshold
    _write_arch(
        tmp_path,
        """
        workers:
          kimi:
            provider: "kimi"
            base_url: "https://api.moonshot.cn/v1"
            model: "moonshot-v1-128k"
            temperature: 0.6
            max_output_lines: 2000
            env_key: "KIMI_API_KEY"
        """,
    )
    # Create a 665-line file to modify — previous hardcoded 500 cap blocked this
    target_rel = "tests/_probe_large.py"
    target = PROJECT_ROOT / target_rel
    target.write_text("\n".join(f"# line {i}" for i in range(665)), encoding="utf-8")
    try:
        from scripts.delegate import validate_task

        issues = validate_task(_task([target_rel], worker="kimi"))
        assert not any("has 665 lines" in i for i in issues), (
            f"Kimi at 2000-line cap should not warn on 665-line file; got: {issues}"
        )
    finally:
        target.unlink()


def test_worker_without_override_uses_500_default(tmp_path, monkeypatch):
    _write_arch(
        tmp_path,
        """
        workers:
          legacy:
            provider: "minimax"
            base_url: "https://api.minimaxi.chat/v1"
            model: "MiniMax-M2.7"
            env_key: "MINIMAX_API_KEY"
        """,
    )
    # 600-line file exceeds the 500 default → warning expected
    target_rel = "tests/_probe_default.py"
    target = PROJECT_ROOT / target_rel
    target.write_text("\n".join(f"# line {i}" for i in range(600)), encoding="utf-8")
    try:
        from scripts.delegate import validate_task

        issues = validate_task(_task([target_rel], worker="legacy"))
        assert any(">500" in i for i in issues), (
            f"Default 500-line threshold should fire on 600-line file; got: {issues}"
        )
    finally:
        target.unlink()


def test_error_message_names_worker_and_threshold(tmp_path, monkeypatch):
    _write_arch(
        tmp_path,
        """
        workers:
          tightworker:
            provider: "minimax"
            base_url: "https://api.minimaxi.chat/v1"
            model: "MiniMax-M2.7"
            max_output_lines: 100
            env_key: "MINIMAX_API_KEY"
        """,
    )
    target_rel = "tests/_probe_small.py"
    target = PROJECT_ROOT / target_rel
    target.write_text("\n".join(f"# line {i}" for i in range(150)), encoding="utf-8")
    try:
        from scripts.delegate import validate_task

        issues = validate_task(_task([target_rel], worker="tightworker"))
        hits = [i for i in issues if "tightworker" in i and "100" in i]
        assert hits, f"Warning should name worker and threshold; got: {issues}"
    finally:
        target.unlink()


# ---------------------------------------------------------------------------
# DeepSeek worker configs
# ---------------------------------------------------------------------------


def test_deepseek_flash_profile_fields(tmp_path):
    _write_arch(
        tmp_path,
        """
        workers:
          deepseek-flash:
            provider: deepseek
            base_url: https://api.deepseek.com
            model: deepseek-v4-flash
            env_key: DEEPSEEK_API_KEY
            temperature: 0.3
            max_concurrency: 15
        """,
    )
    from scripts.delegate import _load_worker_profile

    profile = _load_worker_profile("deepseek-flash")
    assert profile.provider == "deepseek"
    assert profile.model == "deepseek-v4-flash"
    assert profile.temperature == 0.3
    assert profile.omit_temperature == False
    assert profile.max_concurrency == 15


def test_deepseek_pro_thinking_omit_temperature(tmp_path):
    _write_arch(
        tmp_path,
        """
        workers:
          deepseek-pro-thinking:
            provider: deepseek
            base_url: https://api.deepseek.com
            model: deepseek-v4-pro
            env_key: DEEPSEEK_API_KEY
            omit_temperature: true
            max_tokens: 32768
            extra_body: {"thinking": {"type": "enabled", "reasoning_effort": "max"}}
        """,
    )
    from scripts.delegate import _load_worker_profile

    profile = _load_worker_profile("deepseek-pro-thinking")
    assert profile.omit_temperature == True
    assert profile.max_tokens == 32768
    assert profile.extra_body == {"thinking": {"type": "enabled", "reasoning_effort": "max"}}


def test_deepseek_workers_discovered_when_key_set(tmp_path, monkeypatch):
    _write_arch(
        tmp_path,
        """
        workers:
          deepseek-flash:
            provider: deepseek
            base_url: https://api.deepseek.com
            model: deepseek-v4-flash
            env_key: DEEPSEEK_API_KEY
          deepseek-pro:
            provider: deepseek
            base_url: https://api.deepseek.com
            model: deepseek-chat
            env_key: DEEPSEEK_API_KEY
          deepseek-pro-thinking:
            provider: deepseek
            base_url: https://api.deepseek.com
            model: deepseek-reasoner
            env_key: DEEPSEEK_API_KEY
        """,
    )
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    from scripts.delegate import _get_available_workers

    workers = _get_available_workers()
    assert "deepseek-flash" in workers
    assert "deepseek-pro" in workers
    assert "deepseek-pro-thinking" in workers


def test_deepseek_workers_absent_when_key_unset(tmp_path, monkeypatch):
    _write_arch(
        tmp_path,
        """
        workers:
          deepseek-flash:
            provider: deepseek
            base_url: https://api.deepseek.com
            model: deepseek-v4-flash
            env_key: DEEPSEEK_API_KEY
          deepseek-pro:
            provider: deepseek
            base_url: https://api.deepseek.com
            model: deepseek-chat
            env_key: DEEPSEEK_API_KEY
          deepseek-pro-thinking:
            provider: deepseek
            base_url: https://api.deepseek.com
            model: deepseek-reasoner
            env_key: DEEPSEEK_API_KEY
        """,
    )
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    from scripts.delegate import _get_available_workers

    workers = _get_available_workers()
    assert "deepseek-flash" not in workers
    assert "deepseek-pro" not in workers
    assert "deepseek-pro-thinking" not in workers


def test_omit_temperature_false_when_field_absent(tmp_path):
    _write_arch(
        tmp_path,
        """
        workers:
          defaultworker:
            provider: minimax
            base_url: https://api.minimaxi.chat/v1
            model: MiniMax-M2.7
            env_key: MINIMAX_API_KEY
        """,
    )
    from scripts.delegate import _load_worker_profile

    profile = _load_worker_profile("defaultworker")
    assert profile.omit_temperature == False
