"""PDF report renderer — generates HTML then converts via Playwright.

Uses Playwright (headless Chromium) to render the HTML report to PDF,
then optionally adds bookmarks via PyPDF2.
"""

from __future__ import annotations

import contextlib
import tempfile
from pathlib import Path

__all__ = ["generate_pdf"]


def generate_pdf(
    returns,
    benchmark_rets,
    positions,
    transactions,
    trades,
    title,
    output,
    rolling_window,
):
    """Generate a PDF report by rendering the HTML report via Playwright."""
    from fincore.report.render_html import generate_html

    # 1) Generate a temporary HTML file.
    out_dir = Path(output).resolve().parent if output else Path()
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, dir=out_dir) as tmp:
        tmp_html = tmp.name

    generate_html(
        returns,
        benchmark_rets=benchmark_rets,
        positions=positions,
        transactions=transactions,
        trades=trades,
        title=title,
        output=tmp_html,
        rolling_window=rolling_window,
    )

    # 2) Render HTML to PDF via Playwright.
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise ImportError(
            "PDF generation requires Playwright:\n  pip install playwright && python -m playwright install chromium"
        ) from e

    # Temporary PDF path (we add bookmarks before writing the final output).
    tmp_pdf = output + ".tmp.pdf"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(Path(tmp_html).resolve().as_uri(), wait_until="networkidle", timeout=60000)

        # Wait for all ECharts instances to finish rendering.
        page.evaluate("""() => {
            return new Promise((resolve) => {
                let attempts = 0;
                const check = () => {
                    attempts++;
                    const containers = document.querySelectorAll('[id^="c-"]');
                    let allReady = true;
                    containers.forEach(el => {
                        const canvas = el.querySelector('canvas');
                        if (!canvas) allReady = false;
                    });
                    if (allReady || attempts > 30) resolve();
                    else setTimeout(check, 200);
                };
                setTimeout(check, 500);
            });
        }""")
        # Extra wait to let chart animations settle.
        page.wait_for_timeout(1500)

        # Collect section titles and positions for PDF bookmarks.
        section_info = page.evaluate("""() => {
            const sections = document.querySelectorAll('.sec');
            const results = [];
            sections.forEach(sec => {
                const titleEl = sec.querySelector('.sec-title');
                if (titleEl) {
                    const rect = sec.getBoundingClientRect();
                    results.push({
                        id: sec.id,
                        title: titleEl.textContent.trim(),
                        top: rect.top + window.scrollY
                    });
                }
            });
            // Total document height (CSS px).
            const totalHeight = document.documentElement.scrollHeight;
            return { sections: results, totalHeight: totalHeight };
        }""")

        page.pdf(
            path=tmp_pdf,
            format="A4",
            print_background=True,
            margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"},
        )
        browser.close()

    # 3) Cleanup temporary HTML.
    with contextlib.suppress(OSError):
        Path(tmp_html).unlink(missing_ok=True)

    # 4) Add PDF bookmarks (clickable outline).
    _add_pdf_bookmarks(tmp_pdf, output, section_info, title)

    # Cleanup temporary PDF.
    with contextlib.suppress(OSError):
        Path(tmp_pdf).unlink(missing_ok=True)

    return output


def _add_pdf_bookmarks(input_pdf, output_pdf, section_info, report_title):
    """Add clickable bookmarks/outlines to a PDF output."""
    try:
        from PyPDF2 import PdfReader, PdfWriter
    except ImportError:
        # If PyPDF2 isn't available, just copy the file.
        import shutil

        shutil.copy2(input_pdf, output_pdf)
        return

    reader = PdfReader(input_pdf)
    writer = PdfWriter()

    # Copy all pages.
    for page in reader.pages:
        writer.add_page(page)

    # Map document height (CSS px) to pages.
    total_pages = len(reader.pages)
    if total_pages == 0:
        with Path(output_pdf).open("wb") as f:
            writer.write(f)
        return

    sections = section_info.get("sections", [])

    # Each A4 page CSS height in px (approx, 96dpi) minus margins.
    # Playwright uses 96dpi; A4 = 297mm ≈ 1123px, minus margins (12mm*2 = ~91px)
    page_css_height = 1123 - 91  # ≈ 1032px per page content area

    # Root outline item.
    writer.add_outline_item(report_title, 0)

    for sec in sections:
        sec_top = sec["top"]
        sec_title = sec["title"]

        # Estimate the page index for this section.
        est_page = int(sec_top / page_css_height) if page_css_height > 0 else 0
        est_page = min(est_page, total_pages - 1)

        writer.add_outline_item(sec_title, est_page)

    with Path(output_pdf).open("wb") as f:
        writer.write(f)
