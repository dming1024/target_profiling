from pathlib import Path

CSS = Path(__file__).parents[2] / "src/target_profile/report/static/dashboard.css"
TEMPLATE = Path(__file__).parents[2] / "src/target_profile/report/templates/report.html.j2"


def test_dashboard_has_new_components():
    css = CSS.read_text(encoding="utf-8")
    for token in (".kpis", ".kpi-label", ".kpi-value", ".chip", ".chart-grid",
                  ".details", ".summary-groups", ".placeholder-line", ".metric-list",
                  ".reading-progress"):
        assert token in css, token
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
    assert "tabular-nums" in css
    assert "__FONT_500_B64__" in css and "__FONT_700_B64__" in css


def test_template_has_reading_progress_and_symbol_watermark():
    template = TEMPLATE.read_text(encoding="utf-8")
    assert 'class="reading-progress"' in template
    assert 'data-symbol="{{ gene.symbol }}"' in template
