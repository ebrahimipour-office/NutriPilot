# NutriPilot — Technical Design (v1)

Audience: an AI coding agent that will implement NutriPilot v1 from this document and the requirements doc (referenced as `FR-n` / "Req §n").
Scope: local, single-user web app. Keep it simple; do not add layers, abstractions, or services that are not justified below.

---

## 0. How to read this document

- **Fixed** = contract. Implement as written unless it is impossible; if you must deviate, note it in `docs/DECISIONS.md` (one line each).
- **Agent discretion** = you choose the implementation. The text only states the constraints that matter.
- Anything not mentioned is Agent discretion, as long as it respects the principles in §1.
- Section 14 splits the work into phases. Each phase ends with a runnable app and a verifiable "Done when" list. A separate progress file will be derived from §14, so keep the phase boundaries meaningful.

---

## 1. Principles

1. **Boring tech, few moving parts.** One process, one SQLite file, markdown files on disk, server-rendered HTML with HTMX.
2. **The app owns all writes; the AI only reads.** The AI returns text with tagged blocks; the app parses them and persists. The AI never writes files.
3. **The DB is the source of truth** for state (status, version, soft delete). Plan/source files on disk are content (and a derived copy of some state in front-matter).
4. **Nothing is saved from AI output without trainer action**, except the plan draft (which is explicitly a draft). Client meta requires explicit confirmation (FR-13).
5. **Soft delete everywhere**; never physically delete rows or files.
6. **Prompt = pointers, not content.** Sources and example plans are listed with paths; the AI opens what it needs.

---

## 2. Stack & dependencies (Fixed)

| Concern | Choice |
|---|---|
| Language | Python 3.11+ |
| Web | FastAPI + Jinja2 + HTMX (vendored in `app/static/`, no CDN) |
| Server | uvicorn, single worker, bound to `127.0.0.1:8005` |
| DB | SQLite via stdlib `sqlite3` (thin helper, no ORM) |
| Markdown render | `markdown-it-py` with raw HTML **disabled** |
| Front-matter | `PyYAML` (`safe_load` / `safe_dump(allow_unicode=True)`) |
| Uploads | `python-multipart` |
| Tests | `pytest` |

`requirements.txt` should contain only what is used. No Node build step.

Agent discretion: using SQLAlchemy/SQLModel instead of raw `sqlite3` is allowed only if it clearly reduces code; the default recommendation is raw `sqlite3` with `row_factory = sqlite3.Row`.

---

## 3. Project layout (Fixed at top level, free inside)

```
nutripilot/
  run.py                     # starts uvicorn on 127.0.0.1:8005
  requirements.txt
  README.md
  docs/DECISIONS.md          # deviations / notable choices (short)
  app/
    main.py                  # FastAPI app, lifespan (init DB, seed settings, scan sources), middleware
    config.py                # paths, constants (DATA_DIR overridable via env for tests)
    db.py                    # connection helper, schema/migrations, small query helpers
    defaults.py              # default system prompt, default CLI command templates
    routes/                  # chats.py, clients.py, plans.py, settings.py (split as you like)
    prompt_builder.py
    ai_runner.py
    parsers.py               # block extraction, front-matter read/write
    services/                # optional: plan lifecycle, chat turn orchestration (keep thin)
    templates/               # Jinja2 (base.html + pages + HTMX partials)
    static/                  # htmx.min.js, app.css
  data/                      # created at runtime; git-ignored
    app.db
    app.log
    sources/
    plans/<client_id>/plan-<plan_id>-v<version>.md
  tests/
    fake_cli.py              # fake AI CLI used by tests (see §13)
```

Module boundaries required by Req §11: `routes`, `db`, `ai_runner`, `prompt_builder`, `parsers`. A small `services/` module for the chat-turn orchestration and plan lifecycle is fine; do not introduce repositories/DI containers/etc.

---

## 4. Runtime architecture

```
Browser (HTMX) ──HTTP──> FastAPI routes ──> db.py (SQLite)
                                  │
                                  └─> chat turn (background thread)
                                        prompt_builder -> ai_runner (subprocess CLI, cwd=data/)
                                        parsers -> persist message / meta proposal / plan draft
```

### 4.1 Chat turn flow (Fixed behavior, Agent discretion on mechanics)

The AI call can take up to minutes, so the HTTP request must not depend on it.

1. `POST /chats/{id}/messages`: reject if this chat already has a turn running; insert the user message; mark chat as running; start the turn in a background thread (`threading.Thread` or `BackgroundTasks` — any works); respond immediately with an HTML fragment containing the user bubble and a "processing" placeholder that polls.
2. Placeholder polls `GET /chats/{id}/poll` (HTMX `hx-trigger="load delay:2s"`, ~2 s). While running, it returns the same placeholder. When finished, it returns the assistant message fragment and uses `hx-swap-oob` to refresh the plan panel and re-enable the input.
3. The turn function (`process_chat_turn(chat_id)`) works **only from DB state** (it reads history from `messages`), so it can be re-run for retry without inserting a new user message.
4. In a `finally`, always clear the "running" flag.

Running-state: an in-memory `set[int]` of chat ids guarded by a `threading.Lock` is enough (single process). On server restart a half-finished turn is simply lost; the trainer sees the last user message with no answer and can press Retry. No job table.

Reloading the page while a turn is running must show the processing placeholder (check the in-memory set when rendering the chat page).

### 4.2 Retry and errors

- On any failure (CLI missing, non-zero exit, timeout, empty output) store an assistant message with `is_error = 1` and a short human-readable text (Persian is fine). Error messages are **excluded** from the history that goes into later prompts.
- Show a **Retry** button on the last error message: it re-runs `process_chat_turn` for that chat (and may mark/remove the old error message — Agent discretion).
- Full detail (stderr, exit code, duration, command name without the prompt) goes to `data/app.log`.

### 4.3 DB access and threads

SQLite connections are opened per request / per background job via a helper (`with db.connect() as conn:`). Enable `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`, and a `busy_timeout` (~5 s). Do not share a connection across threads.

---

## 5. Data model (Fixed; extends Req §7)

Timestamps are UTC ISO-8601 strings (`TEXT`). Booleans are `INTEGER 0/1`. All text is UTF-8; JSON is written with `ensure_ascii=False`.

```sql
CREATE TABLE users (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL
);                                                   -- seed: id=1 "admin"

CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE meta_fields (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
  key TEXT NOT NULL,              -- machine key the AI uses, slug: [a-z0-9_]+
  label TEXT NOT NULL,            -- Persian display label
  sort_order INTEGER NOT NULL DEFAULT 0,
  deleted_at TEXT
);
CREATE UNIQUE INDEX ux_meta_fields_key ON meta_fields(user_id, key) WHERE deleted_at IS NULL;

CREATE TABLE clients (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
  name TEXT NOT NULL,
  meta_json TEXT NOT NULL DEFAULT '{}',   -- {"key": "value", ...}
  created_at TEXT NOT NULL, deleted_at TEXT
);

CREATE TABLE chats (
  id INTEGER PRIMARY KEY,
  client_id INTEGER NOT NULL REFERENCES clients(id),
  title TEXT NOT NULL,
  created_at TEXT NOT NULL, deleted_at TEXT
);

CREATE TABLE plans (
  id INTEGER PRIMARY KEY,
  client_id INTEGER NOT NULL REFERENCES clients(id),
  chat_id INTEGER NOT NULL REFERENCES chats(id),
  version INTEGER NOT NULL,
  title TEXT NOT NULL,
  file_path TEXT NOT NULL,                 -- relative to data/
  status TEXT NOT NULL CHECK (status IN ('draft','approved')),
  approved_at TEXT,
  created_at TEXT NOT NULL, deleted_at TEXT
);

CREATE TABLE messages (
  id INTEGER PRIMARY KEY,
  chat_id INTEGER NOT NULL REFERENCES chats(id),
  role TEXT NOT NULL CHECK (role IN ('user','assistant')),
  content TEXT NOT NULL,                   -- user: as typed. assistant: visible text with <meta>/<plan> blocks removed
  is_error INTEGER NOT NULL DEFAULT 0,
  meta_proposal TEXT,                      -- JSON of the filtered proposal (assistant only), NULL if none
  meta_status TEXT CHECK (meta_status IN ('pending','saved','dismissed')),
  plan_id INTEGER REFERENCES plans(id),    -- plan created/updated by this message, if any
  created_at TEXT NOT NULL
);

CREATE TABLE sources (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
  name TEXT NOT NULL, description TEXT NOT NULL,
  file_path TEXT NOT NULL UNIQUE,          -- relative to data/; UNIQUE includes soft-deleted rows on purpose (see §8.4)
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, deleted_at TEXT
);

CREATE INDEX ix_chats_client ON chats(client_id);
CREATE INDEX ix_messages_chat ON messages(chat_id, id);
CREATE INDEX ix_plans_chat ON plans(chat_id, version);
CREATE INDEX ix_plans_client ON plans(client_id);
```

Notes:
- **Differences from the requirements doc** (all additive): `user_id` on `meta_fields`/`sources` (so future multi-user is just a filter), and extra columns on `messages` (`is_error`, `meta_proposal`, `meta_status`, `plan_id`) so cards and chips survive page reloads without extra tables.
- `settings` stays global in v1. `chats`/`messages`/`plans` are scoped to a user through `clients.user_id`.
- Provide `current_user_id()` returning `1` and filter top-level queries (clients, meta_fields, sources) by it. Nothing more for auth in v1.
- Migrations: `PRAGMA user_version` + an ordered list of SQL scripts is enough. v1 = the schema above. Agent discretion on the helper.
- **Soft-delete convention:** every read query must filter `deleted_at IS NULL`. Put the filter in the shared query helpers or SQL views so it is hard to forget.

### 5.1 Settings keys (Fixed names, seeded on first start with `INSERT OR IGNORE`; never overwrite existing values)

| Key | Meaning | Default |
|---|---|---|
| `active_cli` | `claude` \| `agy` \| `codex` | `claude` |
| `cmd_claude`, `cmd_agy`, `cmd_codex` | command templates (§7.1) | from `defaults.py` |
| `system_prompt` | trainer-editable AI guidance | from `defaults.py` (Appendix A) |
| `default_plan_duration` | free text, e.g. "یک هفته" | `یک هفته` |
| `ai_timeout_seconds` | CLI timeout | `180` |

Offer a "reset to default" button for `system_prompt` and command templates (defaults live in code, so this is cheap and useful).

---

## 6. Files on disk

### 6.1 Sources

Stored at `data/sources/<slug>-<short-id>.md` (the uploaded filename is **never** used as a path; generate the name). `file_path` in DB is relative to `data/`.

DB `name`/`description`/`enabled` are the source of truth for the prompt. Front-matter in a source file (`name`, `description`) is only read when auto-registering files dropped into `data/sources/` (§8.4); you may also write it on upload so the file is self-describing — Agent discretion. Do not rewrite the source body.

### 6.2 Plans

Path: `data/plans/<client_id>/plan-<plan_id>-v<version>.md` (relative to `data/` in DB). The app **generates the whole file**:

```markdown
---
client_id: 3
client_name: Sara
plan_id: 12
version: 1
status: draft            # draft | approved
title: ...
meta:
  height_cm: "165"
  weight_kg: "70"
approved_at:             # ISO date, only when approved
---
# <title>
...plan body exactly as returned by the AI inside <plan>...
```

- Written with `yaml.safe_dump(..., allow_unicode=True, sort_keys=False)`. This deviates cosmetically from the flow-style `meta: { k: v }` in Req §8.1 because Persian text and colons in values break hand-built flow mappings. Content-wise it is equivalent.
- `meta` is a **snapshot** of the client's meta at write time (machine keys, string values). Refreshed on every draft rewrite; frozen at approval.
- Write atomically (temp file + `os.replace`). Never delete files from disk.
- The file is derived from DB + AI body; if front-matter and DB ever disagree, DB wins.
- Title: first `# H1` line of the body if present, otherwise `"<client name> — v<version>"`.

---

## 7. AI integration

### 7.1 `ai_runner.run_ai(prompt) -> str` (Fixed signature; raises `AIRunError(message)`)

Behavior:
1. Read `active_cli` and its template from settings.
2. Split the template with `shlex.split` (use `posix=False`-safe handling on Windows if the app runs there). **Never `shell=True`.**
3. **Prompt delivery:** if any argv token contains `{prompt}`, substitute it there; otherwise write the prompt to the process **stdin** (UTF-8 bytes). Prefer stdin in default templates: prompts can be tens of KB and OS argv limits (notably Windows) will break long prompts.
4. Resolve the executable with `shutil.which`; if not found raise `AIRunError("CLI '<name>' not found in PATH")`. (On Windows this also resolves `.cmd` shims from npm installs.)
5. Run with `cwd=DATA_DIR`, capture stdout/stderr as bytes, decode UTF-8 with `errors="replace"`, strip ANSI escape codes, strip surrounding whitespace.
6. Enforce `ai_timeout_seconds`. On timeout kill the **process tree** (CLIs often spawn children): new session/process group on POSIX; `taskkill /T /F` or `CREATE_NEW_PROCESS_GROUP` on Windows. No orphans.
7. Non-zero exit or empty stdout → `AIRunError` with a concise message (include the last lines of stderr in the log, not necessarily in the UI).

**Default templates** (`defaults.py`): the exact flags of `claude`, `agy` and `codex` must be taken from each tool's current official documentation at implementation time (Req §9). Requirements for the defaults:
- non-interactive / one-shot mode,
- plain-text output (no TUI, no progress UI on stdout),
- tool permissions restricted to **reading** files (read-only sandbox / allowed-tools list limited to read/search tools), no approval prompts that could hang the process,
- prompt via stdin when the CLI supports it.

Illustrative shape only — verify before use:
```
claude -p --allowedTools "Read,Glob,Grep"
codex exec --sandbox read-only -
agy ...   # check docs
```

Agent discretion: if a CLI prints banners/extra noise on stdout that breaks block parsing, add a flag in its template or a small per-CLI cleanup step. Test each CLI against the acceptance checklist (§14, Phase 7).

### 7.2 `prompt_builder.build_prompt(conn, chat_id) -> str`

Sections in this order (Req §9). Plain text/markdown with clear headers; keep it readable for the model.

1. **System prompt** (from settings) + default plan duration.
2. **Output protocol** — *owned by code, not by the editable system prompt*, so editing the system prompt can never break parsing. Defines:
   - defined meta fields (`key` — `label`),
   - when/how to emit `<meta>{"key":"value"}</meta>` (only defined keys; only values stated in the conversation; only if new or different from current meta),
   - when/how to emit `<plan>…</plan>` (**the full plan every time**, never a diff; markdown; first line `# Title`; no front-matter — the app adds it),
   - blocks go at the very end of the reply, outside the conversational text; the conversational text must still make sense without them.
3. **Current client**: name + current meta (label: value).
4. **Current plan draft/approved file** of this chat, if any: relative path + status, with the note "read this file to revise the plan; ignore its front-matter".
5. **Enabled sources**: name, description, relative path (skip + log if the file is missing).
6. **Approved example plans**: title, client meta (labels + values, **no client name**), relative path. Only approved, non-deleted plans. Soft cap of the most recent N (suggest 50, constant in `config.py`). Tell the AI that files under `plans/` that are not listed are not examples.
7. **Conversation history** + the new trainer message.

History rules:
- Exclude `is_error` messages.
- Replace nothing in user messages. Assistant messages are already stored without blocks (§5), so plan text is not repeated each turn.
- Cap history by count/characters (suggest last 30 messages or ~24k chars, whichever is smaller, dropping oldest). Constants in `config.py`.

Instructions the prompt must convey (partly via the system prompt, partly code-owned):
- Open only the listed files that are relevant; do not browse elsewhere in the working directory.
- Do not write, modify, or create files.
- Trainer corrections apply to this chat only; do not treat them as general rules (FR-10). This is satisfied by construction — only this chat's history is sent — plus one sentence in the prompt.

### 7.3 `parsers`

Pure functions, unit-tested:

- `split_blocks(text) -> (visible_text, meta_dicts: list[dict], plan_md: str | None, errors: list[str])`
  - `<meta>…</meta>` and `<plan>…</plan>` found with non-greedy, `DOTALL` regex.
  - Multiple `<meta>` blocks: merge, later wins. Multiple `<plan>` blocks: use the last.
  - Invalid JSON, non-object JSON, unclosed tag → no block applied, error recorded; in that case **leave the raw text visible** (Req §8.2) and log the error. A broken `<plan>` must never silently disappear.
- `filter_meta(proposal, defined_keys, current_meta) -> dict`
  - keep only defined, non-deleted keys; coerce values to stripped strings; drop empty values; drop values equal to the current value.
  - Returns `{key: {"new": str, "old": str | None}}`; empty result means no card.
- Front-matter helpers: `read_front_matter(path)`, `write_plan_file(...)`.

---

## 8. Domain logic

### 8.1 Meta proposal (FR-11…14)

- After a turn: `filter_meta(...)`; if non-empty, store JSON in `messages.meta_proposal`, `meta_status='pending'`.
- Card (rendered under that assistant message while `pending`): one row per key with label, an editable input prefilled with the proposed value, and the old value shown when it exists and differs (FR-14). Buttons: **Save** / **Dismiss**.
- Save: `POST /messages/{id}/meta` with the (possibly edited) values → merge into `clients.meta_json` (only the submitted keys; empty value = skip), set `meta_status='saved'`. Dismiss sets `'dismissed'`. Nothing touches `clients.meta_json` before this.
- Cards for `saved`/`dismissed` render as a small read-only note (or nothing).

### 8.2 Plan lifecycle (FR-15…20)

`save_plan_from_ai(chat, body_md)` — one DB transaction, read-then-write:

```
latest = latest non-deleted plan of this chat (by version)
if latest exists and latest.status == 'draft':
    overwrite its file (atomic), update title            # FR-16
else:
    version = 1 + MAX(version) over ALL plans of this chat incl. soft-deleted (0 if none)
    insert row (status='draft'), compute file path from new id, write file   # FR-15 / FR-18
set messages.plan_id for the assistant message
```
If the file write fails, roll back the DB change and treat the turn as failed (error message, retry available).

`approve(plan_id)` (FR-17):
- only `draft → approved`; idempotent for already-approved.
- re-render the file with `status: approved`, `approved_at` (date), and a **frozen meta snapshot**; write file first, then commit the DB row. Approved plans are never modified afterwards.
- A new `<plan>` block in a chat whose latest plan is approved always creates the next version as a draft.

Other rules:
- **Version scope = per chat** (each chat's plans form a lineage v1, v2, …). The client page lists plans of all chats grouped by chat, each with its version and status (FR-19). See §16 if you want per-client numbering instead.
- Examples = all non-deleted `approved` plans (Req §4). Soft-deleting a plan removes it from examples; files stay on disk.
- Plan panel (chat page) shows the latest non-deleted plan of the chat: version, status badge, rendered markdown, **Approve** button when draft.

### 8.3 Soft delete cascade (FR-4, 9, 20, 22, 29)

- Client delete: in one transaction set `deleted_at` (same timestamp) on the client, all its chats, and all its plans. Messages are not marked; they are hidden through their chat.
- Chat delete: chat only. Plans of that chat remain visible under the client? → **No**: delete the chat's plans too, to avoid orphan lineages (same timestamp). Agent discretion if you find a reason otherwise; record it in `DECISIONS.md`.
- Meta field soft-delete: the field disappears from forms and prompts; values already stored in `clients.meta_json` are kept untouched (and preserved when a client form is saved — merge, don't replace the whole JSON).
- No restore UI in v1.

### 8.4 Sources registration (FR-21…24)

- Upload: only `.md` (check extension, UTF-8 decodable, size limit ~1 MB); generated filename; `name` + `description` required.
- Startup scan of `data/sources/*.md`: for each file whose relative path is **not in `sources` at all (including soft-deleted rows)**, insert a row using front-matter `name`/`description` (fallback: filename / empty description + log warning). Soft-deleted sources must **not** come back on restart — hence the `UNIQUE(file_path)` that includes deleted rows.
- Toggle enabled, edit name/description, soft delete. Prompt builder only uses `enabled = 1 AND deleted_at IS NULL`.

### 8.5 Chat titles

On the first user message, set the title to its first ~40 characters (no AI call). Rename is optional (Agent discretion).

### 8.6 New chat (FR-5)

Form: pick an existing client **or** type a new client name (explicit choice, two radio options). Create client if needed, create chat, redirect to it.

---

## 9. HTTP surface (suggested; Agent discretion on exact URLs)

| Area | Routes |
|---|---|
| Chats | `GET /` (redirect to last chat or new-chat page), `GET /chats/new`, `POST /chats`, `GET /chats/{id}`, `POST /chats/{id}/messages`, `GET /chats/{id}/poll`, `POST /chats/{id}/retry`, `POST /chats/{id}/delete` |
| Meta card | `POST /messages/{id}/meta` (save), `POST /messages/{id}/meta/dismiss` |
| Plans | `POST /plans/{id}/approve`, `POST /plans/{id}/delete`, `GET /plans/{id}` (rendered view; used by client page) |
| Clients | `GET /clients`, `POST /clients`, `GET /clients/{id}`, `POST /clients/{id}` (name + meta form), `POST /clients/{id}/delete` |
| Settings | `GET /settings`, `POST /settings/cli`, `/settings/prompt`, meta-field CRUD + reorder, source CRUD (`/settings/sources/...`) |

Use HTMX partials for: sending messages, poll result, plan panel refresh, meta card save/dismiss, approve. Everything else can be plain form posts with redirects. Use the POST-only convention for mutations (no state change on GET).

---

## 10. UI notes

- `<html lang="fa" dir="rtl">`; use CSS logical properties (`margin-inline-start`, etc.). Message bubbles and plan content use `dir="auto"` so mixed Persian/English text renders correctly.
- Chat page: sidebar (chat list: title + client name + date, "new chat"), main conversation, header with client name (FR-7), plan panel. The input is disabled with a processing indicator while a turn runs; Enter sends, Shift+Enter newline (Agent discretion).
- Assistant messages: render visible text as markdown (§2 renderer, HTML disabled). If the message created/updated a plan, show a small chip ("برنامه پیش‌نویس به‌روز شد — v1").
- Fonts: system font stack that supports Persian; vendoring one Persian font (e.g. Vazirmatn) is optional.
- Dates: stored UTC; displayed in local time, Gregorian by default. A single Jinja filter `fmt_date` is the seam if you want Jalali later (see §16).
- Keep CSS in one small file. No JS framework; minimal vanilla JS only where HTMX is not enough (e.g. auto-scroll to the bottom of the conversation).

---

## 11. Security & safety (small, Fixed)

Command templates are editable in the UI and executed by the server, so a web page open in the trainer's browser must not be able to reach them.

1. Bind to `127.0.0.1` only.
2. Middleware: reject any request whose `Host` header is not `localhost:8005` / `127.0.0.1:8005` (blocks DNS rebinding), and reject non-GET requests whose `Origin` (or `Referer`) is present and not one of those origins (blocks cross-site form posts). ~20 lines; no CSRF-token machinery needed.
3. Subprocess: argv list, no shell (§7.1).
4. Rendering: Jinja2 autoescape on; markdown-it with `html=False` — AI output and source files are untrusted.
5. Uploads: generated filenames only, `.md` only, size cap. Plan paths are built from integer ids only.
6. Read-only AI: enforced by prompt **and** by CLI flags where available. The app never trusts the AI to have honored it, but it also does not try to diff the filesystem afterward.

Note: the AI's working directory (`data/`) also contains `app.db`. The prompt tells the AI to open only listed files. See §16 for an optional tweak.

---

## 12. Logging & errors

- One rotating file `data/app.log` (`RotatingFileHandler`, ~1 MB × 3) plus console.
- Log: startup, CLI invocations (CLI name, duration, exit code — **not** the full prompt by default), parse errors for blocks, soft warnings (missing source file), unhandled exceptions.
- UI never shows stack traces. Chat turn failures are shown as an error message in the chat (§4.2).

---

## 13. Testing (keep it lean)

- `pytest` with a temp `DATA_DIR` (config override via env) and an in-file SQLite.
- **`tests/fake_cli.py`**: a tiny Python script that reads the prompt from stdin and prints canned output (plain text, text + `<meta>`, text + `<plan>`, malformed blocks, non-zero exit, sleep for timeout). It lets the whole app be developed and tested without any real CLI, and can be wired as a command template (`python tests/fake_cli.py`). Optionally expose it as a hidden fourth CLI option in dev only.
- Unit tests required for: `parsers` (block extraction, malformed cases, meta filtering), `prompt_builder` (section order, history caps, error messages excluded, disabled/deleted sources excluded), plan lifecycle (draft overwrite, new version after approval, soft-deleted version numbering, approval idempotence), `ai_runner` (stdin vs `{prompt}`, timeout, non-zero exit, missing executable) using the fake CLI, soft-delete cascade.
- UI is verified manually through the acceptance checklist; no browser-test framework.

---

## 14. Implementation phases

Each phase leaves the app runnable. Tasks are suggestions — split or merge as needed. Phase order matters (dependencies noted). A phase is complete only when all its "Done when" items pass.

### Phase 0 — Skeleton & infrastructure
*Depends on: nothing. Covers: Req §11 (run/install/logging).*

Tasks:
- Create layout (§3), `requirements.txt`, `run.py`, `config.py` (paths, constants, `DATA_DIR` env override).
- `db.py`: connection helper, PRAGMAs, migration runner, full schema (§5), seed `users(1)` and default settings (§5.1) with `INSERT OR IGNORE`.
- `main.py`: lifespan (create `data/` dirs, init DB), Host/Origin middleware (§11), logging (§12).
- `base.html`: RTL layout, nav (Chats / Clients / Settings), vendored HTMX, `app.css`; markdown render helper (HTML disabled); `fmt_date` filter.
- `defaults.py` with the default system prompt (Appendix A) and placeholder command templates.

Done when:
- `python run.py` serves `http://localhost:8005` with the three nav pages (empty states) in RTL Persian.
- `data/app.db` is created with all tables; restarting does not duplicate or overwrite seeded settings.
- A request with a foreign `Origin` on a POST, or a foreign `Host`, is rejected.
- `pytest` runs (even if only a smoke test).

### Phase 1 — Settings
*Depends on: P0. Covers: FR-21…30.*

Tasks:
- Settings page: active CLI + three command templates (with reset to default), system prompt (with reset), default plan duration, timeout.
- Meta fields: add (key slug validation + uniqueness among live fields), edit label, reorder, soft delete.
- Sources: upload `.md` (validation, generated filename), list, toggle, edit name/description, soft delete; startup scan registering files in `data/sources/` (§8.4).

Done when:
- All settings persist across restarts.
- Adding a duplicate live meta key is rejected; re-adding a key after soft-delete works.
- A non-`.md` upload is rejected; an uploaded source appears in the list and on disk under `data/sources/`.
- A file dropped into `data/sources/` is registered on next start; after soft-deleting it, it is **not** re-registered on the following start.

### Phase 2 — Clients
*Depends on: P0, P1 (meta fields). Covers: FR-1…4.*

Tasks:
- Client list, create, view, edit name, meta form generated from active meta fields (merge-save, preserves unknown keys).
- Client page sections for chats and plans (empty placeholders; filled in later phases).
- Soft delete with cascade (§8.3).

Done when:
- Client created, meta edited and persisted; clearing a field removes the key; values of a soft-deleted meta field survive a form save.
- Deleting a client hides it everywhere and sets `deleted_at` on its (test-inserted) chats and plans; no rows or files are physically removed.

### Phase 3 — AI core (no chat UI yet)
*Depends on: P0, P1. Covers: Req §8.2, §9. Pure Python + tests.*

Tasks:
- `parsers.py` (§7.3), `prompt_builder.py` (§7.2), `ai_runner.py` (§7.1).
- `tests/fake_cli.py` and unit tests (§13).
- Look up current official docs for `claude`, `agy`, `codex`; write the default command templates (read-only, non-interactive, plain output, stdin if supported). Record the doc sources/versions in `docs/DECISIONS.md`.
- A tiny dev script or settings-page "Test CLI" button that sends a trivial prompt through `run_ai` and shows the output (useful for phase 7 too; Agent discretion).

Done when:
- Parser, prompt-builder and runner unit tests pass using the fake CLI (including timeout and non-zero exit).
- Each real CLI that is installed answers a trivial prompt through `run_ai` using its default template without hanging for approval.

### Phase 4 — Chat
*Depends on: P2, P3. Covers: FR-5…10 (FR-10 via prompt).*

Tasks:
- New-chat flow (§8.6), chat page with sidebar, header, conversation, input.
- Turn mechanics (§4.1): send → background turn → poll → assistant message; running guard; error message + Retry (§4.2).
- Auto title (§8.5), chat soft delete (§8.3), markdown rendering of assistant text.
- Page reload during a running turn shows the processing placeholder.

Done when (with the fake CLI and then one real CLI):
- A chat with a new or existing client shows the client name in the header; messages and replies persist across reload.
- A second send while a turn runs is rejected/disabled.
- Forced failures (missing CLI, timeout, non-zero exit) show an error message; Retry works; error messages never appear in later prompts.
- Restarting the server mid-turn leaves a recoverable state (Retry available).

### Phase 5 — Meta extraction
*Depends on: P4. Covers: FR-11…14.*

Tasks:
- Hook parsers + `filter_meta` into the turn: store `meta_proposal`/`meta_status` (§8.1).
- Card partial with editable values, old-vs-new display, Save/Dismiss endpoints.

Done when:
- A reply with `<meta>` containing defined + undefined keys shows a card with **only** defined keys, and values equal to current ones are omitted.
- Nothing changes in `clients.meta_json` until Save; edited values are what get saved; Dismiss saves nothing.
- Card state survives reload; malformed `<meta>` leaves the raw text visible and logs an error.

### Phase 6 — Plans
*Depends on: P4 (P5 not required, but the meta snapshot uses client meta). Covers: FR-15…20.*

Tasks:
- `save_plan_from_ai` (§8.2) wired into the turn; plan file writer (§6.2); message chip; plan panel with Approve.
- Approval, plan soft delete, client-page plan list grouped by chat with all versions rendered (FR-19).
- Prompt builder: include current plan path (item 4) and approved examples (item 6) — verify against real data.

Done when:
- First `<plan>` creates a draft file at `data/plans/<client_id>/plan-<id>-v1.md` and shows in the panel; a second `<plan>` in the same chat overwrites the same draft (no new file).
- Approve → front-matter `status: approved` + frozen meta; the file is no longer modified.
- Next `<plan>` after approval creates v2 as a draft; version numbering stays correct after a soft-deleted version.
- Approved plans appear in the example list in later prompts (also in other clients' chats); drafts and deleted plans do not.

### Phase 7 — Hardening & acceptance
*Depends on: all. Covers: Req §13.*

Tasks:
- Run the full acceptance checklist (Req §13, items 1–8) manually with **each** of the three CLIs; fix per-CLI output quirks.
- Edge cases: Persian text through stdin on the host OS, very long history (cap works), missing source file on disk, large plan, double-click on Approve, two browser tabs on the same chat, process-tree kill on timeout.
- `README.md` (install, run, configure CLIs, data layout, backup = copy `data/`), `docs/DECISIONS.md` final pass.

Done when:
- All eight acceptance criteria in Req §13 pass; switching `active_cli` alone moves execution to another tool (criterion 8).
- README lets a fresh checkout run with `pip install -r requirements.txt && python run.py`.

---

## 15. FR → phase traceability

| FR | Phase | FR | Phase |
|---|---|---|---|
| 1–4 | P2 | 15–20 | P6 |
| 5–10 | P4 | 21–24 | P1 |
| 11–14 | P5 | 25–30 | P1 |

Req §13 acceptance items: 1 → P0, 2 → P1, 3 → P4, 4 → P5, 5 → P6 (+P4), 6 → P6, 7 → P2/P4/P6/P1, 8 → P3/P7.

---

## 16. Assumptions & open points (defaults apply unless you say otherwise)

1. **Plan version scope** — per chat (§8.2). Alternative: per client (v1, v2… across all of a client's chats). Switching is a small change in `save_plan_from_ai` and the client-page grouping.
2. **Chat delete also soft-deletes its plans** (§8.3) so no orphan lineages remain.
3. **Examples cap** — most recent 50 approved plans listed in the prompt (§7.2); no ranking in v1 (Req §14 lists weighting as future).
4. **Client name not included** in the example list in the prompt (only meta + title + path). Plan files themselves contain `client_name` in front-matter (per Req §8.1), so the AI could still see it if it opens a file.
5. **`app.db` lives in `data/`** (per Req §3) and is therefore inside the AI's working directory. Optional tweak: keep DB and log in a sibling folder (e.g. `var/`) and keep `data/` for sources/plans only. One-line config change; not applied by default because the requirements fix the layout.
6. **Dates** shown in Gregorian by default; Jalali display (e.g. via `jdatetime`) can be added behind `fmt_date` if wanted.
7. **Front-matter `meta`** is written as a YAML block mapping rather than the inline `{k: v}` style shown in Req §8.1 (§6.2).
8. **Command templates are editable and executed** — hence the Host/Origin guard (§11), which is an addition to the requirements.

---

## Appendix A — Default system prompt (starting point; the agent may refine wording)

Stored in `defaults.py`, editable by the trainer in Settings. Format/protocol rules are **not** here (they are code-owned, §7.2).

```text
You are a nutrition-planning assistant working for a professional trainer/coach.
The trainer is the expert and the final decision-maker; you draft, they review.

- Reply in Persian unless the trainer writes in another language.
- Build meal plans from the trainer's description of the client. Ask a short clarifying
  question only when information essential to safety or feasibility is missing;
  otherwise state your assumptions and proceed.
- Before drafting, open the sources that are relevant (judge by their descriptions) and
  look at approved example plans for clients with similar profiles. Follow the sources;
  use examples for structure and style, not as templates to copy blindly.
- If the profile suggests a medical condition, pregnancy, an eating disorder, or other
  risk factors, say so explicitly and flag it for the trainer instead of working around it.
- Corrections from the trainer apply to the current conversation only.
- Never write, edit, or create files. You only read files that are listed for you.
- Keep conversational replies short; put the full plan inside the plan block when asked.
```
