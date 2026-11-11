import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator
from app import config
from app import defaults

SCHEMA_V1 = """
CREATE TABLE users (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL
);

CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE meta_fields (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
  key TEXT NOT NULL,
  label TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  deleted_at TEXT
);
CREATE UNIQUE INDEX ux_meta_fields_key ON meta_fields(user_id, key) WHERE deleted_at IS NULL;

CREATE TABLE clients (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
  name TEXT NOT NULL,
  meta_json TEXT NOT NULL DEFAULT '{}',
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
  file_path TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('draft','approved')),
  approved_at TEXT,
  created_at TEXT NOT NULL, deleted_at TEXT
);

CREATE TABLE messages (
  id INTEGER PRIMARY KEY,
  chat_id INTEGER NOT NULL REFERENCES chats(id),
  role TEXT NOT NULL CHECK (role IN ('user','assistant')),
  content TEXT NOT NULL,
  is_error INTEGER NOT NULL DEFAULT 0,
  meta_proposal TEXT,
  meta_status TEXT CHECK (meta_status IN ('pending','saved','dismissed')),
  plan_id INTEGER REFERENCES plans(id),
  created_at TEXT NOT NULL
);

CREATE TABLE sources (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL DEFAULT 1 REFERENCES users(id),
  name TEXT NOT NULL, description TEXT NOT NULL,
  file_path TEXT NOT NULL UNIQUE,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, deleted_at TEXT
);

CREATE INDEX ix_chats_client ON chats(client_id);
CREATE INDEX ix_messages_chat ON messages(chat_id, id);
CREATE INDEX ix_plans_chat ON plans(chat_id, version);
CREATE INDEX ix_plans_client ON plans(client_id);

CREATE VIEW live_meta_fields AS SELECT * FROM meta_fields WHERE deleted_at IS NULL;
CREATE VIEW live_clients AS SELECT * FROM clients WHERE deleted_at IS NULL;
CREATE VIEW live_chats AS SELECT * FROM chats WHERE deleted_at IS NULL;
CREATE VIEW live_plans AS SELECT * FROM plans WHERE deleted_at IS NULL;
CREATE VIEW live_sources AS SELECT * FROM sources WHERE deleted_at IS NULL;
"""

MIGRATIONS: list[str] = [
    SCHEMA_V1,
]


@contextmanager
def connect(db_path: Path | str | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for SQLite database connection with WAL mode, foreign keys, and busy timeout."""
    target_path = Path(db_path) if db_path else config.DB_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(target_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_migrations(conn: sqlite3.Connection) -> None:
    """Run pending migrations tracked by PRAGMA user_version."""
    cur = conn.cursor()
    cur.execute("PRAGMA user_version")
    row = cur.fetchone()
    current_version = row[0] if row else 0

    for idx, migration_sql in enumerate(MIGRATIONS[current_version:], start=current_version + 1):
        cur.executescript(f"{migration_sql}\nPRAGMA user_version = {idx};\n")


def seed_defaults(conn: sqlite3.Connection) -> None:
    """Seed user 1 and default settings using INSERT OR IGNORE (never overwrites existing values)."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO users (id, name, created_at) VALUES (?, ?, ?)",
        (1, "admin", now),
    )
    for key, val in defaults.DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, val),
        )


def init_db(db_path: Path | str | None = None) -> None:
    """Initialize DB, apply any pending migrations, and seed defaults."""
    with connect(db_path) as conn:
        run_migrations(conn)
        seed_defaults(conn)


def current_user_id() -> int:
    """Returns the current user ID for v1 (default: 1)."""
    return 1


def get_settings(conn: sqlite3.Connection | None = None) -> dict[str, str]:
    """Retrieve all settings as a dictionary, with fallbacks to defaults."""
    result = dict(defaults.DEFAULT_SETTINGS)
    if conn is not None:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        for r in rows:
            result[r["key"]] = r["value"]
    else:
        with connect() as c:
            rows = c.execute("SELECT key, value FROM settings").fetchall()
            for r in rows:
                result[r["key"]] = r["value"]
    return result


def get_setting(key: str, default: str | None = None, conn: sqlite3.Connection | None = None) -> str:
    """Retrieve a single setting value by key."""
    if conn is not None:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is not None:
            return row["value"]
    else:
        with connect() as c:
            row = c.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            if row is not None:
                return row["value"]
    if default is not None:
        return default
    return defaults.DEFAULT_SETTINGS.get(key, "")


def update_setting(key: str, value: str, conn: sqlite3.Connection | None = None) -> None:
    """Update or insert a setting key-value pair."""
    if conn is not None:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
    else:
        with connect() as c:
            c.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )


def update_settings(items: dict[str, str], conn: sqlite3.Connection | None = None) -> None:
    """Update or insert multiple settings in a single transaction."""
    if conn is not None:
        for k, v in items.items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (k, v),
            )
    else:
        with connect() as c:
            for k, v in items.items():
                c.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (k, v),
                )


META_KEY_REGEX = re.compile(r"^[a-z0-9_]+$")


def validate_meta_key(key: str) -> str:
    """Validates that a meta field key matches [a-z0-9_]+."""
    cleaned = key.strip()
    if not META_KEY_REGEX.fullmatch(cleaned):
        raise ValueError("Meta field key must match [a-z0-9_]+")
    return cleaned


def active_meta_fields(
    conn: sqlite3.Connection | None = None,
    user_id: int | None = None,
) -> list[sqlite3.Row]:
    """Retrieve all active (non-deleted) meta fields for the user, ordered by sort_order."""
    uid = user_id if user_id is not None else current_user_id()
    query = """
        SELECT id, user_id, key, label, sort_order, deleted_at
        FROM meta_fields
        WHERE user_id = ? AND deleted_at IS NULL
        ORDER BY sort_order ASC, id ASC
    """
    if conn is not None:
        return conn.execute(query, (uid,)).fetchall()
    with connect() as c:
        return c.execute(query, (uid,)).fetchall()


def get_meta_field(
    field_id: int,
    user_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> sqlite3.Row | None:
    """Retrieve an active meta field by ID."""
    uid = user_id if user_id is not None else current_user_id()
    query = "SELECT * FROM meta_fields WHERE id = ? AND user_id = ? AND deleted_at IS NULL"
    if conn is not None:
        return conn.execute(query, (field_id, uid)).fetchone()
    with connect() as c:
        return c.execute(query, (field_id, uid)).fetchone()


def add_meta_field(
    key: str,
    label: str,
    sort_order: int | None = None,
    user_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Add a new meta field. Key must match [a-z0-9_]+ and be unique among live fields for the user."""
    clean_key = validate_meta_key(key)
    clean_label = label.strip()
    if not clean_label:
        raise ValueError("Label cannot be empty")
    uid = user_id if user_id is not None else current_user_id()

    def _execute(c: sqlite3.Connection) -> int:
        existing = c.execute(
            "SELECT id FROM meta_fields WHERE user_id = ? AND key = ? AND deleted_at IS NULL",
            (uid, clean_key),
        ).fetchone()
        if existing:
            raise ValueError(f"Meta field with key '{clean_key}' already exists.")

        assigned_order = sort_order
        if assigned_order is None:
            cur = c.execute(
                "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM meta_fields WHERE user_id = ? AND deleted_at IS NULL",
                (uid,),
            )
            assigned_order = cur.fetchone()[0]

        try:
            cur = c.execute(
                "INSERT INTO meta_fields (user_id, key, label, sort_order) VALUES (?, ?, ?, ?)",
                (uid, clean_key, clean_label, assigned_order),
            )
            return cur.lastrowid
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Meta field with key '{clean_key}' already exists.") from e

    if conn is not None:
        return _execute(conn)
    with connect() as c:
        return _execute(c)


def update_meta_field_label(
    field_id: int,
    label: str,
    user_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Update the label of an active meta field."""
    clean_label = label.strip()
    if not clean_label:
        raise ValueError("Label cannot be empty")
    uid = user_id if user_id is not None else current_user_id()

    def _execute(c: sqlite3.Connection) -> None:
        res = c.execute(
            "UPDATE meta_fields SET label = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (clean_label, field_id, uid),
        )
        if res.rowcount == 0:
            raise ValueError(f"Meta field with id {field_id} not found or deleted")

    if conn is not None:
        _execute(conn)
    else:
        with connect() as c:
            _execute(c)


def soft_delete_meta_field(
    field_id: int,
    user_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Soft delete a meta field by setting its deleted_at timestamp. Never deletes physically."""
    uid = user_id if user_id is not None else current_user_id()
    now = datetime.now(timezone.utc).isoformat()

    def _execute(c: sqlite3.Connection) -> None:
        res = c.execute(
            "UPDATE meta_fields SET deleted_at = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (now, field_id, uid),
        )
        if res.rowcount == 0:
            raise ValueError(f"Meta field with id {field_id} not found or already deleted")

    if conn is not None:
        _execute(conn)
    else:
        with connect() as c:
            _execute(c)


def reorder_meta_fields(
    field_ids: list[int],
    user_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Update sort_order of active meta fields to match the provided list of IDs."""
    uid = user_id if user_id is not None else current_user_id()

    def _execute(c: sqlite3.Connection) -> None:
        for order, fid in enumerate(field_ids):
            c.execute(
                "UPDATE meta_fields SET sort_order = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                (order, fid, uid),
            )

    if conn is not None:
        _execute(conn)
    else:
        with connect() as c:
            _execute(c)


def move_meta_field(
    field_id: int,
    direction: str,
    user_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Move an active meta field 'up' or 'down' relative to its current sorted position."""
    if direction not in ("up", "down"):
        raise ValueError("Direction must be 'up' or 'down'")
    uid = user_id if user_id is not None else current_user_id()

    def _execute(c: sqlite3.Connection) -> None:
        fields = c.execute(
            "SELECT id, sort_order FROM meta_fields WHERE user_id = ? AND deleted_at IS NULL ORDER BY sort_order ASC, id ASC",
            (uid,),
        ).fetchall()
        ids = [f["id"] for f in fields]
        if field_id not in ids:
            raise ValueError(f"Meta field with id {field_id} not found")

        idx = ids.index(field_id)
        if direction == "up" and idx > 0:
            ids[idx], ids[idx - 1] = ids[idx - 1], ids[idx]
        elif direction == "down" and idx < len(ids) - 1:
            ids[idx], ids[idx + 1] = ids[idx + 1], ids[idx]

        for order, fid in enumerate(ids):
            c.execute(
                "UPDATE meta_fields SET sort_order = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
                (order, fid, uid),
            )

    if conn is not None:
        _execute(conn)
    else:
        with connect() as c:
            _execute(c)


def insert_source(
    name: str,
    description: str,
    file_path: str,
    enabled: int = 1,
    user_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Insert a new source record into the database."""
    uid = user_id if user_id is not None else current_user_id()
    now = datetime.now(timezone.utc).isoformat()

    def _execute(c: sqlite3.Connection) -> int:
        cur = c.execute(
            """
            INSERT INTO sources (user_id, name, description, file_path, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (uid, name.strip(), description.strip(), file_path.strip(), enabled, now),
        )
        return cur.lastrowid

    if conn is not None:
        return _execute(conn)
    with connect() as c:
        return _execute(c)


def get_source(
    source_id: int,
    user_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> sqlite3.Row | None:
    """Retrieve an active source by ID."""
    uid = user_id if user_id is not None else current_user_id()

    def _execute(c: sqlite3.Connection) -> sqlite3.Row | None:
        return c.execute(
            "SELECT * FROM sources WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (source_id, uid),
        ).fetchone()

    if conn is not None:
        return _execute(conn)
    with connect() as c:
        return _execute(c)


def active_sources(
    user_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[sqlite3.Row]:
    """Retrieve all active sources for the user, ordered by created_at DESC, id DESC."""
    uid = user_id if user_id is not None else current_user_id()

    def _execute(c: sqlite3.Connection) -> list[sqlite3.Row]:
        return c.execute(
            "SELECT * FROM sources WHERE user_id = ? AND deleted_at IS NULL ORDER BY created_at DESC, id DESC",
            (uid,),
        ).fetchall()

    if conn is not None:
        return _execute(conn)
    with connect() as c:
        return _execute(c)


def update_source(
    source_id: int,
    name: str,
    description: str,
    user_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Update name and description of an active source."""
    clean_name = name.strip() if name else ""
    if not clean_name:
        raise ValueError("Source name is required")
    clean_desc = description.strip() if description else ""
    uid = user_id if user_id is not None else current_user_id()

    def _execute(c: sqlite3.Connection) -> None:
        res = c.execute(
            "UPDATE sources SET name = ?, description = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (clean_name, clean_desc, source_id, uid),
        )
        if res.rowcount == 0:
            raise ValueError(f"Source with id {source_id} not found or deleted")

    if conn is not None:
        _execute(conn)
    else:
        with connect() as c:
            _execute(c)


def toggle_source_enabled(
    source_id: int,
    enabled: int | None = None,
    user_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> int:
    """Toggle or set the enabled flag of an active source (0 or 1)."""
    uid = user_id if user_id is not None else current_user_id()

    def _execute(c: sqlite3.Connection) -> int:
        row = c.execute(
            "SELECT enabled FROM sources WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (source_id, uid),
        ).fetchone()
        if row is None:
            raise ValueError(f"Source with id {source_id} not found or deleted")

        new_val = enabled if enabled is not None else (0 if row["enabled"] else 1)
        if new_val not in (0, 1):
            raise ValueError("enabled must be 0 or 1")

        c.execute(
            "UPDATE sources SET enabled = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (new_val, source_id, uid),
        )
        return new_val

    if conn is not None:
        return _execute(conn)
    with connect() as c:
        return _execute(c)


def soft_delete_source(
    source_id: int,
    user_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Soft delete a source by setting its deleted_at timestamp. Never deletes physically."""
    uid = user_id if user_id is not None else current_user_id()
    now = datetime.now(timezone.utc).isoformat()

    def _execute(c: sqlite3.Connection) -> None:
        res = c.execute(
            "UPDATE sources SET deleted_at = ? WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (now, source_id, uid),
        )
        if res.rowcount == 0:
            raise ValueError(f"Source with id {source_id} not found or already deleted")

    if conn is not None:
        _execute(conn)
    else:
        with connect() as c:
            _execute(c)


def get_all_source_file_paths(
    conn: sqlite3.Connection | None = None,
) -> set[str]:
    """Retrieve all file paths in sources table, INCLUDING soft-deleted rows."""
    def _execute(c: sqlite3.Connection) -> set[str]:
        rows = c.execute("SELECT file_path FROM sources").fetchall()
        return {r["file_path"] for r in rows}

    if conn is not None:
        return _execute(conn)
    with connect() as c:
        return _execute(c)


