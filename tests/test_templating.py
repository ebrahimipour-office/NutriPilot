from app.templating import render_markdown, fmt_date


def test_render_markdown_safe():
    # Regular markdown renders
    html = render_markdown("# سلام دنیا\n\nاین یک **متن آزمایشی** است.")
    assert "<h1>سلام دنیا</h1>" in html
    assert "<strong>متن آزمایشی</strong>" in html

    # Raw HTML tags MUST be disabled (escaped or omitted) per TD §2, §11.4
    xss_attempt = "<script>alert('xss')</script><b>تست</b>"
    escaped_html = render_markdown(xss_attempt)
    assert "<script>" not in escaped_html
    assert "alert('xss')" in escaped_html
    assert "&lt;script&gt;" in escaped_html or "<script>" not in escaped_html


def test_fmt_date():
    assert fmt_date(None) == ""
    assert fmt_date("") == ""

    # Valid UTC ISO date
    formatted = fmt_date("2026-11-02T12:30:00Z")
    assert formatted.startswith("2026-11-02")
