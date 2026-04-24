# Spec-amendment tracking

When a project's implementation knowingly diverges from its design spec —
because the spec has a defect, is silent on an edge case, or the
implementation discovered a better shape — the divergence is *intentional
technical debt* and should be tracked explicitly, not left as a comment in
the code.

RSI provides a lightweight convention for this. The convention is optional;
projects that don't need it pay no cost.

## The convention

1. Projects that want spec-amendment tracking add a file called
   `SPEC_AMENDMENTS.md` (or a project-specific equivalent) at the repo root.
2. The file is classified as **constitution** tier in the project's
   `.rsi/architecture.yaml`, so only the overlord can modify it and every
   change runs constitution-tier ceremony.
3. Each entry captures: spec location, issue description, scaffold
   resolution (with commit SHA), proposed upstream fix, and blocking phase.

Example header for an entry:

```markdown
## I11 — ApplicationStatus.ghosted enum completeness

**Spec location:** spec/models.md §2.3
**Issue:** Spec enumerates four ApplicationStatus values but the workflow
requires a fifth ("ghosted") for applications that never receive a response.
**Scaffold resolution:** Added `GHOSTED = "ghosted"` in commit abc1234;
downstream consumers updated in def5678.
**Proposed upstream fix:** Spec §2.3 should enumerate the fifth value.
**Blocking phase:** None (implementation unblocked).
```

Entries are append-only; resolving an amendment means updating its
`Blocking phase` and `Proposed upstream fix` rather than deleting it.

## Adding the pattern to your architecture.yaml

In the `constitution` block of `.rsi/architecture.yaml`, add the amendment
file's pattern. Inline comments are supported (the YAML-subset parser
strips them before fnmatch compilation — see `scripts/classify_file.py`):

```yaml
file_sensitivity:
  constitution:
    description: "Only overlord can modify. Framework-critical files."
    patterns:
      - "CLAUDE.md"
      - "FRAMEWORK.md"
      - "SPEC_AMENDMENTS.md"  # amendment tracking — see docs/spec-amendments.md
      # Project-specific additions below
      # - "spec/**"            # design-spec directory
```

Once the pattern is in place, `classify_file("SPEC_AMENDMENTS.md")` returns
`"constitution"`, and any edit to the file requires overlord authority —
worker delegations are refused at the task-validation gate.

## Why constitution tier

Amendment entries are the contract between the spec and the implementation.
If a worker could modify them, it could silently "resolve" a divergence by
deleting its entry instead of fixing the underlying code or spec. Keeping
amendments at constitution tier ensures every change is an explicit
decision, visible in ceremony output and git history.

## What RSI does not ship (yet)

This convention is documentation-only in its current form. Future sessions
may add:

- A machine-readable schema for entries (YAML front-matter per section)
- A ceremony hook that surfaces pending amendments on spec-file commits
  ("you touched the spec, are any pending amendments now resolved?")
- Dashboard integration alongside other health indicators

Those are §2.7 items on the RSI roadmap (see
[docs/retrospectives/phase-1-decomposition.md](retrospectives/phase-1-decomposition.md)).
Until they ship, the file is a plain markdown append-log and the ceremony
integration is whatever your project's retrospective cadence chooses to do
with it.
