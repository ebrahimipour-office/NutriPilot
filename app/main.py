import logging
from logging.handlers import RotatingFileHandler
from contextlib import asynccontextmanager
from urllib.parse import urlparse
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app import config
from app import db
from app.routes import chats, clients, settings

logger = logging.getLogger("nutripilot")


def setup_logging() -> None:
    """Setup rotating file logger (data/app.log, ~1 MB x 3) and console logger."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Avoid duplicate handlers on re-initialization
    if not any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers):
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        file_handler = RotatingFileHandler(
            config.LOG_PATH,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)


class SecurityGuardMiddleware(BaseHTTPMiddleware):
    """Enforces Host validation and Origin/Referer CSRF protection (TD §11.1-11.2)."""

    async def dispatch(self, request: Request, call_next):
        allowed_hosts = {h.lower() for h in config.get_allowed_hosts()}
        allowed_origins = {o.lower() for o in config.get_allowed_origins()}

        # 1. Host header validation (blocks DNS rebinding)
        host = request.headers.get("host", "").strip().lower()
        if not host or host not in allowed_hosts:
            return Response("Forbidden Host", status_code=403)

        # 2. Origin/Referer check for state-changing requests (blocks CSRF)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            referer = request.headers.get("referer")

            if origin is not None:
                origin_clean = origin.strip().rstrip("/").lower()
                if origin_clean not in allowed_origins:
                    return Response("Forbidden Origin", status_code=403)
            elif referer:
                parsed = urlparse(referer.strip())
                ref_origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/").lower()
                if ref_origin not in allowed_origins:
                    return Response("Forbidden Referer", status_code=403)

        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for directory creation, logging setup, and DB initialization."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    config.PLANS_DIR.mkdir(parents=True, exist_ok=True)

    setup_logging()
    logger.info("NutriPilot starting up. Working directory: %s", config.DATA_DIR)

    db.init_db()
    logger.info("Database initialized and default settings verified.")

    yield

    logger.info("NutriPilot shutting down.")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(title="NutriPilot", lifespan=lifespan)
    app.add_middleware(SecurityGuardMiddleware)

    config.STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")

    # Health check endpoints
    @app.get("/ping")
    async def ping_get():
        return {"status": "ok"}

    @app.post("/ping")
    async def ping_post():
        return {"status": "ok"}

    # Page routes
    app.include_router(chats.router)
    app.include_router(clients.router)
    app.include_router(settings.router)

    return app


app = create_app()


