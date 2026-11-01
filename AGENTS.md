# AGENTS.md — NutriPilot v1

> **Project**: NutriPilot (AI-assisted Diet Planning Web App for Coaches)  
> **Target Audience**: Antigravity AI Coding Agent (AGY)  
> **Source of Truth**: `diet-planner-requirements.md` (Req), `NutriPilot_Technical_Design.md` (TD), `PROGRESS.md`

---

## 1. Core Directives & Principles

1. **Boring Tech, Few Moving Parts**:
   - Single process, one local SQLite file with WAL mode.
   - Server-rendered HTML with FastAPI, Jinja2, and vendored HTMX.
   - Markdown files on disk for sources and plan drafts/approved files.
   - **No ORMs** (raw `sqlite3` with `row_factory = sqlite3.Row`).
   - **No build steps**, no Docker, no external npm packages.
2. **The App Owns All Writes; The AI Only Reads**:
   - The AI reads markdown sources and example plans directly from disk.
   - The AI outputs tagged blocks (`<meta>`, `<plan>`).
   - The app parses blocks and writes DB rows / plan markdown files.
   - Client meta requires explicit coach approval before persisting (`POST /messages/{id}/meta`).
3. **Soft Delete Everywhere**:
   - Never run physical `DELETE FROM` or `os.remove` on user data.
   - Every read query on live records must include `WHERE deleted_at IS NULL`.
   - Cascade soft delete: Deleting a client sets `deleted_at` on the client, its chats, and its plans.
4. **Security & Defensive Engineering**:
   - Middleware rejects foreign `Host` (blocks DNS rebinding) and foreign `Origin` on state-changing requests (blocks CSRF).
   - `markdown-it-py` with `html=False` (prevents XSS).
   - Subprocess calls never use `shell=True`.

---

## 2. Commit & Progress Governance

Follow [`PROGRESS.md`](file:///D:/Project3/NutriPilot/PROGRESS.md) strictly:
1. Complete tasks sequentially from top to bottom.
2. Commit after **every single task** with mandatory format:
   ```text
   <type>(<scope>): <summary> [<TASK-ID>]
   ```
   Example: `feat(skeleton): scaffold project layout and config [T0.1]`
3. Verify Phase Gates (`T0.G` to `T7.G`) before proceeding to the next phase.
4. Conduct formal code reviews (`R1` to `R7`) writing reports in `docs/reviews/REVIEW-0x.md`.
5. Fix review findings in `F1` to `F7` before moving forward.

---

## 3. Project Skills

Specialized skill runbooks are located in [`.agents/skills/`](file:///D:/Project3/NutriPilot/.agents/skills/):
- `nutripilot-protocol`: Task lifecycle, commit conventions, phase gates, and review reports.
- `fastapi-htmx-persian`: HTMX polling, OOB swaps, Persian RTL CSS logical layout, security middleware.
- `sqlite-wal-persistence`: SQLite connection manager, migrations, soft-delete cascades, PyYAML serialization.
- `subprocess-cli-runner`: Safe subprocess execution, Windows process-tree termination, non-greedy regex parsers.
- `pytest-testing-harness`: Pytest fixtures, temporary test environments, and fake CLI test harness.
