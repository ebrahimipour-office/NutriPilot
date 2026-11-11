import os
import re
import secrets
import sqlite3
import tempfile
import unicodedata
from pathlib import Path

from app import config, db
from app.parsers import serialize_source_markdown


def slugify(text: str) -> str:
    """
    Generate a clean slug from text. Preserves Unicode alphanumeric characters
    (including Persian/Arabic letters and numbers), replaces whitespace and
    symbols with hyphens, collapses consecutive hyphens, and truncates to 50 chars.
    """
    normalized = unicodedata.normalize("NFKC", text.strip())
    cleaned = re.sub(r"[^\w\s-]", "", normalized.lower(), flags=re.UNICODE)
    slug = re.sub(r"[-\s_]+", "-", cleaned).strip("-")
    if not slug:
        slug = "source"
    return slug[:50]


def save_source_file(file_path: Path, content: str) -> None:
    """
    Atomically writes the string content to file_path using a temporary file
    in the same directory.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    dir_name = file_path.parent
    with tempfile.NamedTemporaryFile("w", dir=dir_name, encoding="utf-8", delete=False) as tf:
        tf.write(content)
        temp_name = tf.name
    os.replace(temp_name, file_path)


def upload_source(
    name: str,
    description: str,
    filename: str,
    content: bytes,
    user_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict:
    """
    Validates, saves to disk with generated filename, and registers a markdown source.

    - Extension must be .md
    - Content must be <= UPLOAD_MAX_BYTES
    - Content must be UTF-8 decodable
    - Name and description must be non-empty
    - Generated filename format: data/sources/<slug>-<short-id>.md (uploaded filename never used as a path)
    - Writes self-describing front-matter without altering the source body
    - Inserts a row in DB with relative path sources/<slug>-<short-id>.md
    """
    clean_name = name.strip() if name else ""
    if not clean_name:
        raise ValueError("Source name is required")

    clean_desc = description.strip() if description else ""
    if not clean_desc:
        raise ValueError("Source description is required")

    # Extension check: accept only .md
    if not filename or not filename.lower().endswith(".md"):
        raise ValueError("Only .md files are accepted")

    # Size check
    if len(content) > config.UPLOAD_MAX_BYTES:
        raise ValueError(
            f"File size ({len(content)} bytes) exceeds maximum allowed size of {config.UPLOAD_MAX_BYTES} bytes"
        )

    # UTF-8 decoding check
    try:
        body_text = content.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError("File content must be valid UTF-8 text") from e

    # Generate filename and path
    slug = slugify(clean_name)
    short_id = secrets.token_hex(4)
    file_name = f"{slug}-{short_id}.md"
    rel_path = f"sources/{file_name}"
    abs_path = config.SOURCES_DIR / file_name

    # Prepare markdown with front-matter
    file_content = serialize_source_markdown(clean_name, clean_desc, body_text)

    # Save to disk
    save_source_file(abs_path, file_content)

    # Insert into database
    try:
        source_id = db.insert_source(
            name=clean_name,
            description=clean_desc,
            file_path=rel_path,
            user_id=user_id,
            conn=conn,
        )
    except Exception:
        # Roll back file creation on DB failure
        if abs_path.exists():
            try:
                abs_path.unlink()
            except OSError:
                pass
        raise

    return {
        "id": source_id,
        "name": clean_name,
        "description": clean_desc,
        "file_path": rel_path,
        "abs_path": abs_path,
    }
