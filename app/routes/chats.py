from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from app.templating import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def root_redirect():
    return RedirectResponse(url="/chats", status_code=303)


@router.get("/chats", response_class=HTMLResponse)
async def list_chats(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="chats.html",
        context={"active_nav": "chats"},
    )

