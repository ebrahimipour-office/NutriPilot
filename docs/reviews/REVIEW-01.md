# REVIEW-01 — Phase 0 Foundation

- **Review task:** R1
- **Tasks covered:** T0.1 – T0.G
- **Diff range:** `b330d155e78b4d5d916a25d554ad1ba46d2f0e14..c29e45a1eeb50cd283c9d7120e31eaa58de36f4d`
- **Files changed / lines changed:** 23 files changed, +765 −0 (excluding tests/vendored)
- **Test run:** `pytest -q` → 24 passed, 3 warnings in 0.93s
- **Verdict:** Approved with fixes

## Summary
Phase 0 establishes a clean, minimal foundation strictly adhering to the "Boring tech" architectural directives: single-worker FastAPI server, stdlib SQLite persistence in WAL mode with per-call connection lifecycle, pure SSR with Jinja2 and vendored HTMX, safe markdown rendering (`html=False`), and strict Host/Origin security middleware. The full TD §5 SQL schema, constraints, partial unique index, and views match the specification. All 24 tests pass. Five findings were identified (0 Critical, 0 High, 2 Medium, 3 Low), primarily concerning defense-in-depth on dual Origin/Referer header evaluation, atomic migration version updates, and Starlette deprecation cleanup.

## Findings

### R1-01 — Validate both Origin and Referer when both headers are present on state-changing requests
- **Severity:** Medium
- **Category:** security
- **Location:** `app/main.py:59-67` (TD §11.2)
- **Description:** In `SecurityGuardMiddleware.dispatch`, the Origin/Referer check uses `if origin is not None: ... elif referer: ...`. If a state-changing request (POST/PUT/DELETE) carries both headers (e.g. via an adversarial proxy or crafted client), only `Origin` is evaluated and `Referer` is bypassed. While standard browsers enforce `Origin`, checking both headers when present provides stronger defense-in-depth against header tampering and misconfigured proxies.
- **Suggested fix:** If `origin is not None`, validate that `origin_clean in allowed_origins`. If `referer` is also present, validate that `ref_origin in allowed_origins` as well before allowing the request to proceed.
- **Status:** [ ] open
- **Resolution:** 

### R1-02 — Atomicity of user_version update with executescript in run_migrations
- **Severity:** Medium
- **Category:** data-integrity
- **Location:** `app/db.py:119-121` (TD §5 notes)
- **Description:** `sqlite3.Cursor.executescript` automatically issues a `COMMIT` before running the SQL script and executes the script in its own internal transaction. However, `cur.execute(f"PRAGMA user_version = {idx}")` runs in a separate step after `executescript`. If execution is aborted between the two statements (e.g. process termination or power loss), the schema could be applied while `user_version` remains at the previous number, causing subsequent startup attempts to fail on duplicate table creation.
- **Suggested fix:** Include the `PRAGMA user_version = {idx};` directly at the end of each migration SQL script executed by `executescript`, ensuring the schema statements and version update are executed and committed together.
- **Status:** [ ] open
- **Resolution:** 

### R1-03 — Default ALLOWED_HOSTS includes unadorned localhost and 127.0.0.1 without port
- **Severity:** Low
- **Category:** design-conformance
- **Location:** `app/config.py:45-46` (TD §11.2)
- **Description:** TD §11.2 specifies rejecting any request whose `Host` header is not `localhost:8005` or `127.0.0.1:8005` (to prevent DNS rebinding attacks). `config.get_allowed_hosts()` currently includes `"localhost"` and `"127.0.0.1"` without the port. While localhost resolution is local, omitting the port allows requests targeted at port 80/default port if forwarded to 8005.
- **Suggested fix:** Restrict default `get_allowed_hosts()` to `{f"localhost:{PORT}".lower(), f"127.0.0.1:{PORT}".lower(), "testserver"}`.
- **Status:** [ ] open
- **Resolution:** 

### R1-04 — DeprecationWarning in Jinja2Templates autoescape option
- **Severity:** Low
- **Category:** maintainability
- **Location:** `app/templating.py:30`
- **Description:** Passing `autoescape=True` as a keyword argument to `Jinja2Templates` raises `DeprecationWarning: Extra environment options are deprecated. Use a preconfigured jinja2.Environment instead.` in current Starlette versions.
- **Suggested fix:** Construct a preconfigured `jinja2.Environment` with `FileSystemLoader` and `select_autoescape(["html", "xml"])`, then initialize `Jinja2Templates(env=env)`.
- **Status:** [ ] open
- **Resolution:** 

### R1-05 — Track auto-code-ai.log in .gitignore
- **Severity:** Low
- **Category:** hygiene
- **Location:** `.gitignore`
- **Description:** An untracked file `auto-code-ai.log` appeared in the repository root from automated CLI runs. The `.gitignore` file should ignore `*.log` in the root and subdirectories (except `data/` which is already ignored).
- **Suggested fix:** Add `*.log` to `.gitignore`.
- **Status:** [ ] open
- **Resolution:** 

## Positive notes (optional)
- **Zero ORM / Zero Abstraction Overhead:** `app/db.py` uses stdlib `sqlite3` cleanly with connection-level WAL mode, foreign keys, and busy timeout.
- **Strict Markdown Safety:** `MarkdownIt("commonmark", {"html": False})` guarantees no raw HTML injection through markdown parsing.
- **RTL Logical Layout:** Clean CSS logical properties (`margin-inline`, `margin-block`, `text-align: start`) and `dir="rtl"` provide first-class Persian presentation without layout bugs.
- **Test Isolation:** `tests/conftest.py` completely isolates each test execution using a temporary `DATA_DIR` fixture, avoiding disk residue.
