import pandas as pd

from target_profile.models import ChartSpec, ModuleResult
from target_profile.report.chapter_specs import (
    DEFAULT_THRESHOLDS,
    status_chip as _status_chip,
)
from target_profile.report.render import _block, _summary_view


def _expression_module():
    module = ModuleResult(name="expression")
    module.facts = {
        "symbol": "EGFR",
        "gtex_tissue_count": 54,
        "gtex_top_tissue": "Skin - Sun Exposed (Lower leg)",
        "gtex_top_median_tpm": 78.34,
        "tau": 0.77,
        "depmap_n_lines": 1684,
        "hpa_tissue_specificity": "Tissue enhanced",
        "function_summary": "很长" * 100,
    }
    module.tables = {
        "gtex": pd.DataFrame(
            {"Tissue": ["Lung", "Skin", "Liver"], "median": [10.0, 20.0, 30.0],
             "mean": [1.0, 2.0, 3.0], "max": [1.0, 2.0, 3.0], "count": [1, 2, 3]}
        ),
        "gtex_percentile": pd.DataFrame({"Tissue": ["Lung"], "percentile": [90.0]}),
        "depmap_lineage": pd.DataFrame(
            {"OncotreeLineage": ["Lung"], "median": [5.0], "mean": [5.0], "count": [10]}
        ),
    }
    module.narrative = "EGFR 在 54 个 GTEx 组织中可检测。"
    module.charts = [
        ChartSpec(id="expression-gtex", title="GTEx", option={"series": []})
    ]
    return module


def test_block_has_four_kpis_and_one_primary_table():
    block = _block(_expression_module(), DEFAULT_THRESHOLDS)
    assert len(block["kpis"]) == 4
    assert block["kpis"][2]["label"] == "组织特异性 τ"
    assert block["kpis"][2]["value"] == "0.770"
    assert block["status_chip"] == {"text": "偏特异表达", "level": "info"}
    assert block["primary_table"]["id"] == "gtex"
    assert "组织" in block["primary_table"]["html"]
    assert "Tissue" not in block["primary_table"]["html"]
    assert block["primary_table"]["html"].count("<tr>") == 4  # header + 3 rows


def test_block_details_hold_other_tables_metrics_and_full_text():
    block = _block(_expression_module(), DEFAULT_THRESHOLDS)
    details = block["details"]
    assert details["summary"].startswith("展开明细")
    assert {table["id"] for table in details["tables"]} == {"gtex_percentile", "depmap_lineage"}
    assert any(item["label"] == "HPA RNA 组织特异性" for item in details["metrics"])
    assert block["summary"] == "EGFR 在 54 个 GTEx 组织中可检测。"
    assert block["details"]["full_narrative"] is None


def test_long_narrative_is_truncated_and_full_text_kept():
    module = _expression_module()
    module.narrative = "长结论" * 150
    block = _block(module, DEFAULT_THRESHOLDS)
    assert block["summary"].endswith("…")
    assert block["details"]["full_narrative"] == module.narrative


def test_no_data_block_is_compact():
    module = ModuleResult(name="ptm").degrade("ptm: no curated features")
    block = _block(module, DEFAULT_THRESHOLDS)
    assert block["status"] == "no_data"
    assert block["kpis"] == [] and block["primary_table"] is None
    assert "ptm: no curated features" in block["details"]["caveats"]


def test_summary_view_groups_and_chips():
    by_name = {
        "basic": ModuleResult(name="basic", facts={"approved_name": "EGFR", "protein_length": 1210,
                                                   "target_class": "Kinase", "subcellular_locations": "Cell membrane"}),
        "disease": ModuleResult(name="disease", facts={"top_disease": "NSCLC", "top_disease_score": 0.85,
                                                       "disease_count": 5860, "clinvar_total": 4198}),
        "expression": ModuleResult(name="expression", facts={"tau": 0.77, "gtex_top_tissue": "Skin"}),
        "mutation": ModuleResult(name="mutation", facts={"overall_freq_pct": 3.61, "top_cancer": "GBM",
                                                         "top_cancer_freq_pct": 15.88}),
        "dependency": ModuleResult(name="dependency", facts={"strong_dependency_count": 212, "n_lines": 1183}),
        "cancer": ModuleResult(name="cancer", facts={"driver_status": "驱动证据阳性"}),
        "tractability": ModuleResult(name="tractability", facts={"tractable": "Yes", "approved_drug_count": 18}),
        "safety": ModuleResult(name="safety", facts={"n_safety_liabilities": 21, "constrained": "Yes",
                                                     "common_essential": "No", "loeuf": 0.505, "n_mouse_phenotypes": 181}),
    }
    view = _summary_view(by_name, DEFAULT_THRESHOLDS)
    assert [group["title"] for group in view["groups"]] == ["靶点定位", "疾病与变异", "依赖 · 成药 · 风险"]
    assert view["verdict"]["name"] == "EGFR"
    assert any(chip["text"].startswith("可成药") for chip in view["verdict"]["chips"])
    assert any(item["value"] == "NSCLC" for item in view["groups"][1]["items"])


def test_status_chip_constraint_distinguishes_missing_from_no():
    missing = ModuleResult(name="disease", facts={})
    assert _status_chip(missing, DEFAULT_THRESHOLDS) is None
    unconstrained = ModuleResult(name="disease", facts={"constrained": "No"})
    assert _status_chip(unconstrained, DEFAULT_THRESHOLDS) == {"text": "无强约束", "level": "neutral"}
    constrained = ModuleResult(name="disease", facts={"constrained": "Yes"})
    assert _status_chip(constrained, DEFAULT_THRESHOLDS) == {"text": "强约束", "level": "info"}


def test_summary_chips_do_not_contradict_negative_facts():
    by_name = {
        "basic": ModuleResult(name="basic", facts={"approved_name": "EXAMPLE"}),
        "tractability": ModuleResult(name="tractability", facts={"tractable": "No"}),
        "safety": ModuleResult(name="safety", facts={"constrained": "No", "common_essential": "No"}),
    }
    view = _summary_view(by_name, DEFAULT_THRESHOLDS)
    texts = [chip["text"] for chip in view["verdict"]["chips"]]
    assert "未证实可成药" in texts
    assert "无强约束" in texts
    assert not any(text.startswith("可成药") for text in texts)
    assert not any(text.startswith("强约束") for text in texts)
    assert not any("泛癌必需" in text for text in texts)


def test_summary_chips_positive_facts():
    by_name = {
        "basic": ModuleResult(name="basic", facts={"approved_name": "EXAMPLE"}),
        "tractability": ModuleResult(name="tractability", facts={"tractable": "Yes"}),
        "safety": ModuleResult(name="safety", facts={"constrained": "Yes", "common_essential": "Yes"}),
    }
    view = _summary_view(by_name, DEFAULT_THRESHOLDS)
    texts = [chip["text"] for chip in view["verdict"]["chips"]]
    assert "可成药" in texts
    assert "强约束" in texts
    assert "泛癌必需" in texts
