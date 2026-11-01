# NutriPilot

AI-assisted diet planning web application for coaches and nutritionists.

## Tech Stack
- **Backend:** FastAPI, Python 3.12, stdlib `sqlite3` (WAL mode)
- **Frontend:** Server-rendered HTML with Jinja2 and HTMX, Persian RTL layout
- **Storage:** SQLite for structured state, local Markdown files for sources and plans
- **Execution:** Subprocess-based local CLI runner (`claude`, `agy`, `codex`)

## Getting Started

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the server:
   ```bash
   python run.py
   ```

3. Open in your browser:
   ```text
   http://127.0.0.1:8005
   ```

## Tests
Run test suite with:
```bash
pytest -q
```
