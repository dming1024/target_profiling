from target_profile.report.pdf import html_to_pdf


def test_pdf_failure_returns_false(tmp_path, monkeypatch):
    html = tmp_path / "report.html"
    html.write_text("<html><body>x</body></html>", encoding="utf-8")

    def boom(html_path, pdf_path):
        raise RuntimeError("no browser")

    monkeypatch.setattr("target_profile.report.pdf._print_with_playwright", boom)
    assert html_to_pdf(html, tmp_path / "report.pdf") is False
