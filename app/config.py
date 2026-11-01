import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data")).resolve()

SOURCES_DIR = DATA_DIR / "sources"
PLANS_DIR = DATA_DIR / "plans"
DB_PATH = DATA_DIR / "app.db"
LOG_PATH = DATA_DIR / "app.log"

TEMPLATES_DIR = BASE_DIR / "app" / "templates"
STATIC_DIR = BASE_DIR / "app" / "static"


def configure_data_dir(new_data_dir: Path | str) -> None:
    """Update DATA_DIR and derived paths dynamically (used for isolated test environments)."""
    global DATA_DIR, SOURCES_DIR, PLANS_DIR, DB_PATH, LOG_PATH
    DATA_DIR = Path(new_data_dir).resolve()
    SOURCES_DIR = DATA_DIR / "sources"
    PLANS_DIR = DATA_DIR / "plans"
    DB_PATH = DATA_DIR / "app.db"
    LOG_PATH = DATA_DIR / "app.log"


# Caps and Limits (TD §7.2, §8.4)
HISTORY_MAX_MESSAGES: int = 30
HISTORY_MAX_CHARS: int = 24000
EXAMPLES_CAP: int = 50
UPLOAD_MAX_BYTES: int = 1_000_000

# Server network settings
HOST: str = os.getenv("APP_HOST", "127.0.0.1")
PORT: int = int(os.getenv("APP_PORT", "8005"))

# Allowed Hosts and Origins for SecurityGuardMiddleware (TD §11.2)
def get_allowed_hosts() -> set[str]:
    raw = os.getenv("ALLOWED_HOSTS")
    if raw:
        return {h.strip().lower() for h in raw.split(",") if h.strip()}
    return {
        f"localhost:{PORT}".lower(),
        f"127.0.0.1:{PORT}".lower(),
        "localhost",
        "127.0.0.1",
        "testserver",
    }

def get_allowed_origins() -> set[str]:
    raw = os.getenv("ALLOWED_ORIGINS")
    if raw:
        return {o.strip().rstrip("/").lower() for o in raw.split(",") if o.strip()}
    return {
        f"http://localhost:{PORT}".lower(),
        f"http://127.0.0.1:{PORT}".lower(),
        "http://testserver",
    }

ALLOWED_HOSTS: set[str] = get_allowed_hosts()
ALLOWED_ORIGINS: set[str] = get_allowed_origins()

