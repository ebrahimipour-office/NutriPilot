import pytest
from app import db


def test_validate_meta_key():
    assert db.validate_meta_key("age") == "age"
    assert db.validate_meta_key("target_weight") == "target_weight"
    assert db.validate_meta_key("diet_goal_123") == "diet_goal_123"
    assert db.validate_meta_key("  daily_calories  ") == "daily_calories"

    # Invalid patterns
    with pytest.raises(ValueError):
        db.validate_meta_key("")
    with pytest.raises(ValueError):
        db.validate_meta_key("   ")
    with pytest.raises(ValueError):
        db.validate_meta_key("TargetWeight")
    with pytest.raises(ValueError):
        db.validate_meta_key("target-weight")
    with pytest.raises(ValueError):
        db.validate_meta_key("target weight")
    with pytest.raises(ValueError):
        db.validate_meta_key("weight@kg")
    with pytest.raises(ValueError):
        db.validate_meta_key("وزن")


def test_meta_fields_db_crud_and_ordering():
    # 1. Add fields with auto sort_order
    id1 = db.add_meta_field("age", "سن")
    id2 = db.add_meta_field("target_weight", "وزن هدف")
    id3 = db.add_meta_field("allergies", "حساسیت‌ها")

    fields = db.active_meta_fields()
    assert len(fields) == 3
    assert [f["key"] for f in fields] == ["age", "target_weight", "allergies"]
    assert [f["sort_order"] for f in fields] == [0, 1, 2]

    # 2. Reject duplicate live key
    with pytest.raises(ValueError, match="already exists"):
        db.add_meta_field("age", "سن جدید")

    # 3. Edit label
    db.update_meta_field_label(id1, "سن به سال")
    f1 = db.get_meta_field(id1)
    assert f1["label"] == "سن به سال"

    # Empty label rejected
    with pytest.raises(ValueError, match="Label cannot be empty"):
        db.update_meta_field_label(id1, "   ")

    # 4. Soft delete
    db.soft_delete_meta_field(id2)
    active = db.active_meta_fields()
    assert len(active) == 2
    assert [f["key"] for f in active] == ["age", "allergies"]

    # Verify row is physically preserved on disk in SQLite
    with db.connect() as conn:
        deleted_row = conn.execute("SELECT * FROM meta_fields WHERE id = ?", (id2,)).fetchone()
        assert deleted_row is not None
        assert deleted_row["deleted_at"] is not None
        assert deleted_row["key"] == "target_weight"

    # Soft deleting an already-deleted field raises error
    with pytest.raises(ValueError, match="not found or already deleted"):
        db.soft_delete_meta_field(id2)

    # 5. Re-adding a key after soft delete MUST work
    id2_new = db.add_meta_field("target_weight", "وزن هدف مجدد")
    assert id2_new != id2
    active_after_readd = db.active_meta_fields()
    assert len(active_after_readd) == 3
    assert [f["key"] for f in active_after_readd] == ["age", "allergies", "target_weight"]

    # Both old (soft-deleted) and new (live) rows exist in the raw table
    with db.connect() as conn:
        all_target_weights = conn.execute(
            "SELECT id, key, deleted_at FROM meta_fields WHERE key = 'target_weight' ORDER BY id ASC"
        ).fetchall()
        assert len(all_target_weights) == 2
        assert all_target_weights[0]["deleted_at"] is not None
        assert all_target_weights[1]["deleted_at"] is None


def test_meta_fields_reorder_and_move():
    id1 = db.add_meta_field("f1", "فیلد یک")
    id2 = db.add_meta_field("f2", "فیلد دو")
    id3 = db.add_meta_field("f3", "فیلد سه")

    # Move f2 up
    db.move_meta_field(id2, "up")
    fields = db.active_meta_fields()
    assert [f["id"] for f in fields] == [id2, id1, id3]
    assert [f["sort_order"] for f in fields] == [0, 1, 2]

    # Move top item up (no-op, safe)
    db.move_meta_field(id2, "up")
    fields = db.active_meta_fields()
    assert [f["id"] for f in fields] == [id2, id1, id3]

    # Move bottom item down (no-op, safe)
    db.move_meta_field(id3, "down")
    fields = db.active_meta_fields()
    assert [f["id"] for f in fields] == [id2, id1, id3]

    # Move f2 down
    db.move_meta_field(id2, "down")
    fields = db.active_meta_fields()
    assert [f["id"] for f in fields] == [id1, id2, id3]

    # Explicit reorder
    db.reorder_meta_fields([id3, id2, id1])
    fields = db.active_meta_fields()
    assert [f["id"] for f in fields] == [id3, id2, id1]
    assert [f["sort_order"] for f in fields] == [0, 1, 2]


def test_meta_fields_http_endpoints(client):
    # 1. GET /settings shows empty state or section
    res = client.get("/settings")
    assert res.status_code == 200
    assert "مشخصات شاگرد و کلیدهای متا" in res.text

    # 2. Add meta field
    res_add = client.post(
        "/settings/meta-fields",
        data={"key": "daily_water", "label": "میزان آب مصرفی"},
        follow_redirects=False,
    )
    assert res_add.status_code == 303
    assert res_add.headers["location"] == "/settings?meta_saved=1"

    # Follow redirect and check table
    res_view = client.get(res_add.headers["location"])
    assert res_view.status_code == 200
    assert "daily_water" in res_view.text
    assert "میزان آب مصرفی" in res_view.text
    assert "فیلد متا با موفقیت ذخیره شد" in res_view.text

    # 3. Add duplicate key via HTTP -> 400 Bad Request
    res_dup = client.post(
        "/settings/meta-fields",
        data={"key": "daily_water", "label": "آب مجدد"},
    )
    assert res_dup.status_code == 400
    assert "already exists" in res_dup.text

    # 4. Add invalid key via HTTP -> 400 Bad Request
    res_inv = client.post(
        "/settings/meta-fields",
        data={"key": "Daily-Water!", "label": "آب"},
    )
    assert res_inv.status_code == 400
    assert "must match [a-z0-9_]+" in res_inv.text

    # 5. Add second field
    client.post(
        "/settings/meta-fields",
        data={"key": "sleep_hours", "label": "ساعات خواب"},
    )

    fields = db.active_meta_fields()
    f1, f2 = fields[0], fields[1]
    assert f1["key"] == "daily_water"
    assert f2["key"] == "sleep_hours"

    # 6. Edit label
    res_edit = client.post(
        f"/settings/meta-fields/{f1['id']}/edit",
        data={"label": "مصرف آب روزانه (لیتر)"},
        follow_redirects=False,
    )
    assert res_edit.status_code == 303
    assert db.get_meta_field(f1["id"])["label"] == "مصرف آب روزانه (لیتر)"

    # 7. Move order
    res_move = client.post(
        f"/settings/meta-fields/{f2['id']}/move",
        data={"direction": "up"},
        follow_redirects=False,
    )
    assert res_move.status_code == 303
    fields_after_move = db.active_meta_fields()
    assert fields_after_move[0]["id"] == f2["id"]
    assert fields_after_move[1]["id"] == f1["id"]

    # 8. Reorder endpoint with order string
    res_reorder = client.post(
        "/settings/meta-fields/reorder",
        data={"order": f"{f1['id']},{f2['id']}"},
        follow_redirects=False,
    )
    assert res_reorder.status_code == 303
    fields_after_reorder = db.active_meta_fields()
    assert fields_after_reorder[0]["id"] == f1["id"]

    # 9. Soft delete via HTTP
    res_del = client.post(
        f"/settings/meta-fields/{f1['id']}/delete",
        follow_redirects=False,
    )
    assert res_del.status_code == 303
    assert res_del.headers["location"] == "/settings?meta_deleted=1"

    res_view2 = client.get(res_del.headers["location"])
    assert res_view2.status_code == 200
    assert "فیلد متا حذف گردید" in res_view2.text
    active_keys = [f["key"] for f in db.active_meta_fields()]
    assert "daily_water" not in active_keys

    # 10. Re-add the soft-deleted key via HTTP -> succeeds
    res_readd = client.post(
        "/settings/meta-fields",
        data={"key": "daily_water", "label": "مصرف آب مجدد"},
        follow_redirects=False,
    )
    assert res_readd.status_code == 303
    active_keys_after = [f["key"] for f in db.active_meta_fields()]
    assert "daily_water" in active_keys_after
