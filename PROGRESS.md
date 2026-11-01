# NutriPilot v1 — Implementation Progress

> **Audience:** the AI coding agent implementing NutriPilot v1.
> **Source of truth for _what_ to build:** `docs/TECHNICAL_DESIGN.md` (**TD**) and the requirements doc (**Req**, `FR-n`). Adjust these paths if the files live elsewhere.
> **This file is the source of truth for _where we are_.** Read it at the start of every session; update it at the end of every task.

---

## 0. Operating Rules (read fully before starting)

### 0.1 Checkbox states
| Mark | Meaning |
|---|---|
| `[ ]` | Not started |
| `[x]` | Done: implemented, tests pass, committed |
| `[!]` | Blocked / cannot be completed as specified. Add an indented `Blocked:` note under the task, record a one-line entry in `docs/DECISIONS.md`, and continue with the next unblocked task only if it does not depend on this one |

### 0.2 Resume protocol
1. Open this file and find the **first** `[ ]` task (top to bottom). That is the current task. Do not skip ahead, except past `[!]` tasks.
2. Read the task's `Ref:` sections in TD (and the FR numbers in Req, if any) **before** writing code. Respect **Fixed** items in TD; **Agent discretion** items are yours to decide.
3. Implement only what the task describes. Do not add layers, abstractions, or services the TD does not justify (TD §1, §3).

### 0.3 Definition of done for every task
1. Code works and the full test suite passes (`pytest -q`). Add or extend tests where the task says so.
2. The app still starts (`python run.py`) once Phase 0 is done.
3. Tick the task's checkbox in this file (`[ ]` → `[x]`) **in the same commit**.
4. Commit on the **current branch** (see 0.4). One commit per task, minimum.
5. If you deviated from a **Fixed** item in TD, add a one-line entry to `docs/DECISIONS.md` in the same commit.

### 0.4 Commit rules
- Commit after **every** task, on the current branch. Do not create branches, do not push, do not amend or rebase.
- Stage only the files relevant to the task plus `PROGRESS.md`. Never commit `data/`.
- Message format: `<type>(<scope>): <summary> [<TASK-ID>]` — e.g. `feat(settings): add meta field CRUD [T1.2]`.
  Types: `feat`, `fix`, `test`, `chore`, `docs`, `refactor`. The `[TASK-ID]` tag is **mandatory** (reviews locate commits through it).
- Phase gate tasks (`T<n>.G`) with no code changes still get a commit that only ticks the boxes: `chore(progress): phase <n> gate [T<n>.G]`.

### 0.5 Phase gates
Each phase ends with a `T<n>.G` task listing the "Done when" items from TD §14 as sub-checkboxes. Verify each item for real (automated test, or run the app with the fake CLI and exercise it; use `curl` for HTTP checks). Tick a sub-item only when verified. Tick the gate only when all sub-items are ticked. If an item fails, fix it in the gate's commit (or a preceding `fix` commit) before ticking.

### 0.6 Code review tasks (`R<n>`) — procedure
Review tasks are **not** optional and are **not** a full-codebase review. Each one covers a defined scope of tasks.
1. **Compute the scope diff** (code only; excludes progress/report files and vendored assets):
   ```bash
   BASE=<see the review task>   # previous [R<n-1>] commit, or for R1 the parent of the [T0.1] commit
   git diff $BASE..HEAD --stat -- . ':!PROGRESS.md' ':!docs/reviews' ':!app/static/htmx.min.js'
   git diff $BASE..HEAD       -- . ':!PROGRESS.md' ':!docs/reviews' ':!app/static/htmx.min.js'
   ```
   Find a tagged commit with: `git log --grep='\[R1\]' -1 --format=%H`. If `T0.1` is the repo's first commit (no parent), diff against the empty tree `4b825dc642cb6eb9a060e54bf8d69288fbee4904`.
   Fix commits (`[F<n>]`) made after the previous review fall into the next review's scope automatically.
2. Review **only** the changed code plus the context needed to understand it. If your tooling supports sub-agents, run the review in a fresh one to avoid self-confirmation bias.
3. Check against: the task `Ref:` sections, the **Fixed** contracts in TD, the **review focus** listed in the task, and the generic checklist in Appendix B.
4. Run `pytest -q` and note the result in the report.
5. Write the report to `docs/reviews/REVIEW-0<n>.md` using the template in Appendix A. Every finding gets an ID (`R<n>-01`…), a **severity** (Appendix A), file:line, description, and a suggested fix.
6. **Do not fix anything during the review task.** Only the report file is created/changed. Fixing happens in the `F<n>` task right after.
7. Update the "Review log" table (Section 9) and commit: `docs(review): REVIEW-0<n> [R<n>]`.

### 0.7 Fix tasks (`F<n>`) — procedure
- Open `docs/reviews/REVIEW-0<n>.md`. Fix **all Critical and High** findings and any Medium finding that is cheap (< ~15 min or ≤ ~30 lines). Add a regression test for each Critical/High bug.
- In the report, tick the finding's checkbox and fill `Resolution:` (commit-independent, one line). For findings you decide not to fix now, set `Status: deferred` with a reason (they are handled in `FINAL-FIX`).
- One commit per logical group of fixes, each tagged `[F<n>]`. Update the Review log counts.

### 0.8 Review cadence (why the reviews sit where they do)
Reviews are placed after roughly **6–10 tasks / 600–1000 changed lines** of non-test, non-vendored code, and always right after security- or concurrency-critical code (middleware, upload handling, subprocess runner, turn orchestration, plan lifecycle). Each review therefore takes a bounded amount of effort and covers only work not yet reviewed.

---

## 1. Phase 0 — Skeleton & Infrastructure
*TD §14 Phase 0 · Req §11*

- [x] **T0.1** Scaffold repo per TD §3: directories (`app/`, `app/routes/`, `app/services/`, `app/templates/`, `app/static/`, `tests/`, `docs/`), `run.py` (uvicorn, single worker, `127.0.0.1:8005`), `requirements.txt` (only used packages: fastapi, uvicorn, jinja2, markdown-it-py, PyYAML, python-multipart, pytest, plus `httpx` if needed for `TestClient`), `.gitignore` (`data/`, caches, venv), `README.md` stub, `docs/DECISIONS.md`, and `app/config.py` (paths, `DATA_DIR` env override, constants: `HISTORY_MAX_MESSAGES=30`, `HISTORY_MAX_CHARS=24000`, `EXAMPLES_CAP=50`, `UPLOAD_MAX_BYTES=1_000_000`, host/port, allowed hosts/origins). _Ref: TD §2, §3, §7.2 (caps), §11.2_
- [x] **T0.2** Implement `app/db.py`: `connect()` context manager (new connection per call, `row_factory=sqlite3.Row`, `PRAGMA journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout≈5000`, commit on success / rollback on error); migration runner using `PRAGMA user_version` with an ordered script list; migration 1 = the **complete schema from TD §5 verbatim** (all 7 tables, CHECK constraints, unique partial index, `UNIQUE(sources.file_path)`, all indexes); soft-delete read helpers or `live_*` SQL views so every read filters `deleted_at IS NULL` by default. _Ref: TD §4.3, §5 (schema + notes)_
- [x] **T0.3** Seeding and defaults: seed `users(id=1,'admin')`; seed all settings keys with `INSERT OR IGNORE` (never overwrite); `app/defaults.py` with the default system prompt (Appendix A of TD, verbatim) and **placeholder** command templates for `claude`/`agy`/`codex` (real flags come in T3.5); `current_user_id()` returning `1`. _Ref: TD §5.1, §5 notes, Appendix A (TD)_
- [x] **T0.4** `app/main.py`: FastAPI app with lifespan (create `data/`, `data/sources/`, `data/plans/`; init DB; seed), rotating file log `data/app.log` (~1 MB × 3) + console, and the security middleware: reject requests whose `Host` is not `localhost:8005`/`127.0.0.1:8005` (403); for non-GET/HEAD/OPTIONS reject when `Origin` (or `Referer`) is present and not an allowed origin (403). Make allowed hosts configurable via `config.py` so tests can use `TestClient(base_url="http://localhost:8005")`. _Ref: TD §11.1–11.2, §12, §3 (`main.py`)_
- [ ] **T0.5** Templates & static: `base.html` (`<html lang="fa" dir="rtl">`, nav Chats / Clients / Settings, CSS logical properties), vendored `htmx.min.js` in `app/static/` (no CDN), one small `app.css`, Jinja2 with autoescape on, markdown render helper (`markdown-it-py`, `html=False`) exposed as a Jinja filter, `fmt_date` filter (UTC → local, Gregorian), and three empty-state pages (chats, clients, settings) wired to routes. _Ref: TD §2, §10, §11.4_
- [ ] **T0.6** Tests: `tests/conftest.py` (temp `DATA_DIR` via env, app/TestClient fixture), smoke test (three pages return 200), DB init idempotence (second startup doesn't duplicate/overwrite seeded settings), middleware tests (foreign `Host` → 403; POST with foreign `Origin` → 403; POST without `Origin` allowed). _Ref: TD §13, §14 P0 "Done when"_
- [ ] **T0.G** Phase 0 gate — verify:
  - [ ] `python run.py` serves `http://localhost:8005` with the three nav pages in RTL Persian
  - [ ] `data/app.db` created with all tables; restart does not duplicate/overwrite seeded settings
  - [ ] Foreign `Origin` on POST and foreign `Host` are rejected
  - [ ] `pytest` passes

- [ ] **R1** **Code review — Phase 0 foundation.** Scope: T0.1–T0.G. BASE = parent of the `[T0.1]` commit (see 0.6). Report: `docs/reviews/REVIEW-01.md`. _Review focus:_ schema fidelity to TD §5 (every column/CHECK/index), PRAGMAs and per-call connections, migration idempotence, seeds never overwrite, middleware correctness and bypasses (missing/`null` Origin, port variants, case, `Host` with extra parts), markdown `html=False`, autoescape, `requirements.txt` minimal, no unjustified layers. _Ref: TD §4.3, §5, §11, §12_
- [ ] **F1** Fix findings from `REVIEW-01.md` per 0.7. _Ref: docs/reviews/REVIEW-01.md_

---

## 2. Phase 1 — Settings
*TD §14 Phase 1 · FR-21…30*

- [ ] **T1.1** Settings page + handlers: active CLI (`claude|agy|codex`), the three command templates, system prompt, default plan duration, AI timeout (validate positive int); persist to `settings`; "reset to default" for system prompt and each command template (defaults from `defaults.py`); POST-only mutations with redirect. _Ref: TD §5.1, §9 (Settings), §14 P1; FR-25…27_
- [ ] **T1.2** Meta fields management: add (key must match `[a-z0-9_]+`, unique among **live** fields for the user; re-adding a key after soft delete must work), edit label, reorder (`sort_order`), soft delete; UI section on settings page; query helper `active_meta_fields()` ordered by `sort_order`. _Ref: TD §5 (`meta_fields`, `ux_meta_fields_key`), §8.3 (meta field soft delete), §14 P1; FR-28…29_
- [ ] **T1.3** Source upload service: accept only `.md` (extension check), UTF-8-decodable, size ≤ `UPLOAD_MAX_BYTES`; `name` and `description` required; generated file name `data/sources/<slug>-<short-id>.md` (uploaded filename never used as a path); optionally write self-describing front-matter without touching the body; insert `sources` row with path relative to `data/`. _Ref: TD §6.1, §8.4 (Upload), §11.5; FR-21…22_
- [ ] **T1.4** Source management + startup scan: list, toggle `enabled`, edit name/description, soft delete; `read_front_matter(path)` in `app/parsers.py`; startup scan of `data/sources/*.md` registers every file whose relative path is **not in `sources` at all (including soft-deleted rows)** using front-matter `name`/`description` (fallback: filename / empty description + log warning). Soft-deleted sources must never re-register. _Ref: TD §7.3 (front-matter helpers), §8.4, §5 (`sources.file_path UNIQUE`); FR-23…24_
- [ ] **T1.5** Tests for Phase 1: settings seed not overwritten after change; reset-to-default; meta key validation/uniqueness/re-add after delete; upload rejects non-`.md`, non-UTF-8, oversize, missing name/description; generated filename ≠ uploaded name; scan registers dropped file, ignores already-known and soft-deleted paths. _Ref: TD §13, §14 P1 "Done when"_
- [ ] **T1.G** Phase 1 gate — verify:
  - [ ] All settings persist across restarts
  - [ ] Duplicate live meta key rejected; re-adding after soft delete works
  - [ ] Non-`.md` upload rejected; uploaded source appears in list and on disk under `data/sources/`
  - [ ] File dropped into `data/sources/` is registered on next start; after soft delete it is **not** re-registered on the following start

- [ ] **R2** **Code review — Phase 1 settings/meta fields/sources.** Scope: T1.1–T1.G + `[F1]` commits. BASE = commit tagged `[R1]`. Report: `docs/reviews/REVIEW-02.md`. _Review focus:_ upload handling (extension, UTF-8, size, generated path, traversal, name collisions), scan semantics vs `UNIQUE(file_path)`, slug validation + partial unique index behaviour, validation of settings input, every read filters `deleted_at`, POST-only mutations, template escaping. _Ref: TD §6.1, §8.4, §11.5_
- [ ] **F2** Fix findings from `REVIEW-02.md` per 0.7. _Ref: docs/reviews/REVIEW-02.md_

---

## 3. Phase 2 — Clients
*TD §14 Phase 2 · FR-1…4*

- [ ] **T2.1** Client CRUD: list page, create (name), view page, edit name; client page layout with placeholder sections for chats and plans (filled in later phases); all queries scoped by `current_user_id()` and `deleted_at IS NULL`. _Ref: TD §5 (`clients`), §9 (Clients), §14 P2; FR-1…3_
- [ ] **T2.2** Client meta form: generated from active meta fields; **merge-save** into `clients.meta_json` (submitted keys only; preserve unknown keys and values of soft-deleted fields; empty value removes the key); JSON written with `ensure_ascii=False`. _Ref: TD §5 (`meta_json`), §8.3 (meta field soft delete), §14 P2; FR-2_
- [ ] **T2.3** Soft-delete services in `app/services/`: `delete_client` (one transaction, same timestamp on the client, all its chats, all its plans; messages untouched) and `delete_chat` (chat + its plans, same timestamp; log reasoning in `DECISIONS.md` if you deviate); wire `POST /clients/{id}/delete`; unit tests (no rows/files physically removed; hidden everywhere afterwards). _Ref: TD §8.3, §16.2, §13 (cascade test); FR-4, 9, 20, 22, 29_
- [ ] **T2.G** Phase 2 gate — verify:
  - [ ] Client created, meta edited and persisted; clearing a field removes the key; values of a soft-deleted meta field survive a form save
  - [ ] Deleting a client hides it everywhere and sets `deleted_at` on its (test-inserted) chats and plans; no rows or files physically removed

---

## 4. Phase 3 — AI Core (no chat UI yet)
*TD §14 Phase 3 · Req §8.2, §9*

- [ ] **T3.1** `app/parsers.py`: `split_blocks(text) -> (visible_text, meta_dicts, plan_md, errors)` (non-greedy `DOTALL` regex; multiple `<meta>` merged with later wins; multiple `<plan>` → last wins; invalid JSON / non-object / unclosed tag → block not applied, error recorded, **raw text left visible**) and `filter_meta(proposal, defined_keys, current_meta) -> {key: {"new","old"}}` (only defined live keys; values coerced to stripped strings; empty dropped; equal-to-current dropped). Unit tests for all malformed and filtering cases. _Ref: TD §7.3, §8.1, §13; FR-11…13_
- [ ] **T3.2** `app/prompt_builder.py`: `build_prompt(conn, chat_id) -> str` with sections in the exact order of TD §7.2 (system prompt + default duration → **code-owned output protocol** → current client + meta → current plan path/status (if any) → enabled sources (skip + log warning if file missing) → approved examples as title + labeled meta + path, **no client name**, capped by `EXAMPLES_CAP`, most recent first → history + new message). History: exclude `is_error`, cap by `HISTORY_MAX_MESSAGES`/`HISTORY_MAX_CHARS` dropping oldest. Include the "open only listed files / never write files / corrections apply to this chat only" instructions. Unit tests: section order, caps, error messages excluded, disabled/deleted sources excluded, no client name in examples. _Ref: TD §7.2, §6.2, §13; FR-10_
- [ ] **T3.3** `app/ai_runner.py`: `run_ai(prompt) -> str` + `AIRunError`. Read `active_cli` + template from settings; `shlex.split` (Windows-safe), **never `shell=True`**; `{prompt}` substitution in argv if present, else prompt on **stdin** as UTF-8; resolve executable via `shutil.which` (`AIRunError("CLI '<name>' not found in PATH")`); `cwd=DATA_DIR`; capture bytes, decode `errors="replace"`, strip ANSI, strip whitespace; enforce `ai_timeout_seconds` and kill the **whole process tree** (new session/process group on POSIX; `taskkill /T /F` on Windows); non-zero exit or empty stdout → `AIRunError`; log CLI name, duration, exit code, stderr tail (**not** the prompt). _Ref: TD §7.1, §11.3, §12_
- [ ] **T3.4** `tests/fake_cli.py` (reads prompt from stdin; modes via env/arg: plain text, text+`<meta>`, text+`<plan>`, malformed blocks, non-zero exit, sleep-for-timeout, spawns a child to test tree kill) and `ai_runner` tests: stdin vs `{prompt}` delivery, timeout (and no orphan child), non-zero exit, empty output, missing executable, Persian text round-trip. _Ref: TD §13, §7.1_
- [ ] **T3.5** Default command templates in `defaults.py` for `claude`, `agy`, `codex`: look up each tool's **current official docs**; requirements: non-interactive one-shot, plain-text stdout, **read-only** tool permissions, no approval prompts, prompt via stdin where supported. Record doc sources/versions in `docs/DECISIONS.md`. If docs/CLI are unreachable, use best-known flags, mark them `UNVERIFIED` in `DECISIONS.md`, and continue. _Ref: TD §7.1 (Default templates), §14 P3; Req §9_
- [ ] **T3.6** "Test CLI" button on the settings page (or a tiny dev script): sends a trivial prompt via `run_ai` with the active CLI and shows output/error (no stack traces in UI). _Ref: TD §14 P3 (last task), §12_
- [ ] **T3.G** Phase 3 gate — verify:
  - [ ] Parser, prompt-builder and runner unit tests pass using the fake CLI (including timeout and non-zero exit)
  - [ ] Each real CLI that is installed answers a trivial prompt through `run_ai` with its default template without hanging for approval (mark "not installed" for the others — see Section 9 notes)

- [ ] **R3** **Code review — clients + parsers + prompt builder.** Scope: T2.1–T3.2 + `[F2]` commits. BASE = commit tagged `[R2]`. Report: `docs/reviews/REVIEW-03.md`. _Review focus:_ merge-save semantics (unknown/deleted keys preserved), cascade atomicity and identical timestamp, regex robustness (nested/unclosed/multiple blocks, huge input), "raw text stays visible" on any parse error, `filter_meta` edge cases (non-string values, whitespace, deleted keys), prompt section order and code-owned protocol, history cap correctness, no client name leak, test coverage of every case in TD §13. _Ref: TD §7.2, §7.3, §8.1, §8.3_
- [ ] **F3** Fix findings from `REVIEW-03.md` per 0.7. _Ref: docs/reviews/REVIEW-03.md_

---

## 5. Phase 4 — Chat
*TD §14 Phase 4 · FR-5…10*

- [ ] **T4.1** Turn orchestration in `app/services/` (keep thin): in-memory `set[int]` of running chat ids + `threading.Lock` (atomic check-and-add); `process_chat_turn(chat_id)` works **only from DB state**: build prompt → `run_ai` → store assistant message (blocks not yet parsed; Phase 5/6 hook points left as simple calls to be added); any failure (missing CLI, non-zero, timeout, empty) → assistant message `is_error=1` with short Persian text, full details to `app.log`; `finally` always clears running flag; own DB connection per thread. Unit tests with fake CLI (success, each failure kind, error excluded from later prompts, flag cleared). _Ref: TD §4.1, §4.2, §4.3, §12, §13_
- [ ] **T4.2** New-chat flow + chat list: `GET /chats/new` with two explicit radio options (existing client **or** new client name), `POST /chats` creates client if needed then chat, redirect to chat; `GET /` redirects to last chat or new-chat page; sidebar listing (title, client name, date). _Ref: TD §8.6, §9 (Chats), §10; FR-5…6_
- [ ] **T4.3** Chat page + messaging: layout (sidebar, header with client name, conversation, input, **empty plan panel container** ready for oob refresh); `POST /chats/{id}/messages` (reject if running → inserts user message → auto title from first ~40 chars on first message → mark running → start background thread → return fragment with user bubble + polling placeholder `hx-trigger="load delay:2s"`); `GET /chats/{id}/poll` (placeholder while running; assistant fragment + `hx-swap-oob` plan panel/input re-enable when done); page render checks running set so a reload shows the placeholder; input disabled while processing; assistant text rendered as markdown; `dir="auto"` on bubbles; Enter/Shift+Enter and auto-scroll with minimal vanilla JS. _Ref: TD §4.1, §8.5, §10; FR-7…9_
- [ ] **T4.4** Retry and chat delete: Retry button on the **last error message** → `POST /chats/{id}/retry` re-runs `process_chat_turn` without inserting a user message (old error message removed or marked — note choice in `DECISIONS.md`); `POST /chats/{id}/delete` uses `delete_chat` from T2.3; fill the client page's chats section. _Ref: TD §4.2, §8.3, §9; FR-9_
- [ ] **T4.5** Integration tests with fake CLI via `TestClient`: send → poll → assistant message persisted; second send while running rejected; failure → error message → retry works; error never appears in later prompts; title set once; chat delete hides chat and its plans. _Ref: TD §13, §14 P4 "Done when"_
- [ ] **T4.G** Phase 4 gate — verify (fake CLI, then one real CLI if available):
  - [ ] Chat with new or existing client shows client name in header; messages and replies persist across reload
  - [ ] Second send while a turn runs is rejected/disabled
  - [ ] Forced failures (missing CLI, timeout, non-zero exit) show an error message; Retry works; error messages never appear in later prompts
  - [ ] Restarting the server mid-turn leaves a recoverable state (Retry available)

---

## 6. Phase 5 — Meta Extraction
*TD §14 Phase 5 · FR-11…14*

- [ ] **T5.1** Hook parsing into `process_chat_turn`: call `split_blocks`; store `visible_text` as assistant `content` (on parse errors store raw text and log the error); compute `filter_meta(...)` against defined live keys and the client's current meta; if non-empty store `messages.meta_proposal` JSON (`ensure_ascii=False`) and `meta_status='pending'`. Nothing touches `clients.meta_json`. _Ref: TD §7.3, §8.1 (After a turn), §4.1; FR-11…12_
- [ ] **T5.2** Meta card partial + endpoints: card under the assistant message while `pending` (one row per key: label, editable input prefilled with proposed value, old value shown when it exists and differs); `POST /messages/{id}/meta` merges only submitted non-empty keys into `clients.meta_json` and sets `saved`; `POST /messages/{id}/meta/dismiss` sets `dismissed`; HTMX swap; `saved`/`dismissed` render as a small read-only note; state survives reload. _Ref: TD §8.1, §9 (Meta card), §10; FR-13…14_
- [ ] **T5.3** Tests: reply with defined + undefined keys → card has only defined keys; equal-to-current values omitted; `meta_json` unchanged until Save; edited values are what get saved; Dismiss saves nothing; malformed `<meta>` leaves raw text visible and logs error; double Save is harmless. _Ref: TD §13, §14 P5 "Done when"_
- [ ] **T5.G** Phase 5 gate — verify:
  - [ ] `<meta>` with defined + undefined keys shows a card with **only** defined keys; values equal to current are omitted
  - [ ] Nothing changes in `clients.meta_json` until Save; edited values are saved; Dismiss saves nothing
  - [ ] Card state survives reload; malformed `<meta>` leaves raw text visible and logs an error

- [ ] **R4** **Code review — AI runner + turn orchestration.** Scope: T3.3–T4.1 + `[F3]` commits that touch these files. BASE = commit tagged `[R3]`, then **limit the diff** to: `git diff $BASE..HEAD -- app/ai_runner.py app/defaults.py app/services/ tests/fake_cli.py tests/ app/routes/settings.py`. Report: `docs/reviews/REVIEW-04.md`. _Review focus:_ no `shell=True`, argv built safely, stdin vs `{prompt}` correctness, `which` resolution, timeout kills the full tree on POSIX **and** Windows paths, ANSI stripping, decoding with `errors="replace"`, prompt never logged, default templates actually read-only and non-interactive, thread safety (running-set check-and-add atomic, flag cleared in `finally`, DB connection per thread, no shared connections), error-message content (no stack traces, no secrets). _Ref: TD §4, §7.1, §11.3, §12_
- [ ] **F4** Fix findings from `REVIEW-04.md` per 0.7. _Ref: docs/reviews/REVIEW-04.md_

- [ ] **R5** **Code review — chat UI + meta extraction.** Scope: T4.2–T5.G + `[F4]` commits. BASE = commit tagged `[R4]` (**do not** re-review the T3.3–T4.1 files already covered by R4 unless changed since). Report: `docs/reviews/REVIEW-05.md`. _Review focus:_ send/poll races (double-click, two tabs, poll after finish), reload-during-turn placeholder, `hx-swap-oob` correctness, retry semantics (no duplicate user message), title logic, chat delete cascade wiring, meta card flow (nothing written before Save, only submitted keys merged, empty = skip, XSS in values/labels, state persistence), hook into turn (raw text visible on parse errors), POST-only mutations, template escaping and `dir="auto"`. _Ref: TD §4.1, §4.2, §8.1, §8.5, §10_
- [ ] **F5** Fix findings from `REVIEW-05.md` per 0.7. _Ref: docs/reviews/REVIEW-05.md_

---

## 7. Phase 6 — Plans
*TD §14 Phase 6 · FR-15…20*

- [ ] **T6.1** Plan file writer in `app/parsers.py`: `write_plan_file(...)` generating the **entire file** (YAML front-matter via `yaml.safe_dump(..., allow_unicode=True, sort_keys=False)` with `client_id, client_name, plan_id, version, status, title, meta (block mapping snapshot, string values), approved_at` + `# title` + AI body exactly as returned); atomic write (temp file + `os.replace`); path built from **integer ids only**: `data/plans/<client_id>/plan-<plan_id>-v<version>.md`; title = first `# H1` of the body else `"<client name> — v<version>"`; never delete files. Unit tests incl. Persian text and colons in values. _Ref: TD §6.2, §7.3, §11.5_
- [ ] **T6.2** `save_plan_from_ai(chat, body_md)` in one DB transaction (read-then-write): latest non-deleted plan of chat is `draft` → overwrite its file + update title; otherwise `version = 1 + MAX(version)` over **all** plans of the chat **including soft-deleted** (0 if none) → insert `draft` row, compute path from new id, write file; if file write fails → roll back DB and treat the turn as failed (error message, retry available). Hook into `process_chat_turn` (when `<plan>` parsed): set `messages.plan_id`; render chip "برنامه پیش‌نویس به‌روز شد — v<N>" under the message. _Ref: TD §8.2, §5 (`plans`, `messages.plan_id`), §10; FR-15…16, FR-18_
- [ ] **T6.3** Approval + plan panel: `approve(plan_id)` — only `draft → approved`, idempotent for already-approved; re-render file with `status: approved`, `approved_at` (date) and **frozen meta snapshot** — write file first, then commit DB row; approved plans never modified afterwards; `POST /plans/{id}/approve` (HTMX); plan panel partial in the chat page (latest non-deleted plan: version, status badge, rendered markdown, Approve button when draft) refreshed via oob from the poll response; a new `<plan>` after approval creates the next version as draft. _Ref: TD §8.2 (`approve`), §6.2, §10; FR-17, FR-19_
- [ ] **T6.4** Plan soft delete + client-page plan list: `POST /plans/{id}/delete` (soft delete only; file stays; removes it from examples); `GET /plans/{id}` rendered view; client page lists plans of **all chats grouped by chat**, each with version and status, all versions viewable. _Ref: TD §8.2 (Other rules), §8.3, §9 (Plans), §16.1; FR-19…20_
- [ ] **T6.5** Verify prompt-builder items 4 and 6 against real data: current plan path/status of this chat with the "read this file to revise; ignore front-matter" note; approved examples = all non-deleted `approved` plans (also from other clients, newest first, capped at `EXAMPLES_CAP`), drafts and soft-deleted excluded, **no client name**, a sentence stating that unlisted files under `plans/` are not examples. Fix gaps found in `prompt_builder.py` and extend its tests. _Ref: TD §7.2 (items 4, 6), §16.3–16.4_
- [ ] **T6.6** Plan lifecycle tests: first `<plan>` creates draft file at the expected path; second `<plan>` overwrites the same file (no new file); approve freezes status + meta snapshot and file is not rewritten afterwards; approval idempotent (double call); next `<plan>` after approval → v2 draft; version numbering correct after a soft-deleted version; DB-failure/file-failure rollback; atomic write leaves no partial file. _Ref: TD §13 (plan lifecycle), §14 P6 "Done when"_
- [ ] **T6.G** Phase 6 gate — verify:
  - [ ] First `<plan>` creates draft `data/plans/<client_id>/plan-<id>-v1.md` and shows in panel; second `<plan>` in same chat overwrites the same draft (no new file)
  - [ ] Approve → front-matter `status: approved` + frozen meta; file no longer modified
  - [ ] Next `<plan>` after approval creates v2 as draft; version numbering correct after a soft-deleted version
  - [ ] Approved plans appear in example lists in later prompts (also in other clients' chats); drafts and deleted plans do not

- [ ] **R6** **Code review — plan lifecycle.** Scope: T6.1–T6.G + `[F5]` commits. BASE = commit tagged `[R5]`. Report: `docs/reviews/REVIEW-06.md`. _Review focus:_ transaction boundaries and rollback on file-write failure, version numbering incl. soft-deleted, overwrite-only-if-draft rule, approve ordering (file first, then DB) and idempotence/double-click, frozen snapshot really frozen, atomic writes (`os.replace`, temp file cleanup), paths from integers only (no user input), "DB wins over front-matter", examples query (approved + non-deleted only, no name leak, cap, order), soft-delete filters on every plan query, panel/oob rendering, YAML correctness for Persian/colon values. _Ref: TD §6.2, §8.2, §7.2_
- [ ] **F6** Fix findings from `REVIEW-06.md` per 0.7. _Ref: docs/reviews/REVIEW-06.md_

---

## 8. Phase 7 — Hardening & Acceptance
*TD §14 Phase 7 · Req §13*

- [ ] **T7.1** Edge cases (fix what breaks, add tests where automatable): Persian text through stdin on the host OS; very long history (cap works, newest kept); source file missing on disk (skipped + warning, turn still works); large plan body; double-click on Approve; two browser tabs on the same chat; process-tree kill on timeout (no orphans); poll after server restart. Record results in `docs/ACCEPTANCE.md`. _Ref: TD §14 P7 (Edge cases), §4.1, §7.1_
- [ ] **T7.2** Acceptance run: execute Req §13 items 1–8 **per CLI** (`claude`, `agy`, `codex`), fixing per-CLI output quirks (banners/noise → template flag or small per-CLI cleanup). Record a result table in `docs/ACCEPTANCE.md` (item × CLI: pass / fail / not-installed). Items that need an unavailable CLI are marked `not-installed` and listed for the human to run; do **not** mark them passed. Criterion 8: switching only `active_cli` moves execution to another tool. _Ref: TD §14 P7, §15 (Req §13 mapping), §7.1_
- [ ] **T7.3** Docs: `README.md` (install `pip install -r requirements.txt && python run.py`, configure CLIs, data layout, backup = copy `data/`, security note about editable command templates) and final pass on `docs/DECISIONS.md` (every deviation, doc sources/versions from T3.5). _Ref: TD §0, §14 P7, §11, §16_
- [ ] **T7.G** Phase 7 gate — verify:
  - [ ] Acceptance table complete; every `pass` was actually run
  - [ ] README lets a fresh checkout run with `pip install -r requirements.txt && python run.py` (test in a fresh venv)

- [ ] **R7** **Code review — hardening & final delta.** Scope: T7.1–T7.G + `[F6]` commits. BASE = commit tagged `[R6]`. Report: `docs/reviews/REVIEW-07.md`. _Review focus:_ correctness of edge-case fixes, per-CLI cleanup code, README/DECISIONS accuracy vs actual behavior, dead code or leftover TODOs, unjustified abstractions added late, anything contradicting a **Fixed** item in TD. _Ref: TD §0, §1, §14 P7_
- [ ] **F7** Fix findings from `REVIEW-07.md` per 0.7. _Ref: docs/reviews/REVIEW-07.md_

---

## 9. Closing

- [ ] **FINAL-FIX** Resolve every remaining open finding (`deferred`, Medium, Low) across `REVIEW-01…07`: fix it, or mark `wontfix` in the report with a one-line justification. Update the Review log. Commit tag `[FINAL-FIX]`. _Ref: docs/reviews/*_
- [ ] **FINAL-VERIFY** Final verification (do not tick until **all** sub-items pass):
  - [ ] `pytest -q` fully green
  - [ ] Fresh venv: `pip install -r requirements.txt && python run.py` works; `requirements.txt` contains only used packages
  - [ ] `grep -rn "shell=True" app/` → no hits
  - [ ] `grep -rnE "DELETE FROM|os\.remove|unlink\(|rmtree" app/` → no hits (soft delete only)
  - [ ] Every `SELECT` on `clients/chats/plans/meta_fields/sources` filters `deleted_at IS NULL` (via helper/view or explicitly)
  - [ ] No CDN/external URLs in templates (`grep -rnE "https?://" app/templates app/static --include=*.html --include=*.css`)
  - [ ] Req §13 acceptance items 1–8 documented in `docs/ACCEPTANCE.md`
  - [ ] No unchecked findings left in `docs/reviews/` except `wontfix` with justification
  - [ ] Every task above is `[x]` (or `[!]` with a `DECISIONS.md` entry)

### Review log (update after each R/F task)

| Review | Scope | Report | Critical | High | Medium | Low | Open after fixes |
|---|---|---|---|---|---|---|---|
| R1 | T0.1–T0.G | `docs/reviews/REVIEW-01.md` | – | – | – | – | – |
| R2 | T1.1–T1.G | `docs/reviews/REVIEW-02.md` | – | – | – | – | – |
| R3 | T2.1–T3.2 | `docs/reviews/REVIEW-03.md` | – | – | – | – | – |
| R4 | T3.3–T4.1 | `docs/reviews/REVIEW-04.md` | – | – | – | – | – |
| R5 | T4.2–T5.G | `docs/reviews/REVIEW-05.md` | – | – | – | – | – |
| R6 | T6.1–T6.G | `docs/reviews/REVIEW-06.md` | – | – | – | – | – |
| R7 | T7.1–T7.G | `docs/reviews/REVIEW-07.md` | – | – | – | – | – |

### Notes / blockers log
_(Add dated one-liners here for anything a human must do, e.g. "codex CLI not installed — run acceptance item 3 manually".)_

---

## Appendix A — Review report template (`docs/reviews/REVIEW-0<n>.md`)

````markdown
# REVIEW-0<n> — <short scope name>

- **Review task:** R<n>
- **Tasks covered:** T… – T… (+ F<n-1> fixes)
- **Diff range:** `<BASE sha>..<HEAD sha>`
- **Files changed / lines changed:** <N files, +X −Y (excluding tests/vendored)>
- **Test run:** `pytest -q` → <passed/failed counts>
- **Verdict:** <Approved | Approved with fixes | Needs rework>

## Summary
<3–6 lines: overall quality, main risks.>

## Findings

### R<n>-01 — <title>
- **Severity:** Critical | High | Medium | Low
- **Category:** correctness | security | concurrency | data-integrity | design-conformance | error-handling | testing | maintainability | style
- **Location:** `path/to/file.py:LINE` (+ TD § reference if it violates the design)
- **Description:** <what is wrong and why it matters>
- **Suggested fix:** <concrete change>
- **Status:** [ ] open  <!-- tick when fixed; or write: deferred / wontfix + reason -->
- **Resolution:** <one line, filled by the F<n> task>

(repeat per finding)

## Positive notes (optional)
<what was done well, to keep as pattern>
````

**Severity scale (applies to every finding):**

| Level | Definition | Examples | Handling |
|---|---|---|---|
| **Critical** | Security hole, data loss/corruption, or a core flow is broken; violates a Fixed contract in a way that causes wrong behavior | Origin/Host check bypassable; subprocess with `shell=True`; physical delete; plan overwrite of an approved file; AI output saved without trainer action | Must fix in `F<n>` immediately; add regression test |
| **High** | Feature does not meet its FR / "Done when"; race condition; soft-delete leak; error path that hangs or loses messages | Running-guard not atomic; missing `deleted_at` filter; version numbering ignores soft-deleted; error messages leak into prompts | Must fix in `F<n>`; add regression test |
| **Medium** | Edge-case bug, missing required test, fragile code likely to cause future bugs | Missing test from TD §13 list; unhandled empty value; poor error text | Fix in `F<n>` if cheap, else `FINAL-FIX` |
| **Low** | Style, naming, minor cleanup, small doc gaps | Dead code, inconsistent naming, comment typos | `FINAL-FIX` or `wontfix` |

## Appendix B — Generic review checklist (use in every `R<n>`, skip what is out of scope)

- **Design conformance:** every **Fixed** item touched is implemented as written (schema, settings keys, paths, signatures, section order in the prompt); deviations are in `docs/DECISIONS.md`.
- **Simplicity:** no repositories/DI/ORM/job queues or other layers the TD does not justify (TD §1, §3).
- **Soft delete:** all reads filter `deleted_at IS NULL`; no physical deletes of rows or files.
- **AI never writes:** nothing from AI output is persisted without trainer action, except the plan draft; meta needs explicit Save.
- **Security (TD §11):** Host/Origin guard, no shell, markdown `html=False`, Jinja autoescape (no `|safe` on untrusted data), generated file names, paths from integers.
- **Concurrency:** one DB connection per thread/request; atomic running-guard; flags cleared in `finally`.
- **Error handling:** failures produce `is_error` messages with short text, details only in `app.log`; no stack traces in UI; prompts never logged by default.
- **Encoding:** UTF-8 everywhere; `ensure_ascii=False`; Persian text survives stdin, files, YAML, JSON.
- **Tests:** each unit-test area required by TD §13 for the covered tasks exists and asserts behavior (not just "runs").
- **Hygiene:** no dead code, no leftover `TODO`/debug prints, no committed `data/` files, `requirements.txt` minimal.
