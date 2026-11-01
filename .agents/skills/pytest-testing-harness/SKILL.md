---
name: pytest-testing-harness
description: >-
  Testing patterns, TestClient fixtures, and fake AI CLI implementation for NutriPilot v1.
---

# Pytest Testing Harness & Fake CLI

This skill provides testing patterns and mock harnesses for validating NutriPilot v1.

## 1. Environment & Fixtures (`tests/conftest.py`)

Isolate tests using temporary directory overrides and FastAPI's `TestClient`:
```python
import os
import tempfile
import pytest
from starlette.testclient import TestClient

@pytest.fixture(autouse=True)
def test_env(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "sources").mkdir()
    (data_dir / "plans").mkdir()
    monkeypatch.setenv("NUTRIPILOT_DATA_DIR", str(data_dir))
    monkeypatch.setenv("NUTRIPILOT_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")

@pytest.fixture
def client():
    from app.main import app
    with TestClient(app, base_url="http://localhost:8005") as c:
        yield c
```

## 2. Fake AI CLI (`tests/fake_cli.py`)

Simulate AI CLI responses without calling real external binaries:
```python
import sys
import time
import os

mode = os.getenv("FAKE_CLI_MODE", "plain")

if mode == "plain":
    sys.stdout.write("سلام! من می‌توانم به شما در تنظیم برنامه غذایی کمک کنم.")
elif mode == "meta":
    sys.stdout.write("مشخصات ثبت شد.\n<meta>{\"height\": \"175\", \"weight\": \"72\"}</meta>")
elif mode == "plan":
    sys.stdout.write("برنامه غذایی:\n<plan>\n# برنامه کاهش وزن هفته اول\n- صبحانه: تخم‌مرغ و جو دوسر\n- ناهار: فیله مرغ و برنج کته\n</plan>")
elif mode == "malformed":
    sys.stdout.write("پاسخ با متای ناقص: <meta>{invalid json</meta>")
elif mode == "error":
    sys.stderr.write("Fatal AI CLI error: connection failed\n")
    sys.exit(1)
elif mode == "sleep":
    time.sleep(30)
```

## 3. Required Test Matrix (TD §13)

- **Parsers**: Block extraction, nested tags, malformed JSON, filter comparisons.
- **Prompt Builder**: Section order (1-7), history truncation, exclusion of error messages, exclusion of client names from example plans.
- **AI Runner**: Stdin piping, `{prompt}` substitution, non-zero exits, timeout kills, ANSI stripping.
- **Plan Lifecycle**: Draft overwrite, version increments, soft delete version preservation, approval freezing.
- **Cascade Deletes**: Client deletion soft-deletes chats and plans; chat deletion soft-deletes plans.
