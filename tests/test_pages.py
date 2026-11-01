import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    with TestClient(app, base_url="http://localhost:8005") as c:
        yield c


def test_root_redirect(client):
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/chats"


def test_chats_page(client):
    res = client.get("/chats")
    assert res.status_code == 200
    assert 'lang="fa"' in res.text
    assert 'dir="rtl"' in res.text
    assert "گفت‌وگوها" in res.text
    assert "/static/htmx.min.js" in res.text
    assert "/static/app.css" in res.text


def test_clients_page(client):
    res = client.get("/clients")
    assert res.status_code == 200
    assert 'lang="fa"' in res.text
    assert 'dir="rtl"' in res.text
    assert "مراجعان" in res.text


def test_settings_page(client):
    res = client.get("/settings")
    assert res.status_code == 200
    assert 'lang="fa"' in res.text
    assert 'dir="rtl"' in res.text
    assert "تنظیمات" in res.text


def test_static_files(client):
    res_js = client.get("/static/htmx.min.js")
    assert res_js.status_code == 200
    assert len(res_js.content) > 1000

    res_css = client.get("/static/app.css")
    assert res_css.status_code == 200
    assert "direction: rtl" in res_css.text
