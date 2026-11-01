from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.templating import templates

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
async def view_settings(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={"active_nav": "settings"},
    )

