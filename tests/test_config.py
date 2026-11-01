from app import config


def test_config_constants():
    assert config.HISTORY_MAX_MESSAGES == 30
    assert config.HISTORY_MAX_CHARS == 24000
    assert config.EXAMPLES_CAP == 50
    assert config.UPLOAD_MAX_BYTES == 1_000_000
    assert config.HOST == "127.0.0.1"
    assert config.PORT == 8005


def test_config_paths():
    assert config.BASE_DIR.exists()
    assert config.TEMPLATES_DIR.name == "templates"
    assert config.STATIC_DIR.name == "static"
    assert "localhost:8005" in config.ALLOWED_HOSTS or "localhost" in config.ALLOWED_HOSTS
