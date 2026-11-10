from app import db, defaults


def test_view_settings(client):
    res = client.get("/settings")
    assert res.status_code == 200
    assert "تنظیمات سیستم" in res.text
    assert "ابزار هوش مصنوعی فعال" in res.text
    assert defaults.DEFAULT_CMD_CLAUDE in res.text
    assert defaults.DEFAULT_PLAN_DURATION in res.text
    assert "180" in res.text


def test_save_settings_full(client):
    payload = {
        "active_cli": "agy",
        "cmd_claude": "claude custom {prompt}",
        "cmd_agy": "agy custom {prompt}",
        "cmd_codex": "codex custom {prompt}",
        "system_prompt": "Custom system prompt for testing.",
        "default_plan_duration": "دو هفته",
        "ai_timeout_seconds": "300",
    }
    res = client.post("/settings", data=payload, follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/settings?saved=1"

    # Follow redirect and verify success banner
    follow_res = client.get(res.headers["location"])
    assert follow_res.status_code == 200
    assert "تغییرات با موفقیت ذخیره شدند" in follow_res.text

    # Verify persisted values in database
    settings = db.get_settings()
    assert settings["active_cli"] == "agy"
    assert settings["cmd_claude"] == "claude custom {prompt}"
    assert settings["cmd_agy"] == "agy custom {prompt}"
    assert settings["cmd_codex"] == "codex custom {prompt}"
    assert settings["system_prompt"] == "Custom system prompt for testing."
    assert settings["default_plan_duration"] == "دو هفته"
    assert settings["ai_timeout_seconds"] == "300"


def test_save_settings_validation_active_cli(client):
    payload = {
        "active_cli": "gpt4",
        "cmd_claude": defaults.DEFAULT_CMD_CLAUDE,
        "cmd_agy": defaults.DEFAULT_CMD_AGY,
        "cmd_codex": defaults.DEFAULT_CMD_CODEX,
        "system_prompt": defaults.DEFAULT_SYSTEM_PROMPT,
        "default_plan_duration": "یک هفته",
        "ai_timeout_seconds": "180",
    }
    res = client.post("/settings", data=payload)
    assert res.status_code == 400
    assert "active_cli must be one of" in res.text


def test_save_settings_validation_timeout(client):
    base_payload = {
        "active_cli": "claude",
        "cmd_claude": defaults.DEFAULT_CMD_CLAUDE,
        "cmd_agy": defaults.DEFAULT_CMD_AGY,
        "cmd_codex": defaults.DEFAULT_CMD_CODEX,
        "system_prompt": defaults.DEFAULT_SYSTEM_PROMPT,
        "default_plan_duration": "یک هفته",
    }

    # Zero timeout
    res = client.post("/settings", data={**base_payload, "ai_timeout_seconds": "0"})
    assert res.status_code == 400

    # Negative timeout
    res = client.post("/settings", data={**base_payload, "ai_timeout_seconds": "-10"})
    assert res.status_code == 400

    # Non-integer timeout
    res = client.post("/settings", data={**base_payload, "ai_timeout_seconds": "abc"})
    assert res.status_code == 400


def test_save_settings_validation_empty_fields(client):
    base_payload = {
        "active_cli": "claude",
        "cmd_claude": defaults.DEFAULT_CMD_CLAUDE,
        "cmd_agy": defaults.DEFAULT_CMD_AGY,
        "cmd_codex": defaults.DEFAULT_CMD_CODEX,
        "system_prompt": defaults.DEFAULT_SYSTEM_PROMPT,
        "default_plan_duration": "یک هفته",
        "ai_timeout_seconds": "180",
    }

    # Empty command template
    res = client.post("/settings", data={**base_payload, "cmd_claude": "   "})
    assert res.status_code == 400

    # Empty system prompt
    res = client.post("/settings", data={**base_payload, "system_prompt": "   "})
    assert res.status_code == 400


def test_reset_cmd_template_endpoint(client):
    # Set custom value
    db.update_setting("cmd_claude", "custom-claude-cmd")
    assert db.get_setting("cmd_claude") == "custom-claude-cmd"

    # Reset
    res = client.post("/settings/reset", data={"key": "cmd_claude"}, follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/settings?reset=cmd_claude"

    assert db.get_setting("cmd_claude") == defaults.DEFAULT_CMD_CLAUDE


def test_reset_system_prompt(client):
    db.update_setting("system_prompt", "Custom prompt")
    assert db.get_setting("system_prompt") == "Custom prompt"

    res = client.post("/settings/reset", data={"key": "system_prompt"}, follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/settings?reset=system_prompt"

    assert db.get_setting("system_prompt") == defaults.DEFAULT_SYSTEM_PROMPT


def test_reset_via_main_form_action(client):
    db.update_setting("cmd_agy", "custom-agy-cmd")
    assert db.get_setting("cmd_agy") == "custom-agy-cmd"

    res = client.post(
        "/settings",
        data={
            "action": "reset_cmd_agy",
            "active_cli": "claude",
            "cmd_claude": "c",
            "cmd_agy": "a",
            "cmd_codex": "x",
            "system_prompt": "s",
            "default_plan_duration": "d",
            "ai_timeout_seconds": "180",
        },
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert res.headers["location"] == "/settings?reset=cmd_agy"
    assert db.get_setting("cmd_agy") == defaults.DEFAULT_CMD_AGY


def test_reset_invalid_key(client):
    res = client.post("/settings/reset", data={"key": "non_existent_key"})
    assert res.status_code == 400
    assert "Unknown setting key to reset" in res.text


def test_modular_cli_and_prompt_endpoints(client):
    # Test POST /settings/cli
    res_cli = client.post(
        "/settings/cli",
        data={"active_cli": "codex", "ai_timeout_seconds": "240"},
        follow_redirects=False,
    )
    assert res_cli.status_code == 303
    assert db.get_setting("active_cli") == "codex"
    assert db.get_setting("ai_timeout_seconds") == "240"

    # Test POST /settings/prompt
    res_prompt = client.post(
        "/settings/prompt",
        data={"system_prompt": "Updated system prompt", "default_plan_duration": "یک ماه"},
        follow_redirects=False,
    )
    assert res_prompt.status_code == 303
    assert db.get_setting("system_prompt") == "Updated system prompt"
    assert db.get_setting("default_plan_duration") == "یک ماه"
