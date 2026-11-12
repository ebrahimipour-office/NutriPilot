from typing import Annotated
from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from app import db
from app.templating import templates

router = APIRouter()


@router.get("/clients", response_class=HTMLResponse)
async def list_clients(request: Request):
    clients = db.active_clients()
    created = request.query_params.get("created") == "1"
    updated = request.query_params.get("updated") == "1"
    deleted = request.query_params.get("deleted") == "1"

    return templates.TemplateResponse(
        request=request,
        name="clients.html",
        context={
            "active_nav": "clients",
            "clients": clients,
            "created": created,
            "updated": updated,
            "deleted": deleted,
        },
    )


@router.get("/clients/new", response_class=HTMLResponse)
async def new_client_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="client_new.html",
        context={"active_nav": "clients"},
    )


@router.post("/clients", response_class=RedirectResponse)
async def create_client_endpoint(
    name: Annotated[str, Form()],
):
    clean_name = name.strip() if name else ""
    if not clean_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client name cannot be empty",
        )
    client_id = db.create_client(clean_name)
    return RedirectResponse(
        url=f"/clients/{client_id}?created=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/clients/{client_id}", response_class=HTMLResponse)
async def view_client(client_id: int, request: Request):
    client = db.get_client(client_id)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    chats = db.get_client_chats(client_id)
    plans = db.get_client_plans(client_id)
    saved = request.query_params.get("saved") == "1"
    created = request.query_params.get("created") == "1"

    return templates.TemplateResponse(
        request=request,
        name="client_detail.html",
        context={
            "active_nav": "clients",
            "client": client,
            "chats": chats,
            "plans": plans,
            "saved": saved,
            "created": created,
        },
    )


@router.post("/clients/{client_id}", response_class=RedirectResponse)
async def edit_client_name_endpoint(
    client_id: int,
    name: Annotated[str, Form()],
):
    clean_name = name.strip() if name else ""
    if not clean_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client name cannot be empty",
        )
    client = db.get_client(client_id)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found",
        )
    db.update_client_name(client_id, clean_name)
    return RedirectResponse(
        url=f"/clients/{client_id}?saved=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/clients/{client_id}/edit", response_class=RedirectResponse)
async def edit_client_name_alias(
    client_id: int,
    name: Annotated[str, Form()],
):
    return await edit_client_name_endpoint(client_id=client_id, name=name)


