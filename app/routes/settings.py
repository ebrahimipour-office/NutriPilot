from typing import Annotated
from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from app import db, defaults
from app.templating import templates

router = APIRouter()

ALLOWED_CLIS = {"claude", "agy", "codex"}


def _validate_timeout(timeout_str: str) -> int:
    try:
        val = int(timeout_str.strip())
        if val <= 0:
            raise ValueError()
        return val
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ai_timeout_seconds must be a positive integer",
        )


def _validate_active_cli(cli: str) -> str:
    cleaned = cli.strip()
    if cleaned not in ALLOWED_CLIS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"active_cli must be one of {sorted(ALLOWED_CLIS)}",
        )
    return cleaned


@router.get("/settings", response_class=HTMLResponse)
async def view_settings(request: Request):
    current_settings = db.get_settings()
    saved = request.query_params.get("saved") == "1"
    reset_key = request.query_params.get("reset")

    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "active_nav": "settings",
            "settings": current_settings,
            "saved": saved,
            "reset_key": reset_key,
        },
    )


@router.post("/settings", response_class=RedirectResponse)
async def save_settings(
    active_cli: Annotated[str, Form()] = "claude",
    cmd_claude: Annotated[str, Form()] = "",
    cmd_agy: Annotated[str, Form()] = "",
    cmd_codex: Annotated[str, Form()] = "",
    system_prompt: Annotated[str, Form()] = "",
    default_plan_duration: Annotated[str, Form()] = "یک هفته",
    ai_timeout_seconds: Annotated[str, Form()] = "180",
    action: Annotated[str | None, Form()] = None,
    reset_key: Annotated[str | None, Form()] = None,
):
    key_to_reset = reset_key
    if not key_to_reset and action and action.startswith("reset_"):
        key_to_reset = action.removeprefix("reset_")

    if key_to_reset:
        if key_to_reset not in defaults.DEFAULT_SETTINGS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown setting key to reset: {key_to_reset}",
            )
        db.update_setting(key_to_reset, defaults.DEFAULT_SETTINGS[key_to_reset])
        return RedirectResponse(
            url=f"/settings?reset={key_to_reset}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    cli = _validate_active_cli(active_cli)
    timeout = _validate_timeout(ai_timeout_seconds)

    if not cmd_claude.strip() or not cmd_agy.strip() or not cmd_codex.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Command templates cannot be empty",
        )

    if not system_prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="system_prompt cannot be empty",
        )

    db.update_settings({
        "active_cli": cli,
        "cmd_claude": cmd_claude.strip(),
        "cmd_agy": cmd_agy.strip(),
        "cmd_codex": cmd_codex.strip(),
        "system_prompt": system_prompt.strip(),
        "default_plan_duration": default_plan_duration.strip() or "یک هفته",
        "ai_timeout_seconds": str(timeout),
    })

    return RedirectResponse(
        url="/settings?saved=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/settings/reset", response_class=RedirectResponse)
async def reset_setting(key: Annotated[str, Form()]):
    key_clean = key.strip()
    if key_clean not in defaults.DEFAULT_SETTINGS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown setting key to reset: {key_clean}",
        )
    db.update_setting(key_clean, defaults.DEFAULT_SETTINGS[key_clean])
    return RedirectResponse(
        url=f"/settings?reset={key_clean}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/settings/cli", response_class=RedirectResponse)
async def update_cli_settings(
    active_cli: Annotated[str | None, Form()] = None,
    cmd_claude: Annotated[str | None, Form()] = None,
    cmd_agy: Annotated[str | None, Form()] = None,
    cmd_codex: Annotated[str | None, Form()] = None,
    ai_timeout_seconds: Annotated[str | None, Form()] = None,
):
    updates = {}
    if active_cli is not None:
        updates["active_cli"] = _validate_active_cli(active_cli)
    if ai_timeout_seconds is not None:
        updates["ai_timeout_seconds"] = str(_validate_timeout(ai_timeout_seconds))
    if cmd_claude is not None:
        if not cmd_claude.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cmd_claude cannot be empty")
        updates["cmd_claude"] = cmd_claude.strip()
    if cmd_agy is not None:
        if not cmd_agy.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cmd_agy cannot be empty")
        updates["cmd_agy"] = cmd_agy.strip()
    if cmd_codex is not None:
        if not cmd_codex.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cmd_codex cannot be empty")
        updates["cmd_codex"] = cmd_codex.strip()

    if updates:
        db.update_settings(updates)

    return RedirectResponse(url="/settings?saved=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/prompt", response_class=RedirectResponse)
async def update_prompt_settings(
    system_prompt: Annotated[str | None, Form()] = None,
    default_plan_duration: Annotated[str | None, Form()] = None,
):
    updates = {}
    if system_prompt is not None:
        if not system_prompt.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="system_prompt cannot be empty")
        updates["system_prompt"] = system_prompt.strip()
    if default_plan_duration is not None:
        updates["default_plan_duration"] = default_plan_duration.strip()

    if updates:
        db.update_settings(updates)

    return RedirectResponse(url="/settings?saved=1", status_code=status.HTTP_303_SEE_OTHER)


