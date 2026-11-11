import io
import pytest
from app import config, db, defaults
from app.parsers import serialize_source_markdown
from app.services import sources as source_service


def test_settings_persist_across_restarts_and_seed_not_overwritten(client):
    """
    TD §14 Phase 1 & T1.5:
    All settings persist across restarts; seeding on restart does not overwrite modified values.
    """
    custom_payload = {
        "active_cli": "agy",
        "cmd_claude": "claude custom --stdin {prompt}",
        "cmd_agy": "agy custom --read-only {prompt}",
        "cmd_codex": "codex custom --exec {prompt}",
        "system_prompt": "Custom system prompt for testing persistence across restarts.",
        "default_plan_duration": "سه هفته",
        "ai_timeout_seconds": "240",
    }

    # 1. Update settings via HTTP POST
    res = client.post("/settings", data=custom_payload, follow_redirects=False)
    assert res.status_code == 303

    # 2. Verify stored in DB
    settings_before = db.get_settings()
    for key, val in custom_payload.items():
        assert settings_before[key] == val

    # 3. Simulate application restart: run init_db and seed_defaults
    db.init_db(config.DB_PATH)
    with db.connect(config.DB_PATH) as conn:
        db.seed_defaults(conn)

    # 4. Verify settings were NOT overwritten by defaults
    settings_after = db.get_settings()
    for key, val in custom_payload.items():
        assert settings_after[key] == val, f"Setting '{key}' was overwritten by restart/seeding!"


def test_reset_to_default_all_supported_keys(client):
    """
    TD §14 Phase 1 & T1.5:
    'Reset to default' works for system prompt and each command template.
    """
    # Customize all four keys
    custom_settings = {
        "cmd_claude": "custom-claude-test",
        "cmd_agy": "custom-agy-test",
        "cmd_codex": "custom-codex-test",
        "system_prompt": "custom-prompt-test",
    }
    db.update_settings(custom_settings)

    # 1. Reset cmd_claude via /settings/reset
    res1 = client.post("/settings/reset", data={"key": "cmd_claude"}, follow_redirects=False)
    assert res1.status_code == 303
    assert db.get_setting("cmd_claude") == defaults.DEFAULT_CMD_CLAUDE
    # Ensure others untouched
    assert db.get_setting("cmd_agy") == "custom-agy-test"

    # 2. Reset cmd_agy via /settings/reset
    res2 = client.post("/settings/reset", data={"key": "cmd_agy"}, follow_redirects=False)
    assert res2.status_code == 303
    assert db.get_setting("cmd_agy") == defaults.DEFAULT_CMD_AGY

    # 3. Reset cmd_codex via /settings/reset
    res3 = client.post("/settings/reset", data={"key": "cmd_codex"}, follow_redirects=False)
    assert res3.status_code == 303
    assert db.get_setting("cmd_codex") == defaults.DEFAULT_CMD_CODEX

    # 4. Reset system_prompt via /settings/reset
    res4 = client.post("/settings/reset", data={"key": "system_prompt"}, follow_redirects=False)
    assert res4.status_code == 303
    assert db.get_setting("system_prompt") == defaults.DEFAULT_SYSTEM_PROMPT


def test_meta_key_validation_and_uniqueness(client):
    """
    TD §14 Phase 1 & T1.5:
    Meta key slug validation ([a-z0-9_]+) and uniqueness among live fields.
    """
    # 1. Invalid keys via HTTP return 400
    invalid_keys = [
        "Age",             # uppercase
        "target-weight",   # hyphen
        "water goal",      # space
        "calories!",       # punctuation
        "وزن",             # non-ASCII / Persian
        "",                # empty
        "   ",             # whitespace only
    ]
    for key in invalid_keys:
        res = client.post("/settings/meta-fields", data={"key": key, "label": "تست"})
        assert res.status_code == 400, f"Expected 400 for invalid key '{key}', got {res.status_code}"

    # 2. Valid key succeeds
    res_valid = client.post(
        "/settings/meta-fields",
        data={"key": "target_calories", "label": "کالری هدف"},
        follow_redirects=False,
    )
    assert res_valid.status_code == 303

    # 3. Duplicate live key is rejected with 400
    res_dup = client.post(
        "/settings/meta-fields",
        data={"key": "target_calories", "label": "کالری تکراری"},
    )
    assert res_dup.status_code == 400
    assert "already exists" in res_dup.text


def test_meta_key_readd_after_soft_delete(client):
    """
    TD §14 Phase 1 & T1.5:
    Re-adding a meta key after soft delete must work and preserve soft-deleted records.
    """
    # 1. Add key
    client.post("/settings/meta-fields", data={"key": "body_fat_pct", "label": "درصد چربی ۱"})
    active_before = db.active_meta_fields()
    field1 = next(f for f in active_before if f["key"] == "body_fat_pct")
    assert field1["label"] == "درصد چربی ۱"

    # 2. Soft delete the field
    res_del = client.post(f"/settings/meta-fields/{field1['id']}/delete", follow_redirects=False)
    assert res_del.status_code == 303
    active_after_del = db.active_meta_fields()
    assert not any(f["key"] == "body_fat_pct" for f in active_after_del)

    # 3. Re-add the same key with new label
    res_readd = client.post(
        "/settings/meta-fields",
        data={"key": "body_fat_pct", "label": "درصد چربی جدید"},
        follow_redirects=False,
    )
    assert res_readd.status_code == 303

    # 4. Active fields has the new one with new ID
    active_after_readd = db.active_meta_fields()
    field2 = next(f for f in active_after_readd if f["key"] == "body_fat_pct")
    assert field2["id"] != field1["id"]
    assert field2["label"] == "درصد چربی جدید"

    # 5. Adding again while second is live is rejected
    res_dup2 = client.post(
        "/settings/meta-fields",
        data={"key": "body_fat_pct", "label": "درصد چربی تکراری"},
    )
    assert res_dup2.status_code == 400

    # 6. Verify SQLite raw rows: both old and new exist
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, key, label, deleted_at FROM meta_fields WHERE key = 'body_fat_pct' ORDER BY id ASC"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["id"] == field1["id"]
        assert rows[0]["deleted_at"] is not None
        assert rows[1]["id"] == field2["id"]
        assert rows[1]["deleted_at"] is None


def test_source_upload_validations_and_rejections(client):
    """
    TD §14 Phase 1 & T1.5:
    Upload rejects non-.md, non-UTF-8, oversize, and missing name/description.
    """
    valid_name = "منبع تستی"
    valid_desc = "توضیحات تستی"
    valid_content = b"# Valid Markdown\nSome nutrition content."

    # 1. Non-.md extension rejected
    for bad_ext in ["doc.txt", "guide.pdf", "image.png", "no_extension"]:
        files = {"file": (bad_ext, io.BytesIO(valid_content), "text/plain")}
        res = client.post(
            "/settings/sources/upload",
            data={"name": valid_name, "description": valid_desc},
            files=files,
        )
        assert res.status_code == 400
        assert "Only .md files are accepted" in res.text

    # 2. Non-UTF-8 content rejected
    bad_bytes = b"\xff\xfe\x00\x00\x80\x81"
    files_bad_utf8 = {"file": ("corrupt.md", io.BytesIO(bad_bytes), "text/markdown")}
    res_utf8 = client.post(
        "/settings/sources/upload",
        data={"name": valid_name, "description": valid_desc},
        files=files_bad_utf8,
    )
    assert res_utf8.status_code == 400
    assert "valid UTF-8 text" in res_utf8.text

    # 3. Oversize rejected (> UPLOAD_MAX_BYTES)
    oversized_bytes = b"x" * (config.UPLOAD_MAX_BYTES + 1)
    files_oversize = {"file": ("huge.md", io.BytesIO(oversized_bytes), "text/markdown")}
    res_oversize = client.post(
        "/settings/sources/upload",
        data={"name": valid_name, "description": valid_desc},
        files=files_oversize,
    )
    assert res_oversize.status_code == 400
    assert "exceeds maximum allowed size" in res_oversize.text

    # 4. Missing name rejected
    for empty_name in ["", "   "]:
        files_name = {"file": ("valid.md", io.BytesIO(valid_content), "text/markdown")}
        res_name = client.post(
            "/settings/sources/upload",
            data={"name": empty_name, "description": valid_desc},
            files=files_name,
        )
        assert res_name.status_code == 400
        assert "Source name is required" in res_name.text

    # 5. Missing description rejected
    for empty_desc in ["", "   "]:
        files_desc = {"file": ("valid.md", io.BytesIO(valid_content), "text/markdown")}
        res_desc = client.post(
            "/settings/sources/upload",
            data={"name": valid_name, "description": empty_desc},
            files=files_desc,
        )
        assert res_desc.status_code == 400
        assert "Source description is required" in res_desc.text


def test_source_upload_generated_filename_different_from_uploaded(client):
    """
    TD §14 Phase 1 & T1.5:
    Uploaded filename is never used as a path; generated filename != uploaded name;
    path traversal attempts are neutralized.
    """
    user_filename = "my_custom_source.md"
    content = b"# Sports Hydration\nElectrolytes and fluids guidelines."

    files = {"file": (user_filename, io.BytesIO(content), "text/markdown")}
    res = client.post(
        "/settings/sources/upload",
        data={"name": "هیدراتاسیون ورزشی", "description": "دستورالعمل مایعات"},
        files=files,
        follow_redirects=False,
    )
    assert res.status_code == 303

    sources = db.active_sources()
    assert len(sources) == 1
    source = sources[0]

    # Verify generated path is in sources/ and follows slug-shortid.md
    file_path = source["file_path"]
    assert file_path.startswith("sources/هیدراتاسیون-ورزشی-")
    assert file_path.endswith(".md")
    assert file_path != f"sources/{user_filename}"
    assert user_filename not in file_path

    # Verify file is physically created under data/sources/
    disk_file = config.DATA_DIR / file_path
    assert disk_file.exists()
    assert disk_file.name != user_filename

    # Front-matter and content present
    file_text = disk_file.read_text(encoding="utf-8")
    assert "name: هیدراتاسیون ورزشی" in file_text
    assert "description: دستورالعمل مایعات" in file_text
    assert "# Sports Hydration" in file_text

    # Path traversal upload test
    traversal_files = {"file": ("../../../../etc/shadow.md", io.BytesIO(content), "text/markdown")}
    res_trav = client.post(
        "/settings/sources/upload",
        data={"name": "تست نفوذ مسیر", "description": "آزمون امنیت مسیر فایل"},
        files=traversal_files,
        follow_redirects=False,
    )
    assert res_trav.status_code == 303
    sources2 = db.active_sources()
    assert len(sources2) == 2
    trav_source = next(s for s in sources2 if s["name"] == "تست نفوذ مسیر")
    # Must be safely located inside data/sources/ without traversal tokens
    trav_disk = config.DATA_DIR / trav_source["file_path"]
    assert trav_disk.parent.resolve() == config.SOURCES_DIR.resolve()
    assert "shadow" not in trav_disk.name


def test_startup_scan_registers_dropped_file_and_ignores_soft_deleted():
    """
    TD §14 Phase 1 & T1.5:
    A file dropped into data/sources/ is registered on next start.
    After soft delete, it is NOT re-registered on the following start.
    """
    # 1. Drop a file with front-matter into data/sources/
    f1 = config.SOURCES_DIR / "dropped_guide.md"
    f1.write_text(
        serialize_source_markdown("راهنمای بیرونی", "اضافه شده از دیسک", "# Body 1"),
        encoding="utf-8",
    )

    # 2. Drop a plain file without front-matter
    f2 = config.SOURCES_DIR / "dropped_plain.md"
    f2.write_text("# Body 2 without front matter", encoding="utf-8")

    # 3. Drop a non-markdown file (must be ignored by scan)
    f3 = config.SOURCES_DIR / "ignored.txt"
    f3.write_text("Should be ignored", encoding="utf-8")

    # Run startup scan
    registered = source_service.scan_and_register_sources()
    assert len(registered) == 2

    active = db.active_sources()
    assert len(active) == 2
    s1 = next(s for s in active if s["file_path"] == "sources/dropped_guide.md")
    assert s1["name"] == "راهنمای بیرونی"
    assert s1["description"] == "اضافه شده از دیسک"

    s2 = next(s for s in active if s["file_path"] == "sources/dropped_plain.md")
    assert s2["name"] == "dropped_plain.md"
    assert s2["description"] == ""

    # 4. Idempotence: scanning again registers 0 files
    reg_idempotent = source_service.scan_and_register_sources()
    assert len(reg_idempotent) == 0
    assert len(db.active_sources()) == 2

    # 5. Soft-delete s1
    db.soft_delete_source(s1["id"])
    assert len(db.active_sources()) == 1
    assert db.get_source(s1["id"]) is None

    # Invariant: file physically remains on disk
    assert f1.exists()

    # 6. Re-scan (simulate subsequent startup)
    reg_after_del = source_service.scan_and_register_sources()
    assert len(reg_after_del) == 0

    # s1 must NOT be resurrected; active sources remains 1
    assert len(db.active_sources()) == 1
    assert db.get_source(s1["id"]) is None

    # In SQLite raw table, s1 is still present with deleted_at
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM sources WHERE file_path = 'sources/dropped_guide.md'").fetchone()
        assert row is not None
        assert row["deleted_at"] is not None
