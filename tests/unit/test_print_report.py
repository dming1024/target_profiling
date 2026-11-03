import json
import re

from target_profile.models import ChartSpec, GeneContext, ModuleResult
from target_profile.report.chapter_specs import PRINT_CHART_IDS, MODULE_SPECS
from target_profile.report.render import render_print_report


def _ctx():
    return GeneContext(symbol="EGFR", ensembl_id="ENSG00000146648", entrez_id="1956",
                       uniprot_id="P00533", chromosome="7", start=55019017, end=55211628)


def _modules(chart_ids=None):
    chart_ids = list(PRINT_CHART_IDS if chart_ids is None else chart_ids)
    modules = []
    for name, spec in MODULE_SPECS.items():
        module = ModuleResult(name=name)
        module.facts = {key: "1" for key in spec.kpi}
        module.facts["symbol"] = "EGFR"
        module.tables = {}
        modules.append(module)
    by_name = {module.name: module for module in modules}
    by_name["basic"].facts.update({"approved_name": "EGFR", "protein_length": 1210})
    by_name["summary"].facts = {"thresholds": {"tissue_specific_tau": 0.9}}
    chart_titles = {
        "expression-gtex": "GTEx",
        "mutation-cancers": "Mut",
        "dependency-dist": "Dep",
        "disease-top": "Dis",
        "tractability-heat": "Tract",
        "safety-mouse": "Safe",
        "pathway-network": "PPI",
        "cancer-hallmarks": "Hall",
    }
    for chart_id in chart_ids:
        owner = next(
            (module for module in modules if chart_id in MODULE_SPECS.get(module.name, MODULE_SPECS["basic"]).primary_charts),
            None,
        )
        if owner is None:
            owner = by_name["basic"]
        option = (
            {
                "xAxis": {"axisLabel": {"color": "#8b9bb0"}},
                "yAxis": {"axisLabel": {"color": "#c9d6e5"}},
                "tooltip": {"backgroundColor": "#0f1620", "borderColor": "rgba(8,11,16,.6)"},
                "series": [{"itemStyle": {"color": "#55d6be"}}],
            }
            if chart_id == "expression-gtex"
            else {"series": []}
        )
        owner.charts.append(ChartSpec(id=chart_id, title=chart_titles[chart_id], option=option))
    return modules


def _payload(html):
    match = re.search(r'<script id="chart-data" type="application/json">(.*?)</script>', html, re.S)
    assert match is not None
    return json.loads(match.group(1))


def test_print_report_has_five_pages_and_eight_charts(tmp_path):
    path = render_print_report(_ctx(), _modules(), tmp_path / "out", llm_info=None)
    assert path.name == "_print.html"
    html = path.read_text(encoding="utf-8")
    assert html.count('class="pdf-page"') == 5
    assert html.count('data-chart-id=') == 8
    assert "数据源与许可" in html
    assert "方法学局限" in html
    assert "url(http" not in html
    assert 'src="http' not in html
    assert 'data-theme="print"' in html
    assert "target-print" in html
    payload = _payload(html)
    assert set(payload) == set(PRINT_CHART_IDS)
    raw = json.dumps(payload)
    assert "#8b9bb0" not in raw
    assert "#c9d6e5" not in raw
    assert "#0f1620" not in raw
    assert payload["expression-gtex"]["option"]["yAxis"]["axisLabel"]["color"] == "#39414d"
    assert payload["expression-gtex"]["option"]["series"][0]["itemStyle"]["color"] == "#55d6be"
    assert payload["expression-gtex"]["option"]["tooltip"]["borderColor"] == "rgba(8,11,16,.6)"
    assert "1210 aa" in html
    assert html.count(" / 5") >= 1
    for page in range(1, 6):
        assert f"{page} / 5" in html


def test_print_report_falls_back_to_four_pages_with_three_charts(tmp_path):
    chart_ids = PRINT_CHART_IDS[:3]
    path = render_print_report(_ctx(), _modules(chart_ids), tmp_path / "out", llm_info=None)
    html = path.read_text(encoding="utf-8")
    assert html.count('class="pdf-page"') == 4
    assert "核心图表 II" not in html
    assert "3 / 4" in html
    assert "4 / 4" in html
    payload = _payload(html)
    assert set(payload) == set(chart_ids)
