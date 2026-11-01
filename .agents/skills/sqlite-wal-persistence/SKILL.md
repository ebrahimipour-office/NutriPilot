---
name: sqlite-wal-persistence
description: >-
  Patterns and recipes for NutriPilot's SQLite database layer and disk persistence:
  stdlib sqlite3, WAL mode, user_version migrations, soft delete cascades, and PyYAML front-matter.
---

# SQLite WAL & Soft-Delete Persistence

This skill governs database management and filesystem persistence in NutriPilot v1 without heavy ORM dependencies.

## 1. Connection Helper (`app/db.py`)

Always open fresh connections per request or background thread using a context manager:
```python
import sqlite3
from contextlib import contextmanager
from app.config import DB_PATH

@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
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
```

## 2. Migrations via `PRAGMA user_version`

Schema changes are tracked sequentially:
```python
MIGRATIONS = [
    # Migration 1: Full initial schema from TD §5
    """
    CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL);
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
    """
]

def run_migrations(conn):
    cur = conn.cursor()
    cur.execute("PRAGMA user_version")
    current_version = cur.fetchone()[0]
    for idx, migration_sql in enumerate(MIGRATIONS[current_version:], start=current_version + 1):
        cur.executescript(migration_sql)
        cur.execute(f"PRAGMA user_version = {idx}")
```

## 3. Soft-Delete Rules & Cascades (TD §8.3)

1. **Rule**: Every query fetching active records must filter `deleted_at IS NULL`.
2. **Client Soft Delete Cascade**:
   In a single transaction, set `deleted_at` to the current UTC timestamp on the client, all its chats, and all its plans:
   ```python
   now = datetime.now(timezone.utc).isoformat()
   conn.execute("UPDATE clients SET deleted_at = ? WHERE id = ?", (now, client_id))
   conn.execute("UPDATE chats SET deleted_at = ? WHERE client_id = ?", (now, client_id))
   conn.execute("UPDATE plans SET deleted_at = ? WHERE client_id = ?", (now, client_id))
   ```
3. **Chat Soft Delete Cascade**:
   Set `deleted_at` on the chat and all plans belonging to that chat.

## 4. Markdown Plan Serialization with PyYAML (TD §6.2)

Plan files are written atomically (`tempfile` + `os.replace`):
```python
import os
import yaml
import tempfile

def write_plan_file(file_path: str, front_matter: dict, body_md: str):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    yaml_header = yaml.safe_dump(front_matter, allow_unicode=True, sort_keys=False)
    content = f"---\n{yaml_header}---\n{body_md.strip()}\n"
    
    dir_name = os.path.dirname(file_path)
    with tempfile.NamedTemporaryFile("w", dir=dir_name, encoding="utf-8", delete=False) as tf:
        tf.write(content)
        temp_name = tf.name
    os.replace(temp_name, file_path)
```
