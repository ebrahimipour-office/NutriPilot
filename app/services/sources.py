import logging
import os
import re
import secrets
import sqlite3
import tempfile
import unicodedata
from pathlib import Path

from app import config, db
from app.parsers import read_front_matter, serialize_source_markdown

logger = logging.getLogger("nutripilot")


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

    # Generate filename and path (guarantee no collision with existing disk files)
    slug = slugify(clean_name)
    for _ in range(100):
        short_id = secrets.token_hex(4)
        file_name = f"{slug}-{short_id}.md"
        rel_path = f"sources/{file_name}"
        abs_path = config.SOURCES_DIR / file_name
        if not abs_path.exists():
            break
    else:
        raise RuntimeError("Failed to generate unique filename for source")

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


def scan_and_register_sources(
    sources_dir: Path | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[int]:
    """
    Startup scan of data/sources/*.md:
    Registers every file whose relative path is not in sources at all
    (including soft-deleted rows) using front-matter name/description
    (fallback: filename / empty description + log warning).
    Soft-deleted sources must never re-register.
    """
    target_dir = sources_dir if sources_dir is not None else config.SOURCES_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    registered_ids: list[int] = []

    def _scan(c: sqlite3.Connection) -> list[int]:
        known_paths = db.get_all_source_file_paths(conn=c)
        md_files = sorted(target_dir.glob("*.md"))

        for file_path in md_files:
            if not file_path.is_file():
                continue

            rel_path = f"sources/{file_path.name}"
            if rel_path in known_paths:
                continue

            # Read front-matter
            fm = read_front_matter(file_path)
            raw_name = fm.get("name")
            raw_desc = fm.get("description")

            fallback_name = False
            fallback_desc = False

            if raw_name is not None and str(raw_name).strip():
                name = str(raw_name).strip()
            else:
                name = file_path.name
                fallback_name = True

            if raw_desc is not None and str(raw_desc).strip():
                description = str(raw_desc).strip()
            else:
                description = ""
                fallback_desc = True

            if fallback_name or fallback_desc:
                logger.warning(
                    "Startup scan: source '%s' registered with fallback metadata (name='%s', description='%s')",
                    rel_path,
                    name,
                    description,
                )
            else:
                logger.info(
                    "Startup scan: source '%s' registered from front-matter (name='%s')",
                    rel_path,
                    name,
                )

            new_id = db.insert_source(
                name=name,
                description=description,
                file_path=rel_path,
                enabled=1,
                conn=c,
            )
            known_paths.add(rel_path)
            registered_ids.append(new_id)

        return registered_ids

    if conn is not None:
        return _scan(conn)
    with db.connect() as c:
        return _scan(c)

