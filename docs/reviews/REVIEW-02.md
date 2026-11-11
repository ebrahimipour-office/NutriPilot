# REVIEW-02 — Phase 1 Settings, Meta Fields & Sources

- **Review task:** R2
- **Tasks covered:** T1.1 – T1.G (+ F1 fixes)
- **Diff range:** `3f5e768b5072754f41794362c4c285a7844e93f5..4e7a3c29ddcfeef92d748f2aff3599050d6e4144`
- **Files changed / lines changed:** 10 files changed, +1721 −13 (excluding tests/vendored)
- **Test run:** `pytest -q` → 65 passed, 2 warnings in 2.15s
- **Verdict:** Approved with fixes

## Summary
Phase 1 implements complete settings management, dynamic meta field CRUD with partial unique index semantics and soft-delete re-addition, secure markdown source uploads with generated paths, and startup disk scanning with front-matter extraction. The implementation strictly adheres to the core architectural invariants: no ORMs, per-call SQLite connections with WAL mode, non-overwriting seeds, atomic file updates via temporary files, and server-rendered HTML with autoescaping and no raw HTML markdown parsing. All 65 tests pass. Five findings were identified (0 Critical, 0 High, 2 Medium, 3 Low), focusing on UTF-8 BOM tolerance in front-matter parsing, disk overwrite prevention in uploads, and consistent input validation in modular endpoints.

## Findings

### R2-01 — UTF-8 BOM prevents front-matter regex matching in parse_front_matter
- **Severity:** Medium
- **Category:** data-integrity
- **Location:** `app/parsers.py:11-14` (TD §7.3)
- **Description:** `parse_front_matter` matches the front-matter block using regex `r"^---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n)?(.*)$"`. When markdown files are created or saved on Windows using default tools (like Notepad), they frequently start with a Byte Order Mark (`\ufeff`). Because `re.match` checks from index 0, the leading BOM prevents the pattern from matching, causing valid front-matter metadata (`name`, `description`) to be dropped into the body text.
- **Suggested fix:** Strip leading BOM characters (`text = text.lstrip("\ufeff")`) before executing regex pattern matching in `parse_front_matter`.
- **Status:** [ ] open
- **Resolution:** 

### R2-02 — Avoid potential disk overwrite and data loss if generated file path already exists
- **Severity:** Medium
- **Category:** data-integrity
- **Location:** `app/services/sources.py:86-115` (TD §6.1, §8.4)
- **Description:** In `upload_source`, the generated target filename is `f"{slug}-{short_id}.md"`. `save_source_file(abs_path, file_content)` immediately writes to a temporary file and executes `os.replace(temp_name, abs_path)`. If a file already exists at `abs_path` (e.g. from a manually dropped unindexed file or hash collision), `os.replace` silently replaces it. Furthermore, if the subsequent SQLite `db.insert_source` fails (for example, due to `UNIQUE(file_path)` constraint violation), the exception handler executes `abs_path.unlink()`, permanently destroying the previously existing disk file.
- **Suggested fix:** In `upload_source`, verify that `abs_path.exists()` is false before saving; if a collision occurs, generate a new short ID in a bounded loop until an unused path is found.
- **Status:** [ ] open
- **Resolution:** 

### R2-03 — Inconsistent empty-string handling for default_plan_duration in modular prompt endpoint
- **Severity:** Low
- **Category:** error-handling
- **Location:** `app/routes/settings.py:184-186` (TD §9)
- **Description:** In the main `/settings` form handler, `default_plan_duration` falls back to `"یک هفته"` if empty (`default_plan_duration.strip() or "یک هفته"`). However, in `/settings/prompt`, submitting an empty or whitespace-only `default_plan_duration` sets `updates["default_plan_duration"] = ""` without validation or fallback, persisting an empty duration string to the `settings` table.
- **Suggested fix:** In `update_prompt_settings`, ensure `default_plan_duration` falls back to `"یک هفته"` or rejects empty input with 400 Bad Request if submitted.
- **Status:** [ ] open
- **Resolution:** 

### R2-04 — Prevent non-positive IDs in reorder_meta_fields_endpoint
- **Severity:** Low
- **Category:** maintainability
- **Location:** `app/routes/settings.py:248-252` (TD §5.1, §8.3)
- **Description:** When parsing the comma-separated `order` string in `reorder_meta_fields_endpoint`, integer conversion is wrapped in `int(x.strip())`. However, negative integers or zero values are not rejected prior to invoking `db.reorder_meta_fields`. While the query filters `WHERE id = ? AND deleted_at IS NULL`, validating that all submitted IDs are positive integers improves defensive input sanitation.
- **Suggested fix:** Validate that all parsed integer IDs in `reorder_meta_fields_endpoint` are positive (`id > 0`).
- **Status:** [ ] open
- **Resolution:** 

### R2-05 — Explicit UTF-8 decoding in read_front_matter exception handling
- **Severity:** Low
- **Category:** maintainability
- **Location:** `app/parsers.py:32` (TD §7.3)
- **Description:** `read_front_matter` uses `content = p.read_text(encoding="utf-8", errors="replace")`. While `errors="replace"` safely avoids decoding crashes on corrupted files, files with unreadable binary content or unhandled exceptions swallow errors silently returning `{}` without logging a warning.
- **Suggested fix:** Add a logger warning when `read_front_matter` fails or encounters an exception while reading an existing file.
- **Status:** [ ] open
- **Resolution:** 

## Positive notes (optional)
- **Clean Invariant Adherence:** Every read query in `app/db.py` on live tables (`active_meta_fields`, `get_meta_field`, `active_sources`, `get_source`) strictly filters `deleted_at IS NULL`.
- **Startup Scan Idempotence:** `get_all_source_file_paths` correctly includes soft-deleted rows, ensuring that dropped files registered once and later soft-deleted are never resurrected on subsequent startups.
- **Zero ORM / Pure SQL:** `meta_fields` reordering and partial index handling (`ux_meta_fields_key`) work directly and predictably against SQLite with WAL mode.
- **Comprehensive Test Coverage:** 65 automated tests cover unit validations, HTTP endpoints, soft-delete lifecycles, and disk persistence invariants without mocking SQLite.
