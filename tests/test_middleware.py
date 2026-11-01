import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import config


@pytest.fixture
def client():
    # Use context manager to trigger lifespan
    with TestClient(app, base_url="http://localhost:8005") as c:
        yield c


def test_allowed_hosts(client):
    # Default Host via base_url is localhost:8005
    res = client.get("/ping")
    assert res.status_code == 200

    # 127.0.0.1:8005
    res = client.get("/ping", headers={"host": "127.0.0.1:8005"})
    assert res.status_code == 200

    # Case insensitivity
    res = client.get("/ping", headers={"host": "LOCALHOST:8005"})
    assert res.status_code == 200


def test_forbidden_hosts(client):
    # Foreign domain
    res = client.get("/ping", headers={"host": "evil.com"})
    assert res.status_code == 403
    assert "Forbidden Host" in res.text

    # Foreign domain on port 8005
    res = client.get("/ping", headers={"host": "evil.com:8005"})
    assert res.status_code == 403

    # Subdomain spoofing
    res = client.get("/ping", headers={"host": "localhost:8005.attacker.com"})
    assert res.status_code == 403

    # Empty host
    res = client.get("/ping", headers={"host": ""})
    assert res.status_code == 403


def test_post_origin_allowed(client):
    res = client.post("/ping", headers={"origin": "http://localhost:8005"})
    assert res.status_code == 200

    res = client.post("/ping", headers={"origin": "http://127.0.0.1:8005"})
    assert res.status_code == 200


def test_post_without_origin_allowed(client):
    # Form submission or curl without Origin/Referer is allowed
    res = client.post("/ping")
    assert res.status_code == 200


def test_post_forbidden_origin(client):
    res = client.post("/ping", headers={"origin": "http://evil.com"})
    assert res.status_code == 403
    assert "Forbidden Origin" in res.text

    # Origin null (sandboxed iframe / data uri)
    res = client.post("/ping", headers={"origin": "null"})
    assert res.status_code == 403


def test_post_referer_validation(client):
    # Valid referer
    res = client.post("/ping", headers={"referer": "http://localhost:8005/clients"})
    assert res.status_code == 200

    # Foreign referer
    res = client.post("/ping", headers={"referer": "http://evil.com/clients"})
    assert res.status_code == 403
    assert "Forbidden Referer" in res.text

    # Prefix bypass attempt (e.g. localhost:8005.evil.com)
    res = client.post("/ping", headers={"referer": "http://localhost:8005.evil.com/attack"})
    assert res.status_code == 403


def test_get_ignores_foreign_origin(client):
    # GET/HEAD/OPTIONS are safe methods; foreign Origin is not rejected
    res = client.get("/ping", headers={"origin": "http://evil.com"})
    assert res.status_code == 200
