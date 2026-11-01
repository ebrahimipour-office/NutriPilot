import pytest
from fastapi.testclient import TestClient
from app import config
from app import db
from app.main import app


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Isolate DATA_DIR to a temporary folder for every test."""
    temp_data = tmp_path / "data"
    temp_data.mkdir(parents=True, exist_ok=True)
    (temp_data / "sources").mkdir(parents=True, exist_ok=True)
    (temp_data / "plans").mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("DATA_DIR", str(temp_data))
    config.configure_data_dir(temp_data)

    # Initialize DB and defaults in the temp directory
    db.init_db(config.DB_PATH)
    yield temp_data


@pytest.fixture
def client():
    """TestClient fixture with base_url http://localhost:8005."""
    with TestClient(app, base_url="http://localhost:8005") as c:
        yield c
