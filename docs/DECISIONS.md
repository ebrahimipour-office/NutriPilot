# Architectural & Design Decisions

This document records notable architectural choices, deviations from the Technical Design, and CLI tool configurations for NutriPilot v1.

| Date | ID | Context / Decision | Rationale |
|---|---|---|---|
| 2026-11-02 | D0.1 | Raw `sqlite3` with `row_factory = sqlite3.Row` and WAL mode | Avoid ORM complexity and extra moving parts per boring tech principle. |
| 2026-11-02 | D0.2 | Server-side rendering with Jinja2 and vendored HTMX | Simple, fast single-process web app without Node build pipelines. |
