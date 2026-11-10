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
