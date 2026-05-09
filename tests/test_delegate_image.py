"""Tests for the capability='image' worker path in scripts/delegate.py.

These cover the unit-level wiring (config parsing, routing, validation,
mocked end-to-end). The real-vendor end-to-end is exercised by manually
running .rsi/tasks/TASK-IMG-002.json through delegate.py — out of scope
for unit tests because it costs vendor tokens and time.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import delegate as d  # noqa: E402


# ---------------------------------------------------------------------------
# WorkerProfile.capability / image_endpoint parsing
# ---------------------------------------------------------------------------


def test_worker_profile_defaults_to_text_capability():
    profile = d.WorkerProfile.from_config(
        "minimax",
        {
            "provider": "minimax",
            "base_url": "x",
            "model": "y",
            "env_key": "K",
        },
    )
    assert profile.capability == "text"
    assert profile.image_endpoint == "/image_generation"


def test_worker_profile_parses_image_capability():
    profile = d.WorkerProfile.from_config(
        "minimax-image",
        {
            "provider": "minimax",
            "base_url": "x",
            "model": "image-01",
            "env_key": "K",
            "capability": "image",
            "image_endpoint": "/image_generation",
        },
    )
    assert profile.capability == "image"
    assert profile.image_endpoint == "/image_generation"


def test_worker_profile_lowercases_capability():
    profile = d.WorkerProfile.from_config(
        "x", {"provider": "x", "base_url": "x", "model": "x", "env_key": "K", "capability": "IMAGE"}
    )
    assert profile.capability == "image"


# ---------------------------------------------------------------------------
# Capability-aware routing
# ---------------------------------------------------------------------------


def test_required_capability_defaults_to_text():
    assert d._required_capability({}) == "text"
    assert d._required_capability({"task_kind": "code"}) == "text"


def test_required_capability_image_for_image_kind():
    assert d._required_capability({"task_kind": "image"}) == "image"


def test_resolve_worker_explicit_routing_trusts_user(monkeypatch):
    """Explicit task['worker'] is returned even if it doesn't match capability —
    the user / overlord may know something the round-robin doesn't."""
    monkeypatch.setattr(d, "_active_worker", None)
    task = {"task_kind": "image", "worker": "minimax"}  # text worker for image task
    assert d._resolve_worker(task) == "minimax"


def test_resolve_worker_filters_round_robin_by_capability(monkeypatch):
    """Round-robin path must only return capability-matching workers."""
    monkeypatch.setattr(d, "_active_worker", None)
    monkeypatch.setattr(d, "_round_robin_index", 0)

    fake_text = d.WorkerProfile(
        name="minimax", provider="minimax", base_url="x", model="y", env_key="K"
    )
    fake_image = d.WorkerProfile(
        name="minimax-image",
        provider="minimax",
        base_url="x",
        model="image-01",
        env_key="K",
        capability="image",
    )

    profiles = {"minimax": fake_text, "minimax-image": fake_image}

    def fake_load(name):
        return profiles[name]

    monkeypatch.setattr(d, "_get_available_workers", lambda: ["minimax", "minimax-image"])
    monkeypatch.setattr(d, "_load_worker_profile", fake_load)

    chosen = d._resolve_worker({"task_kind": "image"})
    assert chosen == "minimax-image"


def test_resolve_worker_returns_none_when_no_image_worker(monkeypatch):
    monkeypatch.setattr(d, "_active_worker", None)
    monkeypatch.setattr(d, "_round_robin_index", 0)

    fake_text = d.WorkerProfile(
        name="minimax", provider="minimax", base_url="x", model="y", env_key="K"
    )
    monkeypatch.setattr(d, "_get_available_workers", lambda: ["minimax"])
    monkeypatch.setattr(d, "_load_worker_profile", lambda n: fake_text)

    assert d._resolve_worker({"task_kind": "image"}) is None


# ---------------------------------------------------------------------------
# validate_task — image task flow
# ---------------------------------------------------------------------------


def test_validate_task_image_requires_image_outputs():
    task = {
        "id": "TASK-T1",
        "task_kind": "image",
        "description": "x",
        "instruction": "x",
        "files_to_modify": ["a.jpg"],
        "acceptance_criteria": ["x"],
        "proof_wrong": "x",
        "image_outputs": [],
    }
    issues = d.validate_task(task)
    assert any("image_outputs" in i for i in issues)


def test_validate_task_image_outputs_must_be_subset_of_files_to_modify():
    task = {
        "id": "TASK-T2",
        "task_kind": "image",
        "description": "x",
        "instruction": "x",
        "files_to_modify": ["a.jpg"],
        "acceptance_criteria": ["x"],
        "proof_wrong": "x",
        "image_outputs": ["b.jpg"],
    }
    issues = d.validate_task(task)
    assert any("must also appear in files_to_modify" in i for i in issues)


def test_validate_task_image_passes_with_matching_paths():
    task = {
        "id": "TASK-T3",
        "task_kind": "image",
        "description": "x",
        "instruction": "x",
        "files_to_modify": ["assets/generated/x.jpg"],
        "acceptance_criteria": ["x"],
        "proof_wrong": "x",
        "image_outputs": ["assets/generated/x.jpg"],
    }
    issues = d.validate_task(task)
    # No image-validation issues. (May still have schema issues from upstream,
    # but the image-specific checks should be clean.)
    image_specific = [i for i in issues if "image" in i.lower()]
    assert image_specific == []


# ---------------------------------------------------------------------------
# call_image_worker — mocked end-to-end
# ---------------------------------------------------------------------------


@pytest.fixture
def image_profile(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    return d.WorkerProfile(
        name="minimax-image",
        provider="minimax",
        base_url="https://api.minimaxi.chat/v1",
        model="image-01",
        env_key="MINIMAX_API_KEY",
        capability="image",
        image_endpoint="/image_generation",
        client_timeout_seconds=30,
    )


def test_call_image_worker_rejects_missing_image_outputs(image_profile):
    task = {"id": "T", "instruction": "p", "image_outputs": []}
    result = d.call_image_worker(task, image_profile)
    assert "image_outputs" in result["error"]


def test_call_image_worker_rejects_unsafe_path(image_profile):
    task = {"id": "T", "instruction": "p", "image_outputs": ["../../etc/passwd"]}
    result = d.call_image_worker(task, image_profile)
    assert "Unsafe" in result["error"] or "escape" in result["error"]


def test_call_image_worker_handles_vendor_error(image_profile, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target_rel = "out/img_0.jpg"

    def fake_post(url, headers, body, timeout):
        return {"base_resp": {"status_code": 1024, "status_msg": "rate limited"}}

    monkeypatch.setattr(d, "_post_json", fake_post)
    monkeypatch.setattr(d, "PROJECT_ROOT", tmp_path)
    task = {"id": "T", "instruction": "p", "image_outputs": [target_rel]}
    result = d.call_image_worker(task, image_profile)
    assert "rate limited" in result["error"]


def test_call_image_worker_count_mismatch(image_profile, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(d, "PROJECT_ROOT", tmp_path)

    def fake_post(url, headers, body, timeout):
        # Returns 2 URLs but task asked for 1
        return {
            "id": "abc",
            "data": {"image_urls": ["http://x/a.jpg", "http://x/b.jpg"]},
            "base_resp": {"status_code": 0},
        }

    monkeypatch.setattr(d, "_post_json", fake_post)
    task = {"id": "T", "instruction": "p", "image_outputs": ["out/x.jpg"]}
    result = d.call_image_worker(task, image_profile)
    assert "2 url" in result["error"]
    assert "1 image_outputs" in result["error"]


def test_call_image_worker_writes_files_on_success(image_profile, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(d, "PROJECT_ROOT", tmp_path)

    captured_request: dict = {}

    def fake_post(url, headers, body, timeout):
        captured_request["url"] = url
        captured_request["body"] = body
        return {
            "id": "req-abc-123",
            "data": {"image_urls": ["http://vendor/a.jpg", "http://vendor/b.jpg"]},
            "base_resp": {"status_code": 0},
            "metadata": {"success_count": "2", "failed_count": "0"},
        }

    def fake_download(url, target, timeout):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\xff\xd8\xff\xe0FAKE_JPEG")
        return 9

    monkeypatch.setattr(d, "_post_json", fake_post)
    monkeypatch.setattr(d, "_download_to_path", fake_download)

    task = {
        "id": "T",
        "instruction": "a small red cube",
        "image_aspect_ratio": "1:1",
        "image_outputs": ["out/a.jpg", "out/b.jpg"],
    }
    result = d.call_image_worker(task, image_profile)

    assert "error" not in result or result.get("error") is None or result.get("error") == ""
    assert result["changes"] == {}
    assert len(result["image_outputs"]) == 2
    assert result["image_outputs"][0]["path"] == "out/a.jpg"
    assert result["image_outputs"][0]["request_id"] == "req-abc-123"
    assert result["image_outputs"][0]["bytes"] == 9
    assert result["image_outputs"][0]["aspect_ratio"] == "1:1"
    assert (tmp_path / "out/a.jpg").exists()
    assert (tmp_path / "out/b.jpg").exists()
    # Vendor request format
    assert captured_request["url"] == "https://api.minimaxi.chat/v1/image_generation"
    assert captured_request["body"]["n"] == 2
    assert captured_request["body"]["prompt"] == "a small red cube"
    assert captured_request["body"]["response_format"] == "url"


def test_call_image_worker_rolls_back_on_partial_download(image_profile, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(d, "PROJECT_ROOT", tmp_path)

    def fake_post(url, headers, body, timeout):
        return {
            "id": "req",
            "data": {"image_urls": ["http://vendor/a.jpg", "http://vendor/b.jpg"]},
            "base_resp": {"status_code": 0},
        }

    call_count = [0]

    def fake_download(url, target, timeout):
        call_count[0] += 1
        if call_count[0] == 1:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"first")
            return 5
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(d, "_post_json", fake_post)
    monkeypatch.setattr(d, "_download_to_path", fake_download)

    task = {
        "id": "T",
        "instruction": "p",
        "image_outputs": ["out/a.jpg", "out/b.jpg"],
    }
    result = d.call_image_worker(task, image_profile)
    assert "Download failed" in result["error"]
    assert "out/b.jpg" in result["error"]
    # Rolled back the first successfully-written file
    assert not (tmp_path / "out/a.jpg").exists()


# ---------------------------------------------------------------------------
# call_worker dispatch routing
# ---------------------------------------------------------------------------


def test_call_worker_dispatches_to_image_path_for_image_capability(monkeypatch):
    image_profile = d.WorkerProfile(
        name="minimax-image",
        provider="minimax",
        base_url="x",
        model="image-01",
        env_key="K",
        capability="image",
    )
    monkeypatch.setattr(d, "_resolve_worker", lambda task: "minimax-image")
    monkeypatch.setattr(d, "_load_worker_profile", lambda name: image_profile)
    sentinel = {"changes": {}, "image_outputs": [{"path": "x.jpg"}], "tokens_used": 0}
    monkeypatch.setattr(d, "call_image_worker", lambda task, profile: sentinel)

    result = d.call_worker({"id": "T", "task_kind": "image"})
    assert result is sentinel


# ---------------------------------------------------------------------------
# apply_changes for image tasks
# ---------------------------------------------------------------------------


def test_apply_image_outputs_skips_text_verify(tmp_path, monkeypatch):
    monkeypatch.setattr(d, "PROJECT_ROOT", tmp_path)
    target = tmp_path / "out" / "img.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"\xff\xd8\xff\xe0FAKE")

    git_calls: list = []

    def fake_checkpoint(task_id, files):
        git_calls.append((task_id, files))

    monkeypatch.setattr(d, "_git_checkpoint", fake_checkpoint)
    # If the text verify ever fires for image tasks, fail the test.
    monkeypatch.setattr(d, "_run_verify", lambda files: pytest.fail("verify must not run for image tasks"))

    task = {"id": "T-IMG", "task_kind": "image"}
    result = {"image_outputs": [{"path": "out/img.jpg"}]}
    applied = d.apply_changes(task, result)
    assert applied == ["out/img.jpg"]
    assert git_calls == [("T-IMG", ["out/img.jpg"])]


def test_apply_image_outputs_skips_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(d, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(d, "_git_checkpoint", lambda *a, **kw: None)

    task = {"id": "T", "task_kind": "image"}
    result = {"image_outputs": [{"path": "nope/missing.jpg"}]}
    applied = d.apply_changes(task, result)
    assert applied == []
