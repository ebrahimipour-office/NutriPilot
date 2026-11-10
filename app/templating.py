from datetime import datetime
from markdown_it import MarkdownIt
from fastapi.templating import Jinja2Templates

from app import config

# markdown-it with HTML strictly disabled for XSS prevention (TD §2, §11.4)
md_parser = MarkdownIt("commonmark", {"html": False})


def render_markdown(text: str | None) -> str:
    """Safely render Markdown to HTML without allowing raw HTML tags."""
    if not text:
        return ""
    return md_parser.render(text)


def fmt_date(iso_str: str | None) -> str:
    """Format UTC ISO date to local Gregorian string (YYYY-MM-DD HH:MM)."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        local_dt = dt.astimezone()
        return local_dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(iso_str)


from jinja2 import Environment, FileSystemLoader, select_autoescape

env = Environment(
    loader=FileSystemLoader(str(config.TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)
templates = Jinja2Templates(env=env)
templates.env.filters["render_markdown"] = render_markdown
templates.env.filters["fmt_date"] = fmt_date
