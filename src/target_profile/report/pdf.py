from pathlib import Path
from typing import Callable


def _print_with_playwright(html_path: Path, pdf_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.resolve().as_uri(), wait_until="load")
        page.wait_for_function("window.__chartsReady === true", timeout=15000)
        page.evaluate("window.__snapshotCharts && window.__snapshotCharts()")
        page.pdf(path=str(pdf_path), format="A4", print_background=True)
        browser.close()


def html_to_pdf(
    html_path: Path,
    pdf_path: Path,
    printer: Callable[[Path, Path], None] | None = None,
) -> bool:
    printer = printer or _print_with_playwright
    try:
        printer(html_path, pdf_path)
        return True
    except Exception:
        return False
