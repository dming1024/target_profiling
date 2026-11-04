import pandas as pd

from target_profile.report.chapter_specs import (
    COLUMN_LABELS,
    FACT_LABELS,
    MODULE_SPECS,
    PRINT_CHART_IDS,
    format_value,
    render_table_html,
    table_title,
    truncate_text,
)
from target_profile.report.render import CHAPTERS


def test_every_chapter_module_has_spec():
    for _, _, names, _ in CHAPTERS:
        for name in names:
            assert name in MODULE_SPECS, name


def test_all_tables_have_column_labels():
    required = {
        "diseases", "datasources", "constraint", "clinvar", "gtex",
        "gtex_percentile", "depmap_lineage", "depmap_lines", "cancers",
        "types", "protein_changes", "distribution", "strong_lines",
        "by_lineage", "hallmarks", "pathways", "top_levels", "go_terms",
        "partners", "ptm_sites", "ptm_types", "domains", "tractability",
        "probes", "drugs", "drug_stages", "liabilities",
        "mouse_phenotypes", "expression_breadth", "homologues",
    }
    assert required <= set(COLUMN_LABELS)
    assert COLUMN_LABELS["gtex"]["median"] == "中位 TPM"
    assert COLUMN_LABELS["cancers"]["freq_pct"] == "突变率 (%)"


def test_primary_tables_and_kpi_keys_are_declared():
    assert MODULE_SPECS["expression"].primary_table == "gtex"
    assert MODULE_SPECS["expression"].kpi == (
        "gtex_tissue_count",
        "gtex_top_median_tpm",
        "tau",
        "depmap_n_lines",
    )
    assert len(PRINT_CHART_IDS) == 8
    for name in ("protein_length", "overall_freq_pct", "tractable"):
        assert name in FACT_LABELS


def test_table_titles_are_chinese():
    assert table_title("gtex_percentile") == "组织内表达百分位"
    assert table_title("gtex", 8, primary=True).startswith("Top 8 · ")
    assert "GTEx" in table_title("gtex", 8, primary=True)


def test_format_value_handles_units_and_empty():
    assert format_value("overall_freq_pct", 3.61) == "3.61%"
    assert format_value("tau", 0.7701) == "0.770"
    assert format_value("top_homologue_identity", 99.7) == "99.7%"
    assert format_value("gtex_tissue_count", 54) == "54"
    assert format_value("n_samples", 10967) == "10,967"
    assert format_value("tractable", None) == "—"
    assert format_value("tau", float("nan")) == "—"
    assert format_value("overall_freq_pct", float("nan")) == "—"
    assert format_value("alphafold_available", True) == "Yes"


def test_truncate_text():
    assert truncate_text("短文本") == "短文本"
    text = "龙" * 150
    result = truncate_text(text, 120)
    assert len(result) == 121 and result.endswith("…")


def test_render_table_html_uses_chinese_headers_and_limits_rows():
    frame = pd.DataFrame(
        {
            "Tissue": ["Lung", "Skin", "Liver"],
            "median": [10.0, 20.0, 30.0],
            "mean": [1.0, 2.0, 3.0],
            "max": [1.0, 2.0, 3.0],
            "count": [1, 2, 3],
        }
    )
    html = render_table_html(frame, "gtex", max_rows=2)
    assert "组织" in html and "中位 TPM" in html
    assert "Tissue" not in html and ">median<" not in html
    assert html.count("<tr>") == 3  # header + 2 rows
    assert ">54<" not in html


def test_render_table_html_value_labels():
    frame = pd.DataFrame({"drug": ["A"], "drug_id": ["D1"], "stage": ["Approved"], "diseases": ["NSCLC"]})
    html = render_table_html(frame, "drugs", max_rows=5)
    assert "已批准" in html
    assert "Approved" not in html


def test_kpi_values_use_chinese_labels():
    from target_profile.models import ModuleResult
    from target_profile.report.chapter_specs import kpi_cards

    module = ModuleResult(
        name="tractability",
        facts={"tractable": "Yes", "max_clinical_stage": "Approved", "n_drugs": 3, "approved_drug_count": 2},
    )
    cards = kpi_cards(module)
    values = {card["label"]: card["value"] for card in cards}
    assert values["可成药性"] == "是"
    assert values["最高临床阶段"] == "已批准"


def test_alphafold_kpis_and_labels():
    from target_profile.models import ModuleResult
    from target_profile.report.chapter_specs import kpi_cards

    module = ModuleResult(
        name="basic",
        facts={
            "protein_length": 393,
            "target_class": "Transcription factor",
            "subcellular_locations": "Nucleus",
            "alphafold_mean_plddt": 75.1,
            "alphafold_very_high_pct": 52.7,
        },
    )
    cards = kpi_cards(module)
    labels = {card["label"]: card["value"] for card in cards}
    assert labels["平均 pLDDT"] == "75.100"
    assert labels["高置信残基占比 (≥90)"] == "52.70%"

    assert format_value("pct", 52.7) == "52.70%"
    assert FACT_LABELS["alphafold_entry_id"] == "AlphaFold 模型 ID"
    assert FACT_LABELS["alphafold_coverage"] == "结构覆盖范围"
    assert COLUMN_LABELS["alphafold_categories"]["category"] == "置信度等级"
    assert table_title("alphafold_categories") == "AlphaFold 置信度分级"
