---
name: fastapi-htmx-persian
description: >-
  Patterns and recipes for NutriPilot's web layer: FastAPI, Jinja2 SSR, HTMX out-of-band updates,
  delayed polling, Persian RTL layout, and Host/Origin security middleware.
---

# FastAPI, HTMX & Persian RTL Web Architecture

This skill provides patterns for implementing NutriPilot's server-rendered web UI and security boundaries.

## 1. Security Middleware (TD §11)

In `app/main.py`, enforce strict Host and Origin validation:
```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class SecurityGuardMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_hosts: set[str], allowed_origins: set[str]):
        super().__init__(app)
        self.allowed_hosts = allowed_hosts
        self.allowed_origins = allowed_origins

    async def dispatch(self, request, call_next):
        # 1. Host header validation (blocks DNS rebinding)
        host = request.headers.get("host", "").split(":")[0]
        if host not in self.allowed_hosts:
            return Response("Forbidden Host", status_code=403)

        # 2. Origin/Referer check for state-changing requests (blocks CSRF)
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            origin = request.headers.get("origin")
            referer = request.headers.get("referer")
            if origin and not any(origin.startswith(f"http://{h}") or origin.startswith(f"https://{h}") for h in self.allowed_hosts):
                return Response("Forbidden Origin", status_code=403)
            elif not origin and referer and not any(referer.startswith(f"http://{h}") or referer.startswith(f"https://{h}") for h in self.allowed_hosts):
                return Response("Forbidden Referer", status_code=403)

        return await call_next(request)
```

## 2. HTMX Polling and Out-of-Band Swaps (TD §4.1)

### 2.1 Chat Message Submission
- `POST /chats/{id}/messages` marks chat as running, spawns background turn thread, and returns an HTML fragment:
  1. The user's message bubble.
  2. A polling placeholder element:
  ```html
  <div id="processing-placeholder"
       hx-get="/chats/{{ chat_id }}/poll"
       hx-trigger="load delay:2s"
       hx-swap="outerHTML">
      <div class="spinner">در حال پردازش...</div>
  </div>
  ```

### 2.2 Polling Endpoint (`GET /chats/{id}/poll`)
- If the turn is still running in `running_chats`:
  Return the same placeholder element with `hx-trigger="load delay:2s"`.
- When finished:
  Return the assistant message fragment, plus an out-of-band swap (`hx-swap-oob="true"`) to refresh the plan panel and re-enable the chat input:
  ```html
  <div class="message assistant-message" dir="auto">
      {{ message.content | render_markdown | safe }}
      {% if message.meta_proposal and message.meta_status == 'pending' %}
          {% include "partials/meta_card.html" %}
      {% endif %}
  </div>

  <!-- Out-of-band refresh for the plan panel -->
  <div id="plan-panel-container" hx-swap-oob="true">
      {% include "partials/plan_panel.html" %}
  </div>

  <!-- Out-of-band re-enable input -->
  <button id="send-button" hx-swap-oob="true" type="submit" class="btn-primary">ارسال</button>
  ```

## 3. Persian RTL & CSS Logical Properties (TD §10)

- Root element: `<html lang="fa" dir="rtl">`
- Typography: Use system fonts with Persian support:
  ```css
  body {
      font-family: Vazirmatn, Tahoma, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      direction: rtl;
  }
  ```
- CSS Logical Properties:
  - Use `margin-inline-start`, `margin-inline-end`, `padding-inline-start` instead of `left`/`right`.
- Bidirectional Text:
  - Add `dir="auto"` on message bubbles and user inputs so mixed Persian/English (e.g., numbers, BMI, calories) aligns and renders properly.

## 4. Markdown Rendering Helper (TD §2, §11.4)

Raw HTML must be strictly disabled to eliminate XSS risks from AI output or user inputs:
```python
from markdown_it import MarkdownIt

md_renderer = MarkdownIt("commonmark", {"html": False})

def render_markdown(text: str) -> str:
    if not text:
        return ""
    return md_renderer.render(text)
```
Expose `render_markdown` as a Jinja2 filter.
