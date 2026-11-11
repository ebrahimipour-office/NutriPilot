import logging
import re
from pathlib import Path
import yaml

logger = logging.getLogger("nutripilot")


def parse_front_matter(text: str) -> tuple[dict, str]:
    """
    Extracts front-matter YAML dictionary and body text from markdown.
    If no valid front-matter is present, returns ({}, text).
    Handles UTF-8 BOM prefix if present.
    """
    clean_text = text.lstrip("\ufeff")
    pattern = r"^---\s*\r?\n(.*?)\r?\n---\s*(?:\r?\n)?(.*)$"
    match = re.match(pattern, clean_text, re.DOTALL)
    if not match:
        return {}, text

    yaml_part, body = match.groups()
    try:
        data = yaml.safe_load(yaml_part)
        if isinstance(data, dict):
            return data, body
    except Exception:
        pass
    return {}, text


def read_front_matter(path: str | Path) -> dict:
    """Read front-matter YAML dictionary from a markdown file on disk."""
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        data, _ = parse_front_matter(content)
        return data
    except Exception as e:
        logger.warning("Failed to read front-matter from %s: %s", p, e)
        return {}


def serialize_source_markdown(name: str, description: str, body_text: str) -> str:
    """
    Produce markdown content with self-describing front-matter (name, description)
    without modifying the source body text.
    """
    front_matter, body = parse_front_matter(body_text)
    front_matter["name"] = name
    front_matter["description"] = description
    header = yaml.safe_dump(front_matter, allow_unicode=True, sort_keys=False)
    # Ensure separator after header
    if body and not body.startswith("\n") and not body.startswith("\r\n"):
        body_to_write = body
    else:
        body_to_write = body.lstrip("\r\n") if body else ""

    if body_to_write:
        return f"---\n{header}---\n{body_to_write}\n"
    return f"---\n{header}---\n"
