import json

import pandas as pd

from target_profile.models import ChartSpec, GeneContext, ModuleResult
from target_profile.report.render import render_report

ALL_MODULES = [
    "basic",
    "disease",
    "expression",
    "mutation",
    "dependency",
    "cancer",
    "pathway",
    "ptm",
    "tractability",
    "safety",
    "comparative",
    "summary",
]

CHAPTER_TITLES = [
    "执行摘要",
    "基因与蛋白基础",
    "疾病关联与遗传证据",
    "表达",
    "突变与变异",
    "依赖性与癌症特征",
    "通路与相互作用",
    "蛋白修饰",
    "可成药性与药物",
    "安全性与风险",
    "比较基因组学",
    "药物基因组学/文献",
]


def _ctx():
    return GeneContext(
        symbol="KRAS",
        ensembl_id="ENSG00000133703",
        entrez_id="3845",
        uniprot_id="P01116",
        chromosome="12",
        start=25205246,
        end=25250936,
    )


def _modules():
    modules = [ModuleResult(name=name) for name in ALL_MODULES]
    by_name = {module.name: module for module in modules}
    by_name["basic"].facts = {"approved_name": "KRAS proto-oncogene, GTPase", "protein_length": 189}
    by_name["expression"].facts = {"tau": 0.575, "gtex_top_tissue": "Lung"}
    by_name["expression"].tables["gtex"] = pd.DataFrame({"Tissue": ["Lung"], "median": [10.0]})
    by_name["expression"].charts = [
        ChartSpec(
            id="expression-gtex",
            title="GTEx tissue expression",
            subtitle="Source: GTEx v8",
            option={"series": [{"type": "bar", "data": [10.0]}]},
        )
    ]
    by_name["summary"].label_cards = [
        {"label": "可成药性", "value": "Yes", "level": "ok"},
        {"label": "安全警示", "value": "无安全事件记录（不代表安全）", "level": "info"},
    ]
    by_name["summary"].facts = {"thresholds": {"pan_cancer_hotspot_pct": 5.0}}
    by_name["safety"].caveats = ["safety: 无安全记录不代表安全"]
    by_name["cancer"].status = "no_data"
    return modules


def test_render_full_structure(tmp_path):
    html_path, facts_path = render_report(_ctx(), _modules(), tmp_path / "out", llm_info=None)
    html = html_path.read_text(encoding="utf-8")

    for title in CHAPTER_TITLES + ["附录"]:
        assert title in html

    positions = [html.index(title) for title in CHAPTER_TITLES]
    assert positions == sorted(positions)

    for number in range(1, 13):
        assert f'id="ch-{number}"' in html
    assert 'id="appendix"' in html
    assert 'id="chart-data"' in html
    assert "echarts" in html.lower()

    payload = json.loads(
        html.split('<script id="chart-data" type="application/json">')[1].split("</script>")[0]
    )
    assert payload["expression-gtex"]["option"]["series"][0]["data"] == [10.0]

    for bad in ['src="http', 'href="http', "url(http", "@import url(http"]:
        assert bad not in html

    facts = json.loads(facts_path.read_text(encoding="utf-8"))
    assert facts["gene"]["symbol"] == "KRAS"
    assert facts["modules"]["expression"]["charts"] == ["expression-gtex"]
    assert facts["modules"]["summary"]["label_cards"][0]["value"] == "Yes"


def test_render_empty_and_placeholder(tmp_path):
    html_path, _ = render_report(_ctx(), _modules(), tmp_path / "out", llm_info=None)
    html = html_path.read_text(encoding="utf-8")
    assert "暂无可用数据" in html          # cancer is no_data
    assert "暂未包含" in html              # chapter 12 placeholder
    assert "无安全记录不代表安全" in html


def test_render_llm_footnote(tmp_path):
    info = {"enabled": True, "model": "gpt-test", "used": 3, "cached": 1, "fallback": 0}
    html_path, _ = render_report(_ctx(), _modules(), tmp_path / "out", llm_info=info)
    html = html_path.read_text(encoding="utf-8")
    assert "gpt-test" in html
    assert "LLM" in html


def test_render_degraded_module_keeps_caveat(tmp_path):
    modules = [
        ModuleResult(name="ptm").degrade("ptm: no curated features")
        if module.name == "ptm"
        else module
        for module in _modules()
    ]
    html_path, _ = render_report(_ctx(), modules, tmp_path / "out", llm_info=None)
    html = html_path.read_text(encoding="utf-8")
    assert "暂无可用数据" in html
    assert "ptm: no curated features" in html


def test_render_skips_unserialisable_chart(tmp_path):
    modules = _modules()
    by_name = {module.name: module for module in modules}
    by_name["expression"].charts = [
        ChartSpec(
            id="expression-bad",
            title="Bad chart",
            subtitle="Invalid",
            option={"series": [{"type": "bar", "data": [float("nan")]}]},
        )
    ]
    html_path, _ = render_report(_ctx(), modules, tmp_path / "out", llm_info=None)
    html = html_path.read_text(encoding="utf-8")
    payload = json.loads(
        html.split('<script id="chart-data" type="application/json">')[1].split("</script>")[0]
    )
    assert "expression-bad" not in payload
    assert "因配置无法序列化已跳过" in html


def test_report_uses_kpi_details_and_chinese_headers(tmp_path):
    html_path, _ = render_report(_ctx(), _modules(), tmp_path / "out", llm_info=None)
    html = html_path.read_text(encoding="utf-8")
    assert 'class="kpis"' in html
    assert "<details" in html
    assert "展开明细" in html
    assert "组织" in html
    assert "Tissue" not in html
    assert 'class="summary-groups"' in html


def test_placeholder_is_compact_but_keeps_keyword(tmp_path):
    html_path, _ = render_report(_ctx(), _modules(), tmp_path / "out", llm_info=None)
    html = html_path.read_text(encoding="utf-8")
    assert "暂未包含" in html
    assert 'class="placeholder-line"' in html


def test_hero_chips_are_rendered(tmp_path):
    modules = _modules()
    by_name = {module.name: module for module in modules}
    by_name["tractability"].facts = {"tractable": "Yes"}
    by_name["cancer"].status = "ok"
    by_name["cancer"].facts = {"driver_status": "驱动证据阳性"}
    html_path, _ = render_report(_ctx(), modules, tmp_path / "out", llm_info=None)
    html = html_path.read_text(encoding="utf-8")
    assert "chip-ok" in html
    assert "可成药" in html
