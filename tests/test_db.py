import sqlite3
import pytest
from app import db


def test_db_init_and_migrations(tmp_path):
    db_file = tmp_path / "test.db"
    with db.connect(db_file) as conn:
        db.run_migrations(conn)

    # Check PRAGMAs
    with db.connect(db_file) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode")
        assert cur.fetchone()[0].lower() == "wal"

        cur.execute("PRAGMA foreign_keys")
        assert cur.fetchone()[0] == 1

        cur.execute("PRAGMA user_version")
        assert cur.fetchone()[0] == 1

        # Check all 7 tables exist
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}
        expected_tables = {
            "users",
            "settings",
            "meta_fields",
            "clients",
            "chats",
            "plans",
            "messages",
            "sources",
        }
        assert expected_tables.issubset(tables)

        # Check live views exist
        cur.execute("SELECT name FROM sqlite_master WHERE type='view'")
        views = {row[0] for row in cur.fetchall()}
        expected_views = {
            "live_meta_fields",
            "live_clients",
            "live_chats",
            "live_plans",
            "live_sources",
        }
        assert expected_views.issubset(views)


def test_migrations_idempotency(tmp_path):
    db_file = tmp_path / "test.db"
    db.init_db(db_file)
    # Calling init_db again should not fail and user_version should stay 1
    db.init_db(db_file)
    with db.connect(db_file) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA user_version")
        assert cur.fetchone()[0] == 1


def test_meta_fields_unique_partial_index(tmp_path):
    db_file = tmp_path / "test.db"
    db.init_db(db_file)

    with db.connect(db_file) as conn:
        conn.execute("INSERT INTO users (id, name, created_at) VALUES (1, 'admin', '2026-11-02T00:00:00Z')")
        conn.execute(
            "INSERT INTO meta_fields (user_id, key, label, sort_order) VALUES (1, 'weight_kg', 'وزن', 1)"
        )
        # Duplicate live key for same user should fail
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO meta_fields (user_id, key, label, sort_order) VALUES (1, 'weight_kg', 'وزن دوباره', 2)"
            )

        # Soft delete the first row
        conn.execute("UPDATE meta_fields SET deleted_at = '2026-11-02T01:00:00Z' WHERE key = 'weight_kg'")

        # Now re-adding the same key should succeed
        conn.execute(
            "INSERT INTO meta_fields (user_id, key, label, sort_order) VALUES (1, 'weight_kg', 'وزن جدید', 3)"
        )


def test_sources_unique_file_path(tmp_path):
    db_file = tmp_path / "test.db"
    db.init_db(db_file)

    with db.connect(db_file) as conn:
        conn.execute("INSERT INTO users (id, name, created_at) VALUES (1, 'admin', '2026-11-02T00:00:00Z')")
        conn.execute(
            "INSERT INTO sources (user_id, name, description, file_path, created_at, deleted_at) VALUES (1, 'Src', 'Desc', 'sources/test.md', '2026-11-02T00:00:00Z', '2026-11-02T01:00:00Z')"
        )
        # Even though soft-deleted, UNIQUE(file_path) must be violated
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sources (user_id, name, description, file_path, created_at) VALUES (1, 'Src2', 'Desc2', 'sources/test.md', '2026-11-02T00:00:00Z')"
            )


def test_live_views_filter_soft_deleted(tmp_path):
    db_file = tmp_path / "test.db"
    db.init_db(db_file)

    with db.connect(db_file) as conn:
        conn.execute("INSERT INTO users (id, name, created_at) VALUES (1, 'admin', '2026-11-02T00:00:00Z')")
        conn.execute("INSERT INTO clients (id, user_id, name, created_at) VALUES (1, 1, 'Client Active', '2026-11-02T00:00:00Z')")
        conn.execute("INSERT INTO clients (id, user_id, name, created_at, deleted_at) VALUES (2, 1, 'Client Deleted', '2026-11-02T00:00:00Z', '2026-11-02T01:00:00Z')")

        cur = conn.cursor()
        cur.execute("SELECT id, name FROM live_clients")
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0]["id"] == 1
        assert rows[0]["name"] == "Client Active"


def test_check_constraints(tmp_path):
    db_file = tmp_path / "test.db"
    db.init_db(db_file)

    with db.connect(db_file) as conn:
        conn.execute("INSERT INTO users (id, name, created_at) VALUES (1, 'admin', '2026-11-02T00:00:00Z')")
        conn.execute("INSERT INTO clients (id, user_id, name, created_at) VALUES (1, 1, 'Client', '2026-11-02T00:00:00Z')")
        conn.execute("INSERT INTO chats (id, client_id, title, created_at) VALUES (1, 1, 'Chat', '2026-11-02T00:00:00Z')")

        # Invalid plan status
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO plans (client_id, chat_id, version, title, file_path, status, created_at) VALUES (1, 1, 1, 'P', 'f.md', 'invalid_status', '2026-11-02T00:00:00Z')"
            )

        # Invalid message role
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO messages (chat_id, role, content, created_at) VALUES (1, 'system', 'content', '2026-11-02T00:00:00Z')"
            )

        # Invalid meta_status
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO messages (chat_id, role, content, meta_status, created_at) VALUES (1, 'assistant', 'content', 'rejected', '2026-11-02T00:00:00Z')"
            )
