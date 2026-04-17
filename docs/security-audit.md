# Security Audit — 2026-04-17

**Scope:** full codebase audit of the RSI Framework after migration to native Windows and publication to GitHub.
**Method:** manual + tool-assisted review across secrets, injection, path safety, LLM trust boundaries, dynamic code, dependencies, and git history.

## Findings summary

| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | **HIGH** | Path traversal in `apply_changes` — worker-controlled paths could escape PROJECT_ROOT | **FIXED** |
| 2 | **HIGH** | `validate_task` did not reject absolute or traversal paths in `files_to_modify` / `files_to_read` | **FIXED** |
| 3 | MEDIUM | `.gitignore` did not cover common secret-bearing file patterns (`.env`, `*.pem`, `credentials.*`, SSH keys, cloud SDK dirs) | **FIXED** |
| 4 | MEDIUM | Dependency version pins were too loose (`pydantic>=2.0`, `openai>=1.0`) — ancient versions with CVEs would satisfy them | **FIXED** |
| 5 | LOW (not a bug) | GitHub PAT embedded in local `.git/config` remote URL | **NOT a leak** — token never entered tracked files or git history. User advised to switch to a credential helper and rotate. |
| 6 | LOW | Override file name uses simple path-character substitution; two distinct filepaths could collide on the override filename | Accepted — no security impact (overrides are in a fixed dir and controlled by the local user) |
| 7 | LOW | `EDITOR` env var is passed as argv[0] in `framework_sync.py` | Accepted — requires local env control, same-user scope |

## What was scanned and found clean

- **Subprocess usage** — every call in `scripts/`, `adapters/`, `engine/` uses list-form argv. Zero `shell=True`, zero `os.system`/`os.popen`. `adapters/tool_wrappers.py` uses `shlex.split` to tokenize user-supplied command strings before passing to subprocess.
- **Dynamic code execution** — no `eval`, `exec`, `compile`, `__import__`, `pickle.loads`, or `yaml.load` in production code. `rules_engine.py` explicitly implements a hand-rolled safe evaluator.
- **Git history for secrets** — scanned all commits for API keys, tokens, passwords, PEM blocks, cloud credentials. Clean. The only hit was a placeholder `sk-...` string in README documentation.
- **Tracked files for credentials** — no `.env`, `*.pem`, `credentials.*`, `id_rsa`, or similar ever committed.
- **Review/result data leakage** — `save_result` strips `raw_response` before writing `.memory/reviews/results/*.json`. Delegations log (`delegations.jsonl`) stores only metadata (task_id, verdict, tokens, latency) — no prompt/response content.
- **Dependency CVEs (our chain)** — `pydantic` and `openai` (which uses `httpx`, not `urllib3`) have no known CVEs at installed versions. `pip-audit` on the declared dependency set is clean.

---

## Finding 1 — HIGH: Path traversal in `apply_changes` (fixed)

### Vulnerability

`scripts/delegate.py:apply_changes` previously iterated worker output like:

```python
for filepath, content in result.get("changes", {}).items():
    full_path = PROJECT_ROOT / filepath
    full_path.write_text(content, encoding="utf-8")
```

Python's `pathlib.PurePath.__truediv__` discards the left side when the right is absolute. So a worker response of:

```json
{"changes": {"/etc/passwd": "compromised\n"}}
```

would resolve to `/etc/passwd` — `PROJECT_ROOT / "/etc/passwd"` == `Path("/etc/passwd")` — and be written with the current user's privileges. Relative traversal via `../../etc/passwd` produced the same escape.

### Threat model

- A compromised or adversarially prompted MiniMax endpoint.
- A maliciously authored task spec (anyone with write access to `.rsi/tasks/`) that declares `files_to_modify: ["../../etc/passwd"]` — which would then pass through the existing `files_to_modify ⊇ changes` validator because the malicious path appears on both sides.
- A prompt-injection in file contents read by the worker that convinces it to emit paths outside the project.

In all three cases, the previous code would silently overwrite a file outside the project.

### Fix

Added `_safe_project_path` in `scripts/delegate.py`:

```python
def _safe_project_path(filepath: str) -> Path:
    p = Path(filepath)
    if p.is_absolute() or (len(filepath) >= 2 and filepath[1] == ":"):
        raise UnsafePathError(f"Absolute paths are not allowed: {filepath!r}")
    candidate = (PROJECT_ROOT / p).resolve()
    root = PROJECT_ROOT.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise UnsafePathError(f"Path escapes project root: {filepath!r}") from exc
    return candidate
```

Called from:
- `apply_changes` — refuses unsafe worker paths (writes skipped, error logged)
- `_git_revert` — same bound on the revert path
- `build_worker_prompt` — same bound on `files_to_read` so no arbitrary host file gets dumped into the LLM prompt
- `call_worker` — post-parse check on every path in the worker `changes` dict
- `validate_task` — pre-flight check on both `files_to_modify` and `files_to_read`

### Regression tests

`tests/test_path_safety.py`:
- 16 test cases covering absolute paths (Unix + Windows drive letters), traversal (`../`, deep `../../../`), and benign in-root paths.
- Tests exercise both the `_safe_project_path` helper directly and the `validate_task` entry point end-to-end.

---

## Finding 2 — HIGH: `validate_task` accepted absolute / traversal paths (fixed)

### Vulnerability

The pre-flight `validate_task` would happily accept task specs like:

```json
{"files_to_modify": ["/etc/passwd"], ...}
```

The only path check was against the constitution pattern list — which matched on glob style, not on path safety. `classify_file("/etc/passwd")` returned `"guarded"`, not `"blocked"`.

### Fix

`validate_task` now runs `_safe_project_path` against every entry in `files_to_read` and `files_to_modify`, and emits a `BLOCKED` issue for any that fail. Unsafe specs cannot be delegated.

Covered by the same `test_path_safety.py::TestValidateTaskPathSafety` test class.

---

## Finding 3 — MEDIUM: `.gitignore` missing secret patterns (fixed)

### Gap

The prior `.gitignore` covered Python caches and RSI runtime state but not the canonical list of sensitive file patterns. A user or agent could have placed a `.env`, a PEM key, or a `credentials.json` in the repo tree and accidentally tracked it.

### Fix

Added a `# Secrets and credentials — NEVER commit these.` block to `.gitignore`:

```
.env           .env.*         *.env        .envrc
*.pem          *.key          *.p12        *.pfx
id_rsa         id_rsa.*       id_ed25519   id_ed25519.*
*.gpg          *.asc
credentials.json  credentials.yaml  credentials.yml
secrets.json      secrets.yaml      secrets.yml
service-account*.json
.aws/   .gcloud/   .azure/
.netrc  .pypirc
.openai/  .anthropic/  .minimax/
```

Verified with `git check-ignore -v` against 8 representative filenames — all blocked.

---

## Finding 4 — MEDIUM: loose dependency version pins (fixed)

### Gap

`pyproject.toml` declared:

```
dependencies = [
    "pydantic>=2.0",
    "openai>=1.0",
]
```

`openai 1.0` shipped in late 2023, before several CVE-motivated fixes (including the switch from `urllib3` to `httpx`). A fresh install with an aggressive version solver could legitimately resolve to vulnerable versions.

### Fix

Tightened to audited minima:

```
"pydantic>=2.8,<3"
"openai>=1.40,<3"
```

`pydantic 2.8+` matches the Pydantic v2 API used by `engine/protocol.py`. `openai 1.40+` is the first release that uses httpx by default and supports the OpenAI-compatible `/v1/chat/completions` surface MiniMax implements.

Also added `[project.optional-dependencies].dev` so `pip install -e ".[dev]"` installs mypy, ruff, pre-commit, pip-audit, and pytest at audited versions.

---

## Finding 5 — NOT a leak: GitHub PAT in local `.git/config`

Observed in `git remote -v` output:

```
origin https://x-access-token:gho_XXXX@github.com/VincentOduro/rsi-framework.git
```

### Verification

- `.git/config` is a per-clone, local-only file — never pushed to the remote.
- `git log --all -p | grep -E 'gho_|ghp_|x-access-token'` → no matches in commit history.
- `git grep -n "x-access-token\|gho_"` against tracked files → no matches.
- The token was transmitted to GitHub over HTTPS as the push password; it was used by the push, but not stored anywhere it could leak.

### Recommended user action

1. Rotate the PAT in GitHub → Settings → Developer settings → Tokens.
2. Switch to a credential helper:
   ```bash
   git remote set-url origin https://github.com/VincentOduro/rsi-framework.git
   gh auth login    # or configure a Git Credential Manager / osxkeychain
   ```
3. Going forward, avoid embedding PATs in remote URLs — they appear in `git remote -v`, shell history, and any CI log that dumps environment state.

Credential-hygiene guidance added to the README.

---

## Findings 6 & 7 — LOW: accepted as not-vulnerabilities

### 6. Override filename collision

`scripts/hooks.py:create_override` flattens `/` and `\` in the filepath to `_` when naming the override file. Two distinct filepaths could produce the same override filename (e.g., `a/b` and `a_b`), causing one to shadow the other. Not a security issue because overrides are created by an authenticated local user with write access to the repo; a colliding override just means the more-recent one wins.

### 7. `EDITOR` env var used as argv[0]

`scripts/framework_sync.py:295` reads `os.environ["EDITOR"]` and invokes it as the first arg of a `subprocess.run([editor, FEEDBACK_FILE])` call. An attacker who can set env vars in the user's shell is already inside the trust boundary — setting `EDITOR=rm` would delete the feedback file on the next `rsi sync`, but an attacker with env-var control can do much worse directly.

Both accepted as out-of-scope for this audit.

---

## Deferred (not addressed this pass)

- **Secret scanner in CI.** `scripts/ci_check.sh` already grep-scans for `sk-*`, `ghp_*`, `AIza*`, and PEM blocks. Adding a proper [gitleaks](https://github.com/gitleaks/gitleaks) or [trufflehog](https://github.com/trufflesecurity/trufflehog) step would catch broader patterns. Worth a separate task.
- **SBOM generation.** `pip-audit --cyclonedx` would produce a machine-readable SBOM for distribution — useful if this framework ever ships as a package, not blocking for a template repo.
- **Signed commits.** The project doesn't require `commit.gpgSign`; a downstream user's policy decision.

## Tests

`pytest tests/ -q` → **175 passed, 1 skipped** (was 159, added 16 security regression tests).
