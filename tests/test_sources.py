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
