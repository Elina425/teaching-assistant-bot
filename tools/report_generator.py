"""
Generate Markdown and PDF attachments from a teaching-package report dict.

Markdown is always generated (full Unicode / Armenian support).
PDF uses Arial Unicode if available on macOS, or any TTF pointed to by
FPDF_FONT_PATH, so Armenian characters render correctly.
"""

import os
import tempfile

# macOS system fonts with full Unicode (Armenian included)
_MACOS_UNICODE_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def generate_markdown(report: dict) -> str:
    """Return the full teaching package as a Markdown string."""
    title = report.get("title", "Teaching Package")
    lines = [
        f"# {title}",
        "",
        f"**Audience:** {report.get('audience', 'N/A')}  ",
        f"**Duration:** {report.get('duration', 'N/A')}  ",
        f"**Language:** {report.get('language', 'N/A')}  ",
        "",
        "---",
        "## Summary",
        "",
        report.get("summary", ""),
        "",
        "---",
        "## Concept Map",
        "",
        report.get("concept_map", ""),
        "",
        "---",
        "## Teaching Plan",
        "",
        report.get("revised_plan", ""),
        "",
        "---",
        "## Web Resources",
        "",
        report.get("web_resources_text", ""),
        "",
        "---",
        "## Email Body",
        "",
        report.get("email_body", ""),
    ]
    return "\n".join(lines)


def save_markdown(report: dict) -> str:
    """Write the report to a temp .md file and return its path."""
    title = report.get("title", "teaching_package")
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)[:40].strip()
    path = os.path.join(tempfile.mkdtemp(), f"{safe}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(generate_markdown(report))
    return path


def save_pdf(report: dict) -> str | None:
    """
    Write the report to a temp PDF file and return its path.
    Returns None if PDF generation fails (caller should fall back to MD only).

    Armenian / Unicode characters are rendered when a suitable TTF font is found.
    Priority: FPDF_FONT_PATH env var → macOS system Arial Unicode → skip PDF.
    """
    try:
        from fpdf import FPDF
    except ImportError:
        return None

    font_path = os.getenv("FPDF_FONT_PATH") or _find_unicode_font()
    if not font_path:
        return None  # no Unicode font available; skip PDF

    try:
        title = report.get("title", "Teaching Package")
        safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)[:40].strip()
        path = os.path.join(tempfile.mkdtemp(), f"{safe}.pdf")

        pdf = FPDF()
        pdf.add_font("Unicode", fname=font_path)
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        def h1(text: str) -> None:
            pdf.set_font("Unicode", size=18)
            pdf.set_text_color(30, 30, 120)
            pdf.multi_cell(0, 10, text)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(2)

        def h2(text: str) -> None:
            pdf.set_font("Unicode", size=13)
            pdf.set_text_color(60, 60, 150)
            pdf.multi_cell(0, 8, text)
            pdf.set_text_color(0, 0, 0)
            pdf.ln(1)

        def body(text: str) -> None:
            pdf.set_font("Unicode", size=10)
            pdf.multi_cell(0, 6, text or "")
            pdf.ln(2)

        def rule() -> None:
            pdf.ln(1)
            pdf.set_draw_color(180, 180, 180)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(4)

        h1(title)
        body(
            f"Audience: {report.get('audience', 'N/A')}\n"
            f"Duration: {report.get('duration', 'N/A')}\n"
            f"Language: {report.get('language', 'N/A')}"
        )
        rule()

        for section, key in [
            ("Summary", "summary"),
            ("Concept Map", "concept_map"),
            ("Teaching Plan", "revised_plan"),
            ("Web Resources", "web_resources_text"),
            ("Email Body", "email_body"),
        ]:
            h2(section)
            body(report.get(key, ""))
            rule()

        pdf.output(path)
        return path
    except Exception:
        return None


def _find_unicode_font() -> str | None:
    for p in _MACOS_UNICODE_FONTS:
        if os.path.exists(p):
            return p
    return None
