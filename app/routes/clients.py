from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.templating import templates

router = APIRouter()


@router.get("/clients", response_class=HTMLResponse)
async def list_clients(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="clients.html",
        context={"active_nav": "clients"},
    )

