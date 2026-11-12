import sqlite3
import pytest
from app import db


def test_db_client_crud():
    # Create client
    cid = db.create_client(name="  علی تهرانی  ")
    assert cid > 0

    # Read client
    c = db.get_client(cid)
    assert c is not None
    assert c["name"] == "علی تهرانی"
    assert c["meta_json"] == "{}"
    assert c["deleted_at"] is None

    # Empty name validation
    with pytest.raises(ValueError):
        db.create_client(name="   ")

    # Update client name
    db.update_client_name(cid, "علی تهرانی نژاد")
    updated = db.get_client(cid)
    assert updated["name"] == "علی تهرانی نژاد"

    with pytest.raises(ValueError):
        db.update_client_name(cid, "   ")

    with pytest.raises(ValueError):
        db.update_client_name(99999, "کسی")


def test_db_client_soft_delete_and_user_scoping():
    with db.connect() as conn:
        conn.execute("INSERT INTO users (id, name, created_at) VALUES (2, 'user2', '2026-01-01T00:00:00Z')")

    cid1 = db.create_client(name="شاگرد ۱", user_id=1)
    cid2 = db.create_client(name="شاگرد ۲", user_id=2)

    # Scoped by user_id
    active_u1 = db.active_clients(user_id=1)
    assert any(c["id"] == cid1 for c in active_u1)
    assert not any(c["id"] == cid2 for c in active_u1)

    assert db.get_client(cid2, user_id=1) is None
    assert db.get_client(cid2, user_id=2) is not None

    # Soft-delete client 1 directly via SQL to verify helper respects deleted_at
    with db.connect() as conn:
        conn.execute("UPDATE clients SET deleted_at = '2026-01-01T00:00:00Z' WHERE id = ?", (cid1,))

    assert db.get_client(cid1, user_id=1) is None
    assert not any(c["id"] == cid1 for c in db.active_clients(user_id=1))


def test_client_endpoints_flow(client):
    # 1. List page empty state
    res = client.get("/clients")
    assert res.status_code == 200
    assert "هنوز هیچ مراجعی ثبت نشده است" in res.text

    # 2. New client form page
    res = client.get("/clients/new")
    assert res.status_code == 200
    assert 'name="name"' in res.text

    # 3. Create client validation error
    res_err = client.post("/clients", data={"name": "   "})
    assert res_err.status_code == 400

    # 4. Create client success
    res_create = client.post("/clients", data={"name": "مهدی کاظمی"}, follow_redirects=False)
    assert res_create.status_code == 303
    redirect_url = res_create.headers["location"]
    assert "/clients/" in redirect_url
    assert "created=1" in redirect_url

    # 5. Follow redirect to client detail
    res_detail = client.get(redirect_url)
    assert res_detail.status_code == 200
    assert "مهدی کاظمی" in res_detail.text
    assert "پرونده مراجع" in res_detail.text
    assert "گفت‌وگوها" in res_detail.text
    assert "برنامه‌های غذایی" in res_detail.text
    assert "هنوز گفت‌وگویی برای این مراجع ثبت نشده است" in res_detail.text
    assert "هنوز برنامه غذایی برای این مراجع ثبت نشده است" in res_detail.text

    # Extract ID
    cid = int(redirect_url.split("?")[0].split("/")[-1])

    # 6. Check list page now includes the client
    res_list = client.get("/clients")
    assert res_list.status_code == 200
    assert "مهدی کاظمی" in res_list.text
    assert f"/clients/{cid}" in res_list.text

    # 7. Edit client name
    res_edit = client.post(f"/clients/{cid}", data={"name": "مهدی کاظمی راد"}, follow_redirects=False)
    assert res_edit.status_code == 303
    assert res_edit.headers["location"] == f"/clients/{cid}?saved=1"

    res_after_edit = client.get(f"/clients/{cid}")
    assert res_after_edit.status_code == 200
    assert "مهدی کاظمی راد" in res_after_edit.text

    # 8. Edit name validation error
    res_bad_edit = client.post(f"/clients/{cid}", data={"name": " "})
    assert res_bad_edit.status_code == 400

    # 9. Non-existent client 404
    assert client.get("/clients/9999").status_code == 404
    assert client.post("/clients/9999", data={"name": "نام جدید"}).status_code == 404


def test_client_detail_with_chats_and_plans(client):
    cid = db.create_client(name="نرگس محمدی")

    with db.connect() as conn:
        conn.execute(
            "INSERT INTO chats (client_id, title, created_at) VALUES (?, ?, ?)",
            (cid, "مشاوره ابتدایی رژیم کتو", "2026-02-01T10:00:00Z"),
        )
        chat_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            """
            INSERT INTO plans (client_id, chat_id, version, title, file_path, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (cid, chat_id, 1, "برنامه کاهش وزن ۴ هفته‌ای", "data/plans/1/plan-1-v1.md", "draft", "2026-02-01T10:15:00Z"),
        )

    res = client.get(f"/clients/{cid}")
    assert res.status_code == 200
    assert "مشاوره ابتدایی رژیم کتو" in res.text
    assert "برنامه کاهش وزن ۴ هفته‌ای" in res.text
    assert "v1" in res.text
    assert "پیش‌نویس" in res.text
