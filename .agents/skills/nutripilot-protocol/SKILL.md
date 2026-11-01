---
name: nutripilot-protocol
description: >-
  Operational runbook for NutriPilot v1 development. Enforces PROGRESS.md protocol,
  commit rules, phase gates, code reviews (R1-R7), fix passes (F1-F7), and core design invariants.
---

# NutriPilot Development Protocol & Governance

This skill enforces the operating procedures specified in `PROGRESS.md` for implementing NutriPilot v1.

## 1. Operating Rules

### 1.1 Task Lifecycle
1. Open `PROGRESS.md` and find the **first** unchecked `[ ]` task from top to bottom.
2. Read the referenced sections in `NutriPilot_Technical_Design.md` (TD) and `diet-planner-requirements.md` (Req).
3. Implement only what the task describes; never introduce unjustified layers, DI containers, or ORMs.
4. Run tests: `pytest -q`.
5. Update `PROGRESS.md`: mark the task `[x]`.
6. Commit immediately on the current branch (see commit format).

### 1.2 Mandatory Commit Format
Every task commit must follow this exact format:
```text
<type>(<scope>): <summary> [<TASK-ID>]
```
- **Allowed Types**: `feat`, `fix`, `test`, `chore`, `docs`, `refactor`
- **Mandatory Tag**: `[<TASK-ID>]` (e.g., `[T0.1]`, `[T1.2]`, `[R1]`, `[F1]`, `[T0.G]`)
- **Example**: `feat(settings): add meta field CRUD [T1.2]`
- **Rule**: Never commit `data/` or cache files. Stage only task-relevant files and `PROGRESS.md`.

### 1.3 Phase Gates (`T<n>.G`)
- Each phase ends with a gate task (`T0.G`, `T1.G`, etc.).
- Every sub-checkbox must be verified for real (via automated test or running app with `fake_cli.py`).
- Tick the gate task only when all sub-items pass.
- Commit the gate: `chore(progress): phase <n> gate [T<n>.G]`

### 1.4 Code Reviews (`R<n>`)
- Review tasks (`R1` through `R7`) are mandatory.
- Diff calculation:
  ```bash
  BASE=<previous review commit, or parent of [T0.1] for R1>
  git diff $BASE..HEAD --stat -- . ':!PROGRESS.md' ':!docs/reviews' ':!app/static/htmx.min.js'
  git diff $BASE..HEAD       -- . ':!PROGRESS.md' ':!docs/reviews' ':!app/static/htmx.min.js'
  ```
- Write report to `docs/reviews/REVIEW-0<n>.md` using the template in `PROGRESS.md` Appendix A.
- Assign severity: `Critical`, `High`, `Medium`, `Low`.
- **Do not modify code during a review task.** Commit only the report: `docs(review): REVIEW-0<n> [R<n>]`.

### 1.5 Fix Cycles (`F<n>`)
- Fix all `Critical` and `High` findings, and cheap `Medium` findings.
- Add regression tests for any Critical or High bug.
- Mark findings in the report, update `Resolution:`, and update the Review Log table in `PROGRESS.md`.
- Commit with tag `[F<n>]`.

---

## 2. Fixed Design Invariants (Non-Negotiable)

1. **Boring tech**: One process, one SQLite file with WAL, markdown files on disk, server-rendered HTML with HTMX.
2. **App owns all writes**: The AI only reads; the app parses tags and persists. Client meta requires explicit trainer confirmation (FR-13).
3. **DB is source of truth**: SQLite tracks status, version, and soft deletion.
4. **Soft delete everywhere**: Never execute `DELETE FROM` or `os.remove`. Always filter `deleted_at IS NULL`.
5. **No `shell=True`**: Subprocesses must always use tokenized argv lists.
6. **Security guard**: Reject requests with foreign `Host` (DNS rebinding) or foreign `Origin` on POST (CSRF).
7. **Safe Markdown**: `markdown-it-py` must have raw HTML **disabled** (`html=False`).
