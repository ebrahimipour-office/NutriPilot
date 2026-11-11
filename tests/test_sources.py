import io
import pytest
from pathlib import Path
from app import config, db
from app.parsers import parse_front_matter, read_front_matter, serialize_source_markdown
from app.services import sources as source_service


def test_slugify():
    # English with special characters
    assert source_service.slugify("Diet Guide 2026! @#") == "diet-guide-2026"
    # Persian text
    assert source_service.slugify("راهنمای پروتئین ورزشی") == "راهنمای-پروتئین-ورزشی"
    # Fallback to source when empty or only symbols
    assert source_service.slugify("!@#$%^&*()") == "source"
    assert source_service.slugify("   ") == "source"
    # Collapse multiple dashes / underscores
    assert source_service.slugify("foo__bar---baz  qux") == "foo-bar-baz-qux"


def test_front_matter_parsing_and_serialization(tmp_path):
    # Without front-matter
    raw_md = "# Title\n\nSome body text."
    fm, body = parse_front_matter(raw_md)
    assert fm == {}
    assert body == raw_md

    # With valid front-matter
    with_fm = "---\nname: Sports Diet\ndescription: Athletes guide\n---\n# Body Title\nBody content"
    fm, body = parse_front_matter(with_fm)
    assert fm == {"name": "Sports Diet", "description": "Athletes guide"}
    assert body.strip() == "# Body Title\nBody content"

    # Malformed YAML front-matter should return empty dict and keep raw text visible
    bad_fm = "---\n[invalid yaml: \n---\nBody text"
    fm, body = parse_front_matter(bad_fm)
    assert fm == {}
    assert body == bad_fm

    # serialize_source_markdown
    serialized = serialize_source_markdown(
        name="Ketogenic",
        description="Low carb guideline",
        body_text="# Header\n\n- Fat: 70%\n- Protein: 25%",
    )
    assert "name: Ketogenic" in serialized
    assert "description: Low carb guideline" in serialized
    assert "# Header\n\n- Fat: 70%\n- Protein: 25%" in serialized

    # Save to disk and read back with read_front_matter
    test_file = tmp_path / "test_doc.md"
    test_file.write_text(serialized, encoding="utf-8")
    loaded_fm = read_front_matter(test_file)
    assert loaded_fm["name"] == "Ketogenic"
    assert loaded_fm["description"] == "Low carb guideline"

    # read_front_matter on non-existent file returns empty dict
    assert read_front_matter(tmp_path / "non_existent.md") == {}


def test_upload_source_success():
    name = "راهنمای پروتئین"
    desc = "تنظیم دریافت پروتئین در ورزشکاران"
    content = b"# Protein Guide\n2g per kg bodyweight."
    uploaded_filename = "original_name_from_user.md"

    result = source_service.upload_source(
        name=name,
        description=desc,
        filename=uploaded_filename,
        content=content,
    )

    assert result["id"] is not None
    assert result["name"] == name
    assert result["description"] == desc
    assert result["file_path"].startswith("sources/راهنمای-پروتئین-")
    assert result["file_path"].endswith(".md")
    assert result["abs_path"].exists()

    # Verify generated filename != uploaded filename
    assert result["abs_path"].name != uploaded_filename

    # Verify front-matter written and body untouched
    disk_content = result["abs_path"].read_text(encoding="utf-8")
    assert "# Protein Guide\n2g per kg bodyweight." in disk_content

    fm = read_front_matter(result["abs_path"])
    assert fm["name"] == name
    assert fm["description"] == desc

    # Verify DB record
    source_row = db.get_source(result["id"])
    assert source_row is not None
    assert source_row["name"] == name
    assert source_row["description"] == desc
    assert source_row["file_path"] == result["file_path"]
    assert source_row["enabled"] == 1
    assert source_row["deleted_at"] is None


def test_upload_source_extension_validation():
    with pytest.raises(ValueError, match="Only .md files are accepted"):
        source_service.upload_source(
            name="Test",
            description="Desc",
            filename="guide.txt",
            content=b"# text",
        )

    with pytest.raises(ValueError, match="Only .md files are accepted"):
        source_service.upload_source(
            name="Test",
            description="Desc",
            filename="no_extension",
            content=b"# text",
        )


def test_upload_source_size_validation():
    oversized = b"a" * (config.UPLOAD_MAX_BYTES + 1)
    with pytest.raises(ValueError, match="exceeds maximum allowed size"):
        source_service.upload_source(
            name="Test",
            description="Desc",
            filename="oversized.md",
            content=oversized,
        )


def test_upload_source_utf8_validation():
    invalid_utf8 = b"\xff\xfe\x00\x00\x80"
    with pytest.raises(ValueError, match="valid UTF-8 text"):
        source_service.upload_source(
            name="Test",
            description="Desc",
            filename="invalid.md",
            content=invalid_utf8,
        )


def test_upload_source_missing_name_or_desc():
    with pytest.raises(ValueError, match="Source name is required"):
        source_service.upload_source(
            name="   ",
            description="Desc",
            filename="test.md",
            content=b"# content",
        )

    with pytest.raises(ValueError, match="Source description is required"):
        source_service.upload_source(
            name="Name",
            description="",
            filename="test.md",
            content=b"# content",
        )


def test_upload_source_path_traversal_prevention():
    malicious_filename = "../../../etc/passwd.md"
    result = source_service.upload_source(
        name="Traversal Test",
        description="Checking path traversal safety",
        filename=malicious_filename,
        content=b"# Safe",
    )

    # Must be safely inside SOURCES_DIR
    assert result["abs_path"].parent.resolve() == config.SOURCES_DIR.resolve()
    assert "passwd" not in result["abs_path"].name
    assert result["file_path"].startswith("sources/traversal-test-")


def test_upload_source_db_rollback_on_failure(monkeypatch):
    def failing_insert(*args, **kwargs):
        raise RuntimeError("Database simulated failure")

    monkeypatch.setattr(db, "insert_source", failing_insert)

    with pytest.raises(RuntimeError, match="Database simulated failure"):
        source_service.upload_source(
            name="Rollback Test",
            description="Ensure file is deleted if DB fails",
            filename="test.md",
            content=b"# Will fail DB",
        )

    # Ensure no files left in sources directory
    created_files = list(config.SOURCES_DIR.glob("*.md"))
    assert len(created_files) == 0


def test_http_upload_source_endpoint(client):
    file_bytes = b"# Nutrition 101\nEssential macronutrients..."
    files = {"file": ("nutrition.md", io.BytesIO(file_bytes), "text/markdown")}
    data = {
        "name": "تغذیه پایه",
        "description": "مرجع کلی اصول تغذیه",
    }

    response = client.post("/settings/sources/upload", data=data, files=files, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/settings?source_uploaded=1"

    # Verify source was inserted in DB
    sources = db.active_sources()
    assert len(sources) == 1
    assert sources[0]["name"] == "تغذیه پایه"
    assert sources[0]["description"] == "مرجع کلی اصول تغذیه"
    assert sources[0]["file_path"].startswith("sources/تغذیه-پایه-")

    # Follow redirect and check alert
    get_resp = client.get("/settings?source_uploaded=1")
    assert get_resp.status_code == 200
    assert "منبع جدید با موفقیت آپلود و ذخیره شد" in get_resp.text


def test_http_upload_source_invalid_extension(client):
    file_bytes = b"# Invalid\nThis is not a markdown file"
    files = {"file": ("document.pdf", io.BytesIO(file_bytes), "application/pdf")}
    data = {"name": "Test PDF", "description": "Desc"}

    response = client.post("/settings/sources/upload", data=data, files=files)
    assert response.status_code == 400
    assert "Only .md files are accepted" in response.text


def test_db_toggle_source_enabled():
    source_id = db.insert_source(
        name="Toggle Test",
        description="Testing toggle",
        file_path="sources/toggle-test.md",
        enabled=1,
    )
    assert db.get_source(source_id)["enabled"] == 1

    # Toggle 1 -> 0
    new_val = db.toggle_source_enabled(source_id)
    assert new_val == 0
    assert db.get_source(source_id)["enabled"] == 0

    # Toggle 0 -> 1
    new_val = db.toggle_source_enabled(source_id)
    assert new_val == 1
    assert db.get_source(source_id)["enabled"] == 1

    # Invalid source id raises ValueError
    with pytest.raises(ValueError, match="not found or deleted"):
        db.toggle_source_enabled(99999)


def test_db_update_source():
    source_id = db.insert_source(
        name="Original Name",
        description="Original Desc",
        file_path="sources/update-test.md",
    )

    db.update_source(source_id, name="Updated Name", description="Updated Desc")
    row = db.get_source(source_id)
    assert row["name"] == "Updated Name"
    assert row["description"] == "Updated Desc"

    # Empty name rejected
    with pytest.raises(ValueError, match="Source name is required"):
        db.update_source(source_id, name="   ", description="Desc")

    # Non-existent source raises ValueError
    with pytest.raises(ValueError, match="not found or deleted"):
        db.update_source(99999, name="Test", description="Desc")


def test_db_soft_delete_source():
    # Create file on disk
    test_file = config.SOURCES_DIR / "delete-test.md"
    test_file.write_text("# Content", encoding="utf-8")

    source_id = db.insert_source(
        name="To Delete",
        description="Will be soft deleted",
        file_path="sources/delete-test.md",
    )

    assert len(db.active_sources()) == 1
    db.soft_delete_source(source_id)

    # Invariant: active_sources() must exclude soft-deleted rows
    assert len(db.active_sources()) == 0
    assert db.get_source(source_id) is None

    # Invariant: file on disk MUST NOT be deleted
    assert test_file.exists()

    # Deleting already deleted raises ValueError
    with pytest.raises(ValueError, match="not found or already deleted"):
        db.soft_delete_source(source_id)


def test_startup_scan_with_front_matter():
    doc_path = config.SOURCES_DIR / "expert-guide.md"
    content = serialize_source_markdown(
        name="راهنمای حرفه‌ای",
        description="تنظیم کربوهیدرات در دوران حجم",
        body_text="# Carbs in bulking\n5-7g per kg.",
    )
    doc_path.write_text(content, encoding="utf-8")

    registered = source_service.scan_and_register_sources()
    assert len(registered) == 1

    sources = db.active_sources()
    assert len(sources) == 1
    assert sources[0]["name"] == "راهنمای حرفه‌ای"
    assert sources[0]["description"] == "تنظیم کربوهیدرات در دوران حجم"
    assert sources[0]["file_path"] == "sources/expert-guide.md"
    assert sources[0]["enabled"] == 1


def test_startup_scan_fallback_and_warning(caplog):
    import logging
    # File without front-matter
    plain_file = config.SOURCES_DIR / "unstructured_notes.md"
    plain_file.write_text("# Just Notes\nNo front matter here.", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="nutripilot"):
        registered = source_service.scan_and_register_sources()

    assert len(registered) == 1
    sources = db.active_sources()
    assert len(sources) == 1
    assert sources[0]["name"] == "unstructured_notes.md"
    assert sources[0]["description"] == ""
    assert sources[0]["file_path"] == "sources/unstructured_notes.md"

    # Verify fallback warning was logged
    assert any("registered with fallback" in record.message for record in caplog.records)


def test_startup_scan_idempotence():
    doc_path = config.SOURCES_DIR / "sample.md"
    doc_path.write_text("# Sample", encoding="utf-8")

    reg1 = source_service.scan_and_register_sources()
    assert len(reg1) == 1

    # Second scan should register nothing
    reg2 = source_service.scan_and_register_sources()
    assert len(reg2) == 0
    assert len(db.active_sources()) == 1


def test_startup_scan_never_reregisters_soft_deleted_source():
    doc_path = config.SOURCES_DIR / "perennial.md"
    doc_path.write_text("# Evergreen", encoding="utf-8")

    # Initial registration
    reg1 = source_service.scan_and_register_sources()
    assert len(reg1) == 1
    source_id = reg1[0]

    # Soft delete the source
    db.soft_delete_source(source_id)
    assert len(db.active_sources()) == 0

    # Invariant: disk file remains
    assert doc_path.exists()

    # Subsequent scan MUST NOT re-register the soft-deleted source
    reg2 = source_service.scan_and_register_sources()
    assert len(reg2) == 0
    assert len(db.active_sources()) == 0


def test_http_source_management_endpoints(client):
    # 1. Create a source
    source_id = db.insert_source(
        name="منبع تستی",
        description="توضیح اولیه",
        file_path="sources/test-http.md",
        enabled=1,
    )

    # 2. Toggle via POST /settings/sources/{id}/toggle
    resp = client.post(f"/settings/sources/{source_id}/toggle", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings?source_updated=1"
    assert db.get_source(source_id)["enabled"] == 0

    # 3. Edit via POST /settings/sources/{id}/edit
    edit_data = {
        "name": "نام ویرایش شده",
        "description": "توضیح ویرایش شده",
    }
    resp = client.post(f"/settings/sources/{source_id}/edit", data=edit_data, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings?source_updated=1"
    updated = db.get_source(source_id)
    assert updated["name"] == "نام ویرایش شده"
    assert updated["description"] == "توضیح ویرایش شده"

    # 4. Edit with empty name returns 400
    bad_edit = {"name": "   ", "description": "any"}
    resp = client.post(f"/settings/sources/{source_id}/edit", data=bad_edit)
    assert resp.status_code == 400

    # 5. Dispatcher POST /settings/sources/{id}
    disp_edit = {"name": "نام دیسپچر", "description": "توضیح دیسپچر"}
    resp = client.post(f"/settings/sources/{source_id}", data=disp_edit, follow_redirects=False)
    assert resp.status_code == 303
    assert db.get_source(source_id)["name"] == "نام دیسپچر"

    disp_toggle = {"action": "toggle"}
    resp = client.post(f"/settings/sources/{source_id}", data=disp_toggle, follow_redirects=False)
    assert resp.status_code == 303
    assert db.get_source(source_id)["enabled"] == 1

    # 6. Delete via POST /settings/sources/{id}/delete
    resp = client.post(f"/settings/sources/{source_id}/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings?source_deleted=1"
    assert len(db.active_sources()) == 0

    # 7. Check UI renders alerts and table
    page_resp = client.get("/settings?source_updated=1")
    assert page_resp.status_code == 200
    assert "منبع با موفقیت به‌روزرسانی شد" in page_resp.text

    del_resp = client.get("/settings?source_deleted=1")
    assert del_resp.status_code == 200
    assert "منبع حذف گردید" in del_resp.text


def test_front_matter_parsing_with_utf8_bom():
    """Regression test R2-01: UTF-8 BOM must not break front-matter parsing."""
    raw_with_bom = "\ufeff---\nname: راهنمای ویندوز\ndescription: تست با BOM\n---\n# عنوان اصلی\nمتن بدنه."
    fm, body = parse_front_matter(raw_with_bom)
    assert fm == {"name": "راهنمای ویندوز", "description": "تست با BOM"}
    assert body.strip() == "# عنوان اصلی\nمتن بدنه."


def test_upload_source_collision_avoidance(monkeypatch):
    """Regression test R2-02: upload_source avoids overwriting existing disk files."""
    name = "تست تداخل نام"
    desc = "بررسی عدم بازنویسی فایل‌های موجود"
    content = b"# Existing content that must survive"

    # Pre-create a file that matches the slug
    slug = source_service.slugify(name)
    colliding_file = config.SOURCES_DIR / f"{slug}-11223344.md"
    colliding_file.write_text("Pre-existing data that must not be overwritten", encoding="utf-8")

    # Sequence of short IDs: first returns '11223344' (collides), second returns '55667788' (free)
    ids = iter(["11223344", "55667788"])
    monkeypatch.setattr(source_service.secrets, "token_hex", lambda n: next(ids))

    result = source_service.upload_source(
        name=name,
        description=desc,
        filename="test.md",
        content=content,
    )

    # Generated file must use the non-colliding ID
    assert result["abs_path"].name == f"{slug}-55667788.md"
    assert result["abs_path"].exists()

    # Pre-existing file must remain intact
    assert colliding_file.exists()
    assert colliding_file.read_text(encoding="utf-8") == "Pre-existing data that must not be overwritten"


def test_read_front_matter_logs_warning_on_unreadable_file(tmp_path, caplog):
    """Regression test R2-05: read_front_matter logs warning when reading fails."""
    import logging

    bad_file = tmp_path / "permission_denied.md"
    bad_file.write_text("# Test", encoding="utf-8")

    def failing_read(*args, **kwargs):
        raise PermissionError("Simulated permission error")

    with caplog.at_level(logging.WARNING, logger="nutripilot"):
        import unittest.mock
        with unittest.mock.patch.object(Path, "read_text", side_effect=failing_read):
            res = read_front_matter(bad_file)
            assert res == {}

    assert any("Failed to read front-matter" in record.message for record in caplog.records)


