# 报告重设计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 12 章 HTML 报告重构为「结论先行 + Top 主表 + 折叠明细」的统一版式，并新增 5 页浅色 PDF 精简版。

**Architecture:** 新增 `report/chapter_specs.py` 集中声明每章的 KPI、状态、主表、中文表头与格式规则；`report/render.py` 负责把 `ModuleResult` 转成新模板所需结构；网页模板与打印模板分离，共用同一份渲染上下文与 ECharts payload。

**Tech Stack:** Python 3.13、Jinja2、pandas、ECharts 5.5.1、Playwright、pytest。

> **Git 约定：** 用户要求本项目暂不使用 git。因此本计划**不包含 commit 步骤**；每个任务以「目标测试通过」作为完成标志，最终统一运行全量 pytest。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `src/target_profile/report/chapter_specs.py` | 新增。章节元数据、中文表头、数值格式、状态规则、表格 HTML 生成 |
| `src/target_profile/report/render.py` | 修改。生成 block/section 视图、执行摘要视图、共享上下文、打印报告 |
| `src/target_profile/report/templates/report.html.j2` | 重写。KPI 条、状态 chip、图表双列、主表、`<details>`、新摘要 |
| `src/target_profile/report/templates/print.html.j2` | 新增。5 页精简 PDF 模板 |
| `src/target_profile/report/static/dashboard.css` | 重写。方向 A 设计令牌与组件 |
| `src/target_profile/report/static/print-speedread.css` | 新增。浅色 A4 精简版样式 |
| `src/target_profile/report/print.css` | 保留。浏览器手动打印 `report.html` 时的降级样式 |
| `src/target_profile/cli.py` | 修改。PDF 改由 `_print.html` 生成并在 finally 清理 |
| `tests/unit/test_chapter_specs.py` | 新增。元数据、格式化、表头、截断测试 |
| `tests/unit/test_render_blocks.py` | 新增。块视图与摘要视图测试 |
| `tests/unit/test_print_report.py` | 新增。打印模板与图表选择测试 |
| `tests/test_cli_run.py` | 修改。新增 PDF 使用精简模板并清理临时文件的测试 |

---

### Task 1: 章节元数据与中文表头

**Files:**
- Create: `src/target_profile/report/chapter_specs.py`
- Test: `tests/unit/test_chapter_specs.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/test_chapter_specs.py`：

```python
from target_profile.report.chapter_specs import (
    COLUMN_LABELS,
    FACT_LABELS,
    MODULE_SPECS,
    PRINT_CHART_IDS,
    table_title,
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_chapter_specs.py -v`

Expected: FAIL，`ModuleNotFoundError: No module named 'target_profile.report.chapter_specs'`

- [ ] **Step 3: 创建 `chapter_specs.py`**

创建 `src/target_profile/report/chapter_specs.py`：

```python
"""Presentation metadata for the target profile report."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_THRESHOLDS = {
    "tissue_specific_tau": 0.9,
    "tissue_partial_tau": 0.6,
    "pan_cancer_hotspot_pct": 5.0,
    "strong_dependency_effect": -0.5,
    "loeuf_constrained": 0.6,
}


@dataclass(frozen=True)
class ModuleSpec:
    kpi: tuple[str, ...] = ()
    status: str | None = None
    primary_table: str | None = None
    secondary_tables: tuple[str, ...] = ()
    primary_charts: tuple[str, ...] = ()
    table_rows: int = 8


MODULE_SPECS: dict[str, ModuleSpec] = {
    "basic": ModuleSpec(
        kpi=("protein_length", "target_class", "subcellular_locations", "alphafold_mean_plddt"),
        status="target_class",
    ),
    "disease": ModuleSpec(
        kpi=("disease_count", "top_disease", "clinvar_total", "constrained"),
        status="constraint",
        primary_table="diseases",
        secondary_tables=("datasources", "constraint", "clinvar"),
        primary_charts=("disease-top",),
    ),
    "expression": ModuleSpec(
        kpi=("gtex_tissue_count", "gtex_top_median_tpm", "tau", "depmap_n_lines"),
        status="tau",
        primary_table="gtex",
        secondary_tables=("gtex_percentile", "depmap_lineage", "depmap_lines"),
        primary_charts=("expression-gtex",),
    ),
    "mutation": ModuleSpec(
        kpi=("overall_freq_pct", "top_cancer_freq_pct", "n_mutated_samples", "top_protein_change"),
        status="mutation_freq",
        primary_table="cancers",
        secondary_tables=("types", "protein_changes"),
        primary_charts=("mutation-cancers",),
    ),
    "dependency": ModuleSpec(
        kpi=("strong_dependency_count", "strong_dependency_fraction", "median_effect", "top_lineage"),
        status="dependency",
        primary_table="by_lineage",
        secondary_tables=("distribution", "strong_lines"),
        primary_charts=("dependency-dist",),
    ),
    "cancer": ModuleSpec(
        kpi=("n_cancer_hallmarks", "top_hallmark", "driver_status", "essential"),
        status="driver",
        primary_table="hallmarks",
        primary_charts=("cancer-hallmarks",),
    ),
    "pathway": ModuleSpec(
        kpi=("n_pathways", "top_level_term", "n_go_terms", "n_partners_high_conf"),
        status="pathway",
        primary_table="pathways",
        secondary_tables=("top_levels", "go_terms", "partners"),
        primary_charts=("pathway-network",),
    ),
    "ptm": ModuleSpec(
        kpi=("n_ptm_sites", "top_ptm_type", "n_domains", "sequence_length"),
        status="ptm",
        primary_table="ptm_sites",
        secondary_tables=("ptm_types", "domains"),
        primary_charts=("ptm-sites",),
    ),
    "tractability": ModuleSpec(
        kpi=("tractable", "max_clinical_stage", "n_drugs", "approved_drug_count"),
        status="tractable",
        primary_table="drugs",
        secondary_tables=("tractability", "probes", "drug_stages"),
        primary_charts=("tractability-heat",),
    ),
    "safety": ModuleSpec(
        kpi=("n_safety_liabilities", "top_safety_event", "n_mouse_phenotypes", "constrained"),
        status="safety",
        primary_table="liabilities",
        secondary_tables=("mouse_phenotypes", "expression_breadth"),
        primary_charts=("safety-mouse",),
    ),
    "comparative": ModuleSpec(
        kpi=("n_homologues", "top_homologue_identity", "n_paralogues", "top_paralogue_identity"),
        status="homologue",
        primary_table="homologues",
        primary_charts=("comparative-identity",),
    ),
}

PRINT_CHART_IDS = (
    "expression-gtex",
    "mutation-cancers",
    "dependency-dist",
    "disease-top",
    "tractability-heat",
    "safety-mouse",
    "pathway-network",
    "cancer-hallmarks",
)

TABLE_TITLES: dict[str, str] = {
    "diseases": "疾病关联",
    "datasources": "证据来源分布",
    "constraint": "LoF 约束分析",
    "clinvar": "ClinVar 变异",
    "gtex": "GTEx 组织表达",
    "gtex_percentile": "组织内表达百分位",
    "depmap_lineage": "DepMap 谱系表达",
    "depmap_lines": "DepMap 细胞系表达",
    "cancers": "TCGA 癌种突变频率",
    "types": "突变类型",
    "protein_changes": "蛋白改变",
    "distribution": "依赖性分布",
    "strong_lines": "强依赖细胞系",
    "by_lineage": "谱系依赖性",
    "hallmarks": "癌症 hallmark",
    "pathways": "Reactome 通路",
    "top_levels": "Reactome 顶层类别",
    "go_terms": "GO 条目",
    "partners": "高置信互作伙伴",
    "ptm_sites": "PTM 位点",
    "ptm_types": "PTM 类型",
    "domains": "结构域 / 区域",
    "tractability": "可成药桶",
    "probes": "化学探针",
    "drugs": "药物与临床候选",
    "drug_stages": "临床阶段分布",
    "liabilities": "安全事件",
    "mouse_phenotypes": "小鼠表型",
    "expression_breadth": "表达广度",
    "homologues": "同源基因",
}

COLUMN_LABELS: dict[str, dict[str, str]] = {
    "diseases": {"disease_id": "疾病 ID", "disease": "疾病", "score": "关联评分", "datasources": "证据源数"},
    "datasources": {"datasource": "证据来源", "diseases": "涉及疾病数"},
    "constraint": {"type": "变异类型", "score": "约束评分", "oe": "观察/预期", "oe_upper": "OE 上限"},
    "clinvar": {"variant": "变异", "classification": "临床分类", "review": "审阅状态"},
    "gtex": {"Tissue": "组织", "median": "中位 TPM", "mean": "平均 TPM", "max": "最大 TPM", "count": "样本数"},
    "gtex_percentile": {"Tissue": "组织", "percentile": "组织内百分位"},
    "depmap_lineage": {"OncotreeLineage": "谱系", "median": "中位 log2(TPM+1)", "mean": "平均", "count": "细胞系数"},
    "depmap_lines": {
        "ModelID": "模型 ID", "value": "log2(TPM+1)", "CellLineName": "细胞系",
        "OncotreeLineage": "谱系", "OncotreePrimaryDisease": "原发疾病",
    },
    "cancers": {
        "studyId": "研究 ID", "cancer": "癌种", "n_samples": "样本数",
        "n_mutated_samples": "突变样本数", "n_mutations": "突变数", "freq_pct": "突变率 (%)",
    },
    "types": {"mutationType": "突变类型", "count": "计数"},
    "protein_changes": {"proteinChange": "蛋白改变", "count": "计数"},
    "distribution": {
        "ModelID": "模型 ID", "effect": "Chronos 效应", "CellLineName": "细胞系",
        "OncotreeLineage": "谱系", "OncotreePrimaryDisease": "原发疾病",
    },
    "strong_lines": {
        "ModelID": "模型 ID", "effect": "Chronos 效应", "CellLineName": "细胞系",
        "OncotreeLineage": "谱系", "OncotreePrimaryDisease": "原发疾病",
    },
    "by_lineage": {"OncotreeLineage": "谱系", "median": "中位 Chronos 效应", "mean": "平均效应", "count": "细胞系数"},
    "hallmarks": {"impact": "影响", "label": "Hallmark", "promotes": "促进", "suppresses": "抑制", "total": "合计"},
    "pathways": {"pathwayId": "通路 ID", "pathway": "通路", "topLevelTerm": "顶层类别"},
    "top_levels": {"topLevelTerm": "顶层类别", "count": "通路数"},
    "go_terms": {"aspect": "GO 方面", "term": "GO 条目", "evidence_count": "证据数"},
    "partners": {"preferredName_B": "互作伙伴", "score": "互作分数"},
    "ptm_sites": {"type": "修饰类型", "position": "位置", "end": "结束位置", "description": "描述"},
    "ptm_types": {"type": "修饰类型", "count": "位点数"},
    "domains": {"type": "类型", "name": "名称", "start": "起点", "end": "终点"},
    "tractability": {"modality": "模态", "bucket": "可成药桶", "available": "可用"},
    "probes": {"probe": "探针", "drug_id": "药物 ID", "mechanism": "机制", "high_quality": "高质量"},
    "drugs": {"drug": "药物", "drug_id": "药物 ID", "stage": "阶段", "diseases": "适应症"},
    "drug_stages": {"stage": "阶段", "count": "药物数"},
    "liabilities": {"event": "安全事件", "datasource": "数据源", "effect": "影响", "studies": "研究数"},
    "mouse_phenotypes": {"phenotype_class": "表型类别", "models": "模型数"},
    "expression_breadth": {"tissue": "组织", "median": "中位 TPM"},
    "homologues": {"species": "物种", "type": "同源类型", "identity": "一致性 (%)", "target_gene_id": "目标基因 ID"},
}

VALUE_LABELS: dict[str, dict[str, str]] = {
    "stage": {"APPROVAL": "已批准", "PHASE_3": "III 期", "PHASE_2": "II 期", "PHASE_1": "I 期"},
    "type": {"ortholog": "直系同源", "within_species_paralog": "种内旁系同源"},
    "impact": {"promotes": "促进", "suppresses": "抑制"},
}

FACT_LABELS: dict[str, str] = {
    "symbol": "基因符号",
    "ensembl_id": "Ensembl ID",
    "biotype": "基因类型",
    "tau": "组织特异性 τ",
    "gtex_top_tissue": "最高表达组织",
    "gtex_top_median_tpm": "最高组织中位 TPM",
    "gtex_tissue_count": "GTEx 组织数",
    "gtex_mean_percentile": "平均组织内百分位",
    "gtex_median_across_tissues": "组织中位 TPM",
    "depmap_n_lines": "DepMap 细胞系数",
    "depmap_median_logtpm": "细胞系中位 log2(TPM+1)",
    "depmap_top_lineage": "表达最高谱系",
    "hpa_tissue_specificity": "HPA RNA 组织特异性",
    "hpa_subcellular_location": "HPA 亚细胞定位",
    "n_studies": "TCGA 研究数",
    "n_samples": "TCGA 样本数",
    "n_mutated_samples": "突变样本数",
    "overall_freq_pct": "泛癌突变率 (%)",
    "top_cancer": "最高突变癌种",
    "top_cancer_freq_pct": "最高癌种突变率 (%)",
    "top_protein_change": "最常见蛋白改变",
    "top_protein_change_count": "最常见改变计数",
    "n_lines": "DepMap 细胞系数",
    "median_effect": "中位 Chronos 效应",
    "mean_effect": "平均 Chronos 效应",
    "strong_dependency_count": "强依赖细胞系数",
    "strong_dependency_fraction": "强依赖比例",
    "threshold_effect": "强依赖阈值",
    "top_lineage": "最敏感谱系",
    "top_lineage_median": "最敏感谱系中位效应",
    "most_dependent_line": "最依赖细胞系",
    "approved_name": "蛋白质全名 (OT)",
    "target_class": "靶点类别",
    "subcellular_locations": "亚细胞定位",
    "function_summary": "功能摘要",
    "synonym_count": "别名数",
    "protein_length": "蛋白长度 (aa)",
    "protein_name": "UniProt 蛋白名",
    "alphafold_available": "AlphaFold 结构",
    "alphafold_mean_plddt": "平均 pLDDT",
    "n_pathways": "Reactome 通路数",
    "top_level_term": "主要通路类别",
    "top_level_terms": "Top 通路类别",
    "n_go_terms": "GO 条目数",
    "go_aspect_summary": "GO 方面分布",
    "n_partners_high_conf": "高置信互作伙伴数",
    "top_partner": "最强互作伙伴",
    "top_partner_score": "最高互作分数",
    "n_ptm_sites": "文献注释 PTM 位点数",
    "top_ptm_type": "主要 PTM 类型",
    "ptm_types": "PTM 类型分布",
    "n_domains": "结构域/区域数",
    "domain_summary": "结构域摘要",
    "sequence_length": "序列长度 (aa)",
    "disease_count": "疾病关联数",
    "top_disease": "Top 关联疾病",
    "top_disease_score": "最高关联分数",
    "top_diseases": "Top 3 关联疾病",
    "pli": "pLI",
    "loeuf": "LOEUF",
    "lof_oe": "LoF 观察/预期比",
    "constrained": "强约束",
    "clinvar_total": "ClinVar 记录数",
    "clinvar_pathogenic_submissions": "ClinVar 含致病提交记录数",
    "clinvar_top_variant": "ClinVar 代表变异",
    "tractable": "可成药性",
    "approved_modalities": "已批准药物模态",
    "advanced_clinical_modalities": "临床后期模态",
    "n_probes": "化学探针数",
    "n_high_quality_probes": "高质量探针数",
    "top_probe": "代表探针",
    "n_drugs": "药物/临床候选数",
    "max_clinical_stage": "最高临床阶段",
    "approved_drug_count": "已批准药物数",
    "n_safety_liabilities": "安全事件记录数",
    "safety_datasources": "安全事件数据源",
    "top_safety_event": "代表安全事件",
    "n_mouse_phenotypes": "小鼠表型数",
    "top_mouse_phenotype_class": "主要小鼠表型类别",
    "mouse_phenotype_examples": "小鼠表型示例",
    "common_essential": "泛癌必需",
    "n_paralogues": "旁系同源数",
    "top_paralogue_identity": "最近旁系一致性 (%)",
    "n_tissues_expressed": "表达组织数",
    "tissue_count": "组织总数",
    "expression_tau": "表达 τ",
    "n_cancer_hallmarks": "癌症 hallmark 数",
    "top_hallmark": "代表 hallmark",
    "cancer_hallmark_impacts": "hallmark 影响分布",
    "essential": "泛癌必需（OT）",
    "pan_cancer_freq_pct": "泛癌突变率（%）",
    "driver_status": "驱动状态",
    "n_homologues": "同源基因数",
    "top_homologue": "最相近同源基因",
    "top_homologue_identity": "最高同源一致性 (%)",
    "top_orthologue": "最近直系同源",
    "top_orthologue_identity": "直系同源一致性 (%)",
}


def table_title(table_key: str, row_count: int | None = None, primary: bool = False) -> str:
    base = TABLE_TITLES.get(table_key, table_key.replace("_", " "))
    if primary and row_count:
        return f"Top {min(row_count, 8)} · {base}"
    return base
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_chapter_specs.py -v`

Expected: 4 passed。

- [ ] **Step 5: 检查点**

Run: `uv run pytest tests/unit/test_chapter_specs.py -q`

Expected: 全部通过。不做 git commit（本项目禁用 git）。

---

### Task 2: 数值格式、截断与表格 HTML

**Files:**
- Modify: `src/target_profile/report/chapter_specs.py`
- Test: `tests/unit/test_chapter_specs.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/unit/test_chapter_specs.py` 末尾追加：

```python
import pandas as pd

from target_profile.report.chapter_specs import (
    format_value,
    render_table_html,
    truncate_text,
)


def test_format_value_handles_units_and_empty():
    assert format_value("overall_freq_pct", 3.61) == "3.61%"
    assert format_value("tau", 0.7701) == "0.770"
    assert format_value("top_homologue_identity", 99.7) == "99.7%"
    assert format_value("gtex_tissue_count", 54) == "54"
    assert format_value("n_samples", 10967) == "10,967"
    assert format_value("tractable", None) == "—"
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
    frame = pd.DataFrame({"drug": ["A"], "drug_id": ["D1"], "stage": ["APPROVAL"], "diseases": ["NSCLC"]})
    html = render_table_html(frame, "drugs", max_rows=5)
    assert "已批准" in html
    assert "APPROVAL" not in html
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_chapter_specs.py -v`

Expected: FAIL，`ImportError: cannot import name 'format_value'`。

- [ ] **Step 3: 实现格式化与表格函数**

在 `chapter_specs.py` 顶部加入 `import html`、`import math`、`import pandas as pd`，并在文件末尾追加：

```python
_PCT_KEYS = {
    "overall_freq_pct", "top_cancer_freq_pct", "pan_cancer_freq_pct",
    "freq_pct", "expression_freq_pct",
}
_THREE_DECIMAL_KEYS = {
    "score", "median", "mean", "effect", "oe", "oe_upper", "percentile",
    "tau", "pli", "loeuf", "lof_oe", "top_disease_score", "top_partner_score",
    "strong_dependency_fraction", "top_lineage_median", "median_effect",
    "mean_effect", "threshold_effect", "alphafold_mean_plddt",
}
_ONE_DECIMAL_PCT_KEYS = {
    "identity", "top_homologue_identity", "top_orthologue_identity",
    "top_paralogue_identity",
}
_BOOL_KEYS = {"available", "high_quality", "alphafold_available", "constrained", "common_essential"}


def _is_count_key(key: str) -> bool:
    return (
        key == "count"
        or key.startswith("n_")
        or key.endswith("_count")
        or key in {"models", "studies", "diseases", "participants", "tissues"}
    )


def _is_numeric_key(key: str) -> bool:
    return (
        key in _PCT_KEYS
        or key in _THREE_DECIMAL_KEYS
        or key in _ONE_DECIMAL_PCT_KEYS
        or _is_count_key(key)
        or key.endswith("_pct")
    )


def _as_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def format_value(key: str, value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if key in _BOOL_KEYS:
        return str(value)
    if key in _PCT_KEYS or key.endswith("_pct"):
        number = _as_number(value)
        return f"{number:.2f}%" if number is not None else str(value)
    if key in _ONE_DECIMAL_PCT_KEYS:
        number = _as_number(value)
        return f"{number:.1f}%" if number is not None else str(value)
    if key in _THREE_DECIMAL_KEYS:
        number = _as_number(value)
        return f"{number:.3f}" if number is not None else str(value)
    if _is_count_key(key):
        number = _as_number(value)
        return f"{int(round(number)):,}" if number is not None else str(value)
    return str(value)


def format_cell(column: str, value: Any) -> str:
    text = format_value(column, value)
    mapped = VALUE_LABELS.get(column, {}).get(text)
    if mapped:
        text = mapped
    return truncate_text(text, 60)


def truncate_text(text: str, limit: int = 120) -> str:
    text = str(text).strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def is_numeric_column(column: str) -> bool:
    return _is_numeric_key(column)


def render_table_html(frame: pd.DataFrame, table_key: str, max_rows: int = 8) -> str:
    if frame is None or not hasattr(frame, "head") or frame.empty:
        return ""
    labels = COLUMN_LABELS.get(table_key, {})
    columns = [column for column in frame.columns if not labels or column in labels]
    if not columns:
        columns = list(frame.columns)
    head = frame.loc[:, columns].head(max_rows)
    header_cells = []
    for column in columns:
        label = labels.get(column, str(column))
        css = ' class="num"' if is_numeric_column(column) else ""
        header_cells.append(f"<th{css}>{html.escape(str(label))}</th>")
    rows = []
    for row in head.itertuples(index=False, name=None):
        cells = []
        for column, value in zip(columns, row):
            css = ' class="num"' if is_numeric_column(column) else ""
            cells.append(f"<td{css}>{html.escape(format_cell(column, value))}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return (
        '<table class="dt"><thead><tr>'
        + "".join(header_cells)
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_chapter_specs.py -v`

Expected: 8 passed。

- [ ] **Step 5: 检查点**

Run: `uv run pytest tests/unit/test_chapter_specs.py -q`

Expected: 全部通过。

---

### Task 3: KPI、状态与块视图

**Files:**
- Modify: `src/target_profile/report/chapter_specs.py`
- Modify: `src/target_profile/report/render.py`
- Test: `tests/unit/test_render_blocks.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/test_render_blocks.py`：

```python
import pandas as pd

from target_profile.models import ChartSpec, ModuleResult
from target_profile.report.chapter_specs import DEFAULT_THRESHOLDS
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_render_blocks.py -v`

Expected: FAIL，`ImportError: cannot import name '_block'` 或 `_summary_view`。

- [ ] **Step 3: 在 `chapter_specs.py` 增补 KPI / 状态 / 指标函数**

在 `chapter_specs.py` 末尾追加：

```python
KPI_UNITS: dict[str, str] = {
    "protein_length": "aa",
    "sequence_length": "aa",
    "gtex_tissue_count": "个组织",
    "gtex_top_median_tpm": "TPM",
    "depmap_n_lines": "细胞系",
    "n_mutated_samples": "样本",
    "disease_count": "种",
    "clinvar_total": "条",
    "strong_dependency_count": "细胞系",
    "n_mouse_phenotypes": "个",
    "n_drugs": "个",
    "approved_drug_count": "个",
    "n_homologues": "个",
    "n_paralogues": "个",
    "n_pathways": "条",
    "n_go_terms": "条",
    "n_partners_high_conf": "个",
    "n_ptm_sites": "个",
    "n_domains": "个",
    "n_cancer_hallmarks": "项",
    "n_safety_liabilities": "条",
}

_TKPI_TRUNCATE = {"target_class", "subcellular_locations", "top_level_term"}


def _kpi_hint(key: str, facts: dict[str, Any]) -> str:
    if key == "top_disease":
        score = _as_number(facts.get("top_disease_score"))
        return f"评分 {score:.3f}" if score is not None else ""
    if key == "top_protein_change":
        count = _as_number(facts.get("top_protein_change_count"))
        return f"{int(count)} 次" if count is not None else ""
    if key == "top_cancer":
        freq = _as_number(facts.get("top_cancer_freq_pct"))
        return f"{freq:.2f}%" if freq is not None else ""
    if key == "top_homologue_identity":
        return "最高同源一致性"
    return ""


def kpi_cards(module: "ModuleResult") -> list[dict[str, str]]:
    spec = MODULE_SPECS.get(module.name)
    if not spec:
        return []
    cards: list[dict[str, str]] = []
    for key in spec.kpi:
        if key not in module.facts:
            continue
        raw = module.facts.get(key)
        if raw is None or raw == "":
            continue
        value = format_value(key, raw)
        if key in _TKPI_TRUNCATE:
            value = truncate_text(value, 32)
        cards.append(
            {
                "label": FACT_LABELS.get(key, key),
                "value": value,
                "unit": KPI_UNITS.get(key, ""),
                "hint": _kpi_hint(key, module.facts),
            }
        )
    return cards


def _chip(text: str, level: str) -> dict[str, str]:
    return {"text": text, "level": level}


def status_chip(module: "ModuleResult", thresholds: dict[str, float] | None = None) -> dict[str, str] | None:
    spec = MODULE_SPECS.get(module.name)
    if not spec or not spec.status:
        return None
    settings = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    facts = module.facts
    rule = spec.status
    if rule == "target_class":
        text = str(facts.get("target_class") or "").split(" / ")[0].strip()
        return _chip(text, "info") if text else None
    if rule == "constraint":
        return _chip("强约束", "info") if facts.get("constrained") == "Yes" else _chip("无强约束", "neutral")
    if rule == "tau":
        tau = _as_number(facts.get("tau"))
        if tau is None:
            return None
        if tau >= settings["tissue_specific_tau"]:
            return _chip("组织特异", "ok")
        if tau >= settings["tissue_partial_tau"]:
            return _chip("偏特异表达", "info")
        return _chip("广泛表达", "neutral")
    if rule == "mutation_freq":
        freq = _as_number(facts.get("overall_freq_pct"))
        if freq is None:
            return None
        hot = freq > settings["pan_cancer_hotspot_pct"]
        return _chip("高频突变" if hot else "低频突变", "warn" if hot else "info")
    if rule == "dependency":
        effect = _as_number(facts.get("mean_effect"))
        if effect is None:
            return None
        strong = effect <= settings["strong_dependency_effect"]
        return _chip("强依赖" if strong else "非强依赖", "ok" if strong else "info")
    if rule == "driver":
        text = str(facts.get("driver_status") or "").strip()
        return _chip(text, "warn" if "阳性" in text else "info") if text else None
    if rule == "pathway":
        text = str(facts.get("top_level_term") or "").strip()
        return _chip(text, "info") if text else None
    if rule == "ptm":
        text = str(facts.get("top_ptm_type") or "").strip()
        return _chip(text, "info") if text else None
    if rule == "tractable":
        text = str(facts.get("tractable") or "").strip()
        if not text:
            return None
        return _chip("可成药" if text == "Yes" else "未证实", "ok" if text == "Yes" else "neutral")
    if rule == "safety":
        count = _as_number(facts.get("n_safety_liabilities"))
        if count is None:
            return None
        if count > 0:
            return _chip(f"{int(count)} 条安全事件", "warn")
        return _chip("无安全记录（不代表安全）", "neutral")
    if rule == "homologue":
        count = _as_number(facts.get("n_homologues"))
        return _chip(f"{int(count)} 个同源基因", "info") if count is not None else None
    return None


def metric_rows(module: "ModuleResult") -> list[dict[str, str]]:
    spec = MODULE_SPECS.get(module.name)
    skip = set(spec.kpi) if spec else set()
    skip |= {"symbol", "thresholds"}
    rows = []
    for key, value in module.facts.items():
        if key in skip or value is None or value == "":
            continue
        rows.append({"label": FACT_LABELS.get(key, key), "value": format_value(key, value)})
    return rows


def details_summary(tables: list[dict[str, Any]], metrics: list[dict[str, str]], full_narrative: str | None) -> str:
    parts: list[str] = []
    if tables:
        parts.append(f"{len(tables)} 张明细表")
    if metrics:
        parts.append(f"{len(metrics)} 项指标")
    if full_narrative:
        parts.append("完整结论")
    return "展开明细 · " + " · ".join(parts) if parts else "展开明细"
```

在文件顶部增加类型检查用的导入：

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from target_profile.models import ModuleResult
```

注意：`kpi_cards`、`status_chip`、`metric_rows` 的注解使用字符串 `"ModuleResult"`，运行时不需要该导入。

- [ ] **Step 4: 在 `render.py` 重构 `_block` 并新增 `_summary_view`**

在 `render.py` 顶部导入：

```python
from target_profile.report.chapter_specs import (
    DEFAULT_THRESHOLDS,
    FACT_LABELS,
    MODULE_SPECS,
    ModuleSpec,
    details_summary,
    kpi_cards,
    metric_rows,
    render_table_html,
    status_chip,
    table_title,
    truncate_text,
)
```

删除 `render.py` 中原有的 `FACT_LABELS` 常量（已移动到 `chapter_specs.py`），保留 `THRESHOLD_LABELS`、`LIMITATIONS`、`FALLBACK_SOURCES`。

用以下实现替换原 `_block`：

```python
def _block(module: ModuleResult, thresholds: dict[str, float] | None = None) -> dict[str, Any]:
    title = SECTION_TITLES.get(module.name, module.name)
    settings = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    chip = status_chip(module, settings)
    if module.status == "no_data":
        return {
            "id": module.name,
            "title": title,
            "status": "no_data",
            "status_chip": None,
            "narrative": None,
            "summary": None,
            "charts": [],
            "kpis": [],
            "primary_table": None,
            "details": {
                "summary": "展开明细",
                "tables": [],
                "metrics": [],
                "caveats": list(module.caveats),
                "full_narrative": None,
            },
        }

    spec = MODULE_SPECS.get(module.name, ModuleSpec())
    tables = []
    primary_table = None
    seen = set()
    if spec.primary_table:
        frame = module.tables.get(spec.primary_table)
        if hasattr(frame, "head") and not frame.empty:
            row_count = min(len(frame), spec.table_rows)
            primary_table = {
                "id": spec.primary_table,
                "title": table_title(spec.primary_table, row_count, primary=True),
                "html": render_table_html(frame, spec.primary_table, spec.table_rows),
            }
            seen.add(spec.primary_table)

    for key in spec.secondary_tables:
        frame = module.tables.get(key)
        if hasattr(frame, "head") and not frame.empty:
            tables.append(
                {
                    "id": key,
                    "title": table_title(key, len(frame)),
                    "html": render_table_html(frame, key, 20),
                }
            )
            seen.add(key)

    for key, frame in module.tables.items():
        if key in seen or not hasattr(frame, "head") or frame.empty:
            continue
        tables.append(
            {
                "id": key,
                "title": table_title(key, len(frame)),
                "html": render_table_html(frame, key, 20),
            }
        )

    metrics = metric_rows(module)
    full_narrative = module.narrative if module.narrative and len(module.narrative) > 200 else None
    summary = truncate_text(module.narrative or "", 200) if module.narrative else None

    return {
        "id": module.name,
        "title": title,
        "status": "ok",
        "status_chip": chip,
        "narrative": module.narrative,
        "summary": summary,
        "charts": [],
        "kpis": kpi_cards(module),
        "primary_table": primary_table,
        "details": {
            "summary": details_summary(tables, metrics, full_narrative),
            "tables": tables,
            "metrics": metrics,
            "caveats": list(module.caveats),
            "full_narrative": full_narrative,
        },
    }


def _summary_view(by_name: dict[str, ModuleResult], thresholds: dict[str, float] | None = None) -> dict[str, Any]:
    settings = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

    def facts(name: str, key: str) -> Any:
        module = by_name.get(name)
        return module.facts.get(key) if module is not None else None

    basic = by_name.get("basic")
    name = str(facts("basic", "approved_name") or "单基因靶点")
    line = str(facts("basic", "function_summary") or facts("basic", "target_class") or "")
    line = truncate_text(line, 120)

    chips = []
    tractable = facts("tractability", "tractable")
    if tractable:
        chips.append({"text": f"可成药 · {tractable}", "level": "ok" if tractable == "Yes" else "neutral"})
    driver = facts("cancer", "driver_status")
    if driver:
        chips.append({"text": str(driver), "level": "warn" if "阳性" in str(driver) else "info"})
    tau = _number_for_summary(facts("expression", "tau"))
    if tau is not None:
        if tau >= settings["tissue_specific_tau"]:
            text, level = "组织特异表达", "ok"
        elif tau >= settings["tissue_partial_tau"]:
            text, level = "偏特异表达", "info"
        else:
            text, level = "广泛表达", "neutral"
        chips.append({"text": f"{text} · τ={tau:.2f}", "level": level})
    constrained = facts("safety", "constrained") or facts("disease", "constrained")
    if constrained:
        chips.append({"text": f"强约束 · {constrained}", "level": "info"})
    essential = facts("safety", "common_essential")
    if essential:
        chips.append({"text": f"泛癌必需 · {essential}", "level": "warn" if essential == "Yes" else "neutral"})

    groups = [
        {
            "title": "靶点定位",
            "items": [
                {"label": "靶点类别", "value": truncate_text(str(facts("basic", "target_class") or "—"), 40)},
                {"label": "蛋白长度", "value": format_value("protein_length", facts("basic", "protein_length"))},
                {"label": "最高表达组织", "value": str(facts("expression", "gtex_top_tissue") or "—")},
                {"label": "亚细胞定位", "value": truncate_text(str(facts("basic", "subcellular_locations") or "—"), 40)},
            ],
        },
        {
            "title": "疾病与变异",
            "items": [
                {"label": "Top 关联疾病", "value": str(facts("disease", "top_disease") or "—")},
                {"label": "关联评分", "value": format_value("top_disease_score", facts("disease", "top_disease_score"))},
                {"label": "泛癌突变率", "value": format_value("overall_freq_pct", facts("mutation", "overall_freq_pct"))},
                {"label": "最高癌种", "value": str(facts("mutation", "top_cancer") or "—")},
                {"label": "ClinVar 记录", "value": format_value("clinvar_total", facts("disease", "clinvar_total"))},
            ],
        },
        {
            "title": "依赖 · 成药 · 风险",
            "items": [
                {
                    "label": "强依赖细胞系",
                    "value": f"{format_value('strong_dependency_count', facts('dependency', 'strong_dependency_count'))} / "
                    f"{format_value('n_lines', facts('dependency', 'n_lines'))}",
                },
                {"label": "可成药性", "value": f"{facts('tractability', 'tractable') or '—'} · "
                                              f"{format_value('approved_drug_count', facts('tractability', 'approved_drug_count'))} 药"},
                {"label": "安全事件", "value": format_value("n_safety_liabilities", facts("safety", "n_safety_liabilities"))},
                {"label": "小鼠表型", "value": format_value("n_mouse_phenotypes", facts("safety", "n_mouse_phenotypes"))},
                {"label": "癌症驱动", "value": str(facts("cancer", "driver_status") or "—")},
            ],
        },
    ]

    return {
        "verdict": {"name": name, "subtitle": str(facts("basic", "protein_name") or ""), "line": line, "chips": chips},
        "groups": groups,
    }


def _number_for_summary(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
```

注意：`_summary_view` 中 `basic` 变量只用于判断存在性，可以删除未使用的赋值以通过 lint；若项目无 lint 可保留。

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_render_blocks.py -v`

Expected: 5 passed。

- [ ] **Step 6: 检查点**

Run: `uv run pytest tests/unit/test_render_blocks.py tests/unit/test_chapter_specs.py -q`

Expected: 全部通过。

---

### Task 4: 共享上下文与报告模板

**Files:**
- Modify: `src/target_profile/report/render.py`
- Rewrite: `src/target_profile/report/templates/report.html.j2`
- Test: `tests/unit/test_render.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/unit/test_render.py` 末尾追加：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_render.py -v`

Expected: 新增 3 个测试 FAIL（模板尚未输出 `kpis` / `summary-groups`）。

- [ ] **Step 3: 重构 `render.py` 为共享上下文**

用以下实现替换 `render_report` 函数（保留 `render_print_report` 在 Task 5 添加）：

```python
def _report_thresholds(by_name: dict[str, ModuleResult]) -> dict[str, float]:
    summary = by_name.get("summary")
    values = (summary.facts.get("thresholds") if summary is not None else None) or {}
    return {**DEFAULT_THRESHOLDS, **values}


def _section_chip(blocks: list[dict[str, Any]]) -> dict[str, str] | None:
    if len(blocks) == 1:
        return blocks[0].get("status_chip")
    return None


def build_report_context(
    gene: GeneContext,
    modules: list[ModuleResult],
    *,
    llm_info: dict | None = None,
) -> dict[str, Any]:
    by_name = {module.name: module for module in modules}
    thresholds = _report_thresholds(by_name)
    sections: list[dict[str, Any]] = []
    chart_payload: dict[str, Any] = {}
    summary_view = _summary_view(by_name, thresholds)

    for number, title, names, mode in CHAPTERS:
        if mode == "placeholder":
            sections.append(
                {
                    "id": f"ch-{number}",
                    "number": number,
                    "title": title,
                    "mode": mode,
                    "blocks": [],
                    "missing": False,
                    "status_chip": None,
                    "summary": None,
                }
            )
            continue
        if mode == "summary":
            sections.append(
                {
                    "id": f"ch-{number}",
                    "number": number,
                    "title": title,
                    "mode": mode,
                    "blocks": [],
                    "missing": False,
                    "status_chip": None,
                    "summary": summary_view,
                }
            )
            continue
        present = [by_name[name] for name in names if name in by_name]
        blocks = [_block(module, thresholds) for module in present]
        for block in blocks:
            serialisable = []
            for chart in block["charts"]:
                try:
                    json.dumps(chart["option"], allow_nan=False)
                except (TypeError, ValueError):
                    block["details"]["caveats"].append(
                        f"图表 {chart['id']} 因配置无法序列化已跳过。"
                    )
                    continue
                serialisable.append(chart)
                chart_payload[chart["id"]] = {"title": chart["title"], "option": chart["option"]}
            block["charts"] = serialisable
        sections.append(
            {
                "id": f"ch-{number}",
                "number": number,
                "title": title,
                "mode": mode,
                "blocks": blocks,
                "missing": not present,
                "status_chip": _section_chip(blocks),
                "summary": None,
            }
        )

    missing = [
        f"{SECTION_TITLES.get(module.name, module.name)}：暂无可用数据"
        for module in modules
        if module.status == "no_data" and module.name != "summary"
    ]
    summary = by_name.get("summary")
    thresholds_rows = []
    if summary is not None:
        for key, value in (summary.facts.get("thresholds") or {}).items():
            thresholds_rows.append({"label": THRESHOLD_LABELS.get(key, key), "value": value})

    basic = by_name.get("basic")
    hero_subtitle = (
        (basic.facts.get("approved_name") if basic is not None else None)
        or "单基因靶点全方位画像"
    )
    hero_chips = summary_view["verdict"]["chips"]

    return {
        "gene": gene,
        "hero_subtitle": hero_subtitle,
        "hero_chips": hero_chips,
        "sections": sections,
        "summary_view": summary_view,
        "chart_payload": chart_payload,
        "appendix": {
            "sources": _load_sources(),
            "missing": missing,
            "thresholds": thresholds_rows,
            "llm_text": _llm_text(llm_info),
            "limitations": LIMITATIONS,
        },
        "generated_at": now_iso(),
        "thresholds": thresholds,
    }


def render_report(
    gene: GeneContext,
    modules: list[ModuleResult],
    out_dir: Path,
    *,
    llm_info: dict | None = None,
) -> tuple[Path, Path]:
    context = build_report_context(gene, modules, llm_info=llm_info)
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template("report.html.j2")
    css, dashboard_js, echarts_js = _assets()

    html = template.render(
        **context,
        chart_payload=context["chart_payload"],
        css=css,
        dashboard_js=dashboard_js,
        echarts_js=echarts_js,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / "report.html"
    html_path.write_text(html, encoding="utf-8")

    facts_payload = {
        "gene": {
            "symbol": gene.symbol,
            "ensembl_id": gene.ensembl_id,
            "entrez_id": gene.entrez_id,
            "uniprot_id": gene.uniprot_id,
            "chromosome": gene.chromosome,
            "start": gene.start,
            "end": gene.end,
            "biotype": gene.biotype,
        },
        "generated_at": context["generated_at"],
        "llm": llm_info,
        "modules": {
            module.name: {
                "status": module.status,
                "facts": module.facts,
                "caveats": module.caveats,
                "charts": [spec.id for spec in module.charts],
                "narrative": module.narrative,
                "label_cards": module.label_cards,
            }
            for module in modules
        },
    }
    facts_path = out_dir / "facts.json"
    facts_path.write_text(
        json.dumps(facts_payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return html_path, facts_path
```

同时在 `_block` 末尾把图表写入返回结构：

```python
        "charts": [
            {"id": spec.id, "title": spec.title, "subtitle": spec.subtitle, "option": spec.option}
            for spec in module.charts
        ],
```

（即用该列表替换 Task 3 中 `_block` 的 `"charts": []`。）

并在 `render.py` 的 `CHAPTERS` 中把第 1 章 mode 改为 `"summary"`：

```python
CHAPTERS = [
    (1, "执行摘要", ["summary"], "summary"),
    ...
]
```

- [ ] **Step 4: 重写 `report.html.j2`**

用以下完整内容替换模板文件：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ gene.symbol }} 靶点画像</title>
<style>{{ css | safe }}</style>
</head>
<body>
<div class="bg-grid"></div>
<div class="shell">
  <aside class="toc">
    <div class="toc-brand"><span class="dot"></span>TARGET PROFILE</div>
    <nav>
      {% for section in sections %}
      <a href="#{{ section.id }}"><span class="num">{{ "%02d" | format(section.number) }}</span>{{ section.title }}</a>
      {% endfor %}
      <a href="#appendix"><span class="num">A</span>附录</a>
    </nav>
  </aside>

  <main>
    <header class="hero reveal">
      <div class="eyebrow">TARGET PROFILE · 靶点全方位画像</div>
      <h1>{{ gene.symbol }}</h1>
      <p class="subtitle">{{ hero_subtitle }}</p>
      <div class="hero-chips">
        {% for chip in hero_chips %}
        <span class="chip chip-{{ chip.level }}">{{ chip.text }}</span>
        {% endfor %}
      </div>
      <div class="badges">
        <span class="badge">ENSEMBL · {{ gene.ensembl_id }}</span>
        {% if gene.uniprot_id %}<span class="badge">UNIPROT · {{ gene.uniprot_id }}</span>{% endif %}
        {% if gene.chromosome %}<span class="badge">CHR {{ gene.chromosome }}:{{ gene.start }}-{{ gene.end }}</span>{% endif %}
        <span class="badge">GENERATED · {{ generated_at }}</span>
      </div>
    </header>

    {% for section in sections %}
    <section id="{{ section.id }}" class="reveal">
      <div class="section-head">
        <span class="section-num">{{ "%02d" | format(section.number) }}</span>
        <h2>{{ section.title }}</h2>
        {% if section.status_chip %}
        <span class="chip chip-{{ section.status_chip.level }}">{{ section.status_chip.text }}</span>
        {% endif %}
      </div>

      {% if section.mode == "placeholder" %}
      <p class="placeholder-line">暂未包含：药物基因组学 / 文献 / GWAS 证据将在后续版本提供。</p>

      {% elif section.mode == "summary" %}
      <div class="verdict">
        <div class="verdict-top">
          <h3>{{ section.summary.verdict.name }}</h3>
          {% if section.summary.verdict.subtitle %}<span class="verdict-sub">{{ section.summary.verdict.subtitle }}</span>{% endif %}
        </div>
        {% if section.summary.verdict.line %}<p class="verdict-line">{{ section.summary.verdict.line }}</p>{% endif %}
        <div class="chips">
          {% for chip in section.summary.verdict.chips %}
          <span class="chip chip-{{ chip.level }}">{{ chip.text }}</span>
          {% endfor %}
        </div>
      </div>
      <div class="summary-groups">
        {% for group in section.summary.groups %}
        <div class="summary-group">
          <div class="group-title">{{ group.title }}</div>
          <dl>
            {% for item in group.items %}
            <dt>{{ item.label }}</dt><dd>{{ item.value }}</dd>
            {% endfor %}
          </dl>
        </div>
        {% endfor %}
      </div>

      {% elif section.missing %}
      <div class="panel empty">
        <div class="empty-icon">×</div>
        <p>该章节暂无可用数据。</p>
      </div>

      {% else %}
        {% for block in section.blocks %}
          {% if block.status == "no_data" %}
          <div class="panel empty">
            <div class="empty-icon">×</div>
            <p>暂无可用数据。</p>
            {% for caveat in block.details.caveats %}<p class="caveat">注：{{ caveat }}</p>{% endfor %}
          </div>
          {% else %}
          <div class="block">
            {% if section.blocks | length > 1 %}
            <div class="block-head">
              <h3>{{ block.title }}</h3>
              {% if block.status_chip %}<span class="chip chip-{{ block.status_chip.level }}">{{ block.status_chip.text }}</span>{% endif %}
            </div>
            {% endif %}

            {% if block.kpis %}
            <div class="kpis">
              {% for kpi in block.kpis %}
              <div class="kpi">
                <div class="kpi-label">{{ kpi.label }}</div>
                <div class="kpi-value">{{ kpi.value }}{% if kpi.unit %}<span class="kpi-unit">{{ kpi.unit }}</span>{% endif %}</div>
                {% if kpi.hint %}<div class="kpi-hint">{{ kpi.hint }}</div>{% endif %}
              </div>
              {% endfor %}
            </div>
            {% endif %}

            {% if block.summary %}<p class="narrative">{{ block.summary }}</p>{% endif %}

            {% if block.charts %}
            <div class="chart-grid">
              {% for chart in block.charts %}
              <figure class="panel chart-panel">
                <figcaption>
                  <span class="chart-title">{{ chart.title }}</span>
                  {% if chart.subtitle %}<span class="chart-sub">{{ chart.subtitle }}</span>{% endif %}
                </figcaption>
                <div class="chart" data-chart-id="{{ chart.id }}"></div>
              </figure>
              {% endfor %}
            </div>
            {% endif %}

            {% if block.primary_table %}
            <div class="panel table-panel">
              <h4>{{ block.primary_table.title }}</h4>
              {{ block.primary_table.html | safe }}
            </div>
            {% endif %}

            {% if block.details.tables or block.details.metrics or block.details.full_narrative or block.details.caveats %}
            <details class="details">
              <summary>{{ block.details.summary }}</summary>
              {% if block.details.full_narrative %}
              <p class="narrative">{{ block.details.full_narrative }}</p>
              {% endif %}
              {% for table in block.details.tables %}
              <div class="table-panel inner">
                <h4>{{ table.title }}</h4>
                {{ table.html | safe }}
              </div>
              {% endfor %}
              {% if block.details.metrics %}
              <dl class="metric-list">
                {% for item in block.details.metrics %}
                <dt>{{ item.label }}</dt><dd>{{ item.value }}</dd>
                {% endfor %}
              </dl>
              {% endif %}
              {% for caveat in block.details.caveats %}<p class="caveat">注：{{ caveat }}</p>{% endfor %}
            </details>
            {% endif %}
          </div>
          {% endif %}
        {% endfor %}
      {% endif %}
    </section>
    {% endfor %}

    <section id="appendix" class="reveal">
      <div class="section-head">
        <span class="section-num">A</span>
        <h2>附录</h2>
      </div>
      <div class="panel">
        <h3>数据源与许可</h3>
        <table class="dt">
          <thead><tr><th>来源</th><th>许可</th><th>署名</th></tr></thead>
          <tbody>
          {% for source in appendix.sources %}
          <tr><td>{{ source.name }}</td><td>{{ source.license }}</td><td>{{ source.attribution }}</td></tr>
          {% endfor %}
          </tbody>
        </table>
        <h3>标签阈值（执行摘要）</h3>
        <table class="dt">
          <thead><tr><th>标签</th><th>阈值</th></tr></thead>
          <tbody>
          {% for item in appendix.thresholds %}
          <tr><td>{{ item.label }}</td><td>{{ item.value }}</td></tr>
          {% endfor %}
          </tbody>
        </table>
        <h3>缺失维度</h3>
        {% if appendix.missing %}
        <ul>{% for item in appendix.missing %}<li>{{ item }}</li>{% endfor %}</ul>
        {% else %}
        <p>本次运行所有维度均返回数据。</p>
        {% endif %}
        <h3>LLM 使用情况</h3>
        <p>{{ appendix.llm_text }}</p>
        <h3>方法学局限</h3>
        <ul>{% for item in appendix.limitations %}<li>{{ item }}</li>{% endfor %}</ul>
      </div>
    </section>

    <footer>
      <p>数据来源：GTEx v8、DepMap、HPA、cBioPortal TCGA PanCancer Atlas、Open Targets（Reactome/GO、疾病关联、可成药性、安全性、癌症 hallmark、同源基因）、STRING、UniProt、AlphaFold DB、ClinVar。仅供科研参考，不构成临床诊疗建议。</p>
      <p>图表引擎 ECharts 5.5.1（Apache-2.0）；显示字体 Space Grotesk（SIL OFL 1.1）。报告为自包含单文件，生成后无需联网。</p>
    </footer>
  </main>
</div>
<script id="chart-data" type="application/json">{{ chart_payload | tojson }}</script>
<script>{{ echarts_js | safe }}</script>
<script>{{ dashboard_js | safe }}</script>
</body>
</html>
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_render.py -v`

Expected: 全部通过（含原有结构测试与新增 3 个测试）。若旧测试因 `FACT_LABELS` 移动失败，确认 `render.py` 已从 `chapter_specs` 导入。

- [ ] **Step 6: 运行相关测试**

Run: `uv run pytest tests/unit/test_render.py tests/unit/test_render_blocks.py tests/unit/test_summary.py -q`

Expected: 全部通过。

---

### Task 5: 视觉样式重写（方向 A）

**Files:**
- Rewrite: `src/target_profile/report/static/dashboard.css`
- Verify: `src/target_profile/report/templates/report.html.j2` 类名匹配

- [ ] **Step 1: 写失败检查（结构性）**

创建临时检查脚本 `tests/unit/test_dashboard_css.py`：

```python
from pathlib import Path

CSS = Path(__file__).parents[2] / "src/target_profile/report/static/dashboard.css"


def test_dashboard_has_new_components():
    css = CSS.read_text(encoding="utf-8")
    for token in (".kpis", ".kpi-label", ".kpi-value", ".chip", ".chart-grid",
                  ".details", ".summary-groups", ".placeholder-line", ".metric-list"):
        assert token in css, token
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
    assert "tabular-nums" in css
    assert "__FONT_500_B64__" in css and "__FONT_700_B64__" in css
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_dashboard_css.py -v`

Expected: FAIL（缺少 `.kpis` 等新类）。

- [ ] **Step 3: 重写 `dashboard.css`**

用以下完整内容替换 `src/target_profile/report/static/dashboard.css`（字体占位符必须保留）：

```css
@font-face {
  font-family: "Space Grotesk";
  font-style: normal;
  font-weight: 500;
  font-display: swap;
  src: url(data:font/woff2;base64,__FONT_500_B64__) format("woff2");
}
@font-face {
  font-family: "Space Grotesk";
  font-style: normal;
  font-weight: 700;
  font-display: swap;
  src: url(data:font/woff2;base64,__FONT_700_B64__) format("woff2");
}

:root {
  --bg: #0b1017;
  --bg-2: #0c1118;
  --panel: #121a25;
  --panel-2: #0f1620;
  --line: rgba(130, 160, 190, .18);
  --line-soft: rgba(130, 160, 190, .09);
  --text: #e8eff8;
  --body: #c3d0e0;
  --muted: #8294a9;
  --cyan: #4fd1c5;
  --blue: #6ea8fe;
  --amber: #f0b053;
  --rose: #f27d9a;
  --green: #75d88a;
  --violet: #a78bfa;
  --font-sans: "Space Grotesk", system-ui, -apple-system, "PingFang SC",
    "Noto Sans SC", "Microsoft YaHei", sans-serif;
  --font-mono: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--body);
  font-family: var(--font-sans);
  font-size: 14px;
  line-height: 1.7;
  -webkit-font-smoothing: antialiased;
}
.bg-grid {
  position: fixed; inset: 0; z-index: -1;
  background-image:
    linear-gradient(rgba(110, 168, 254, .04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(110, 168, 254, .04) 1px, transparent 1px),
    radial-gradient(ellipse 60% 40% at 50% 0%, rgba(79, 209, 197, .08), transparent 70%);
  background-size: 40px 40px, 40px 40px, 100% 100%;
}

.shell {
  display: grid;
  grid-template-columns: 230px minmax(0, 1fr);
  gap: 40px;
  max-width: 1400px;
  margin: 0 auto;
  padding: 0 32px;
}
main { max-width: 1080px; padding: 44px 0 72px; min-width: 0; }

/* TOC */
.toc { position: sticky; top: 0; align-self: start; max-height: 100vh; padding: 44px 0 28px; overflow-y: auto; }
.toc-brand { display: flex; align-items: center; gap: 8px; font-family: var(--font-mono); font-size: 11px; letter-spacing: .18em; color: var(--muted); margin-bottom: 20px; }
.toc-brand .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--cyan); box-shadow: 0 0 12px var(--cyan); }
.toc nav { display: flex; flex-direction: column; gap: 2px; }
.toc a { display: flex; align-items: center; gap: 10px; padding: 6px 10px 6px 12px; border-left: 2px solid transparent; color: var(--muted); text-decoration: none; font-size: 13px; transition: color .18s, border-color .18s, background .18s; }
.toc a .num { font-family: var(--font-mono); font-size: 10px; color: rgba(139, 155, 176, .7); }
.toc a:hover { color: var(--text); background: rgba(110, 168, 254, .06); }
.toc a.active { color: var(--text); border-left-color: var(--cyan); background: rgba(79, 209, 197, .07); }

/* Hero */
.hero { padding: 8px 0 32px; border-bottom: 1px solid var(--line); margin-bottom: 40px; }
.eyebrow { font-family: var(--font-mono); font-size: 11px; letter-spacing: .22em; color: var(--cyan); text-transform: uppercase; }
.hero h1 { margin: 6px 0 4px; font-size: clamp(44px, 6vw, 72px); line-height: 1; font-weight: 700; letter-spacing: -.02em; background: linear-gradient(120deg, var(--cyan), var(--blue)); -webkit-background-clip: text; background-clip: text; color: transparent; }
.hero .subtitle { margin: 6px 0 14px; color: var(--muted); font-size: 15px; }
.hero-chips { display: flex; flex-wrap: wrap; gap: 7px; margin-bottom: 14px; }
.badges { display: flex; flex-wrap: wrap; gap: 8px; }
.badge { font-family: var(--font-mono); font-size: 10.5px; color: var(--muted); border: 1px solid var(--line); border-radius: 999px; padding: 4px 11px; background: var(--panel-2); }

/* Sections */
section { margin-bottom: 48px; scroll-margin-top: 24px; }
.section-head { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.section-num { font-family: var(--font-mono); font-size: 11px; color: var(--cyan); border: 1px solid rgba(79, 209, 197, .35); border-radius: 5px; padding: 2px 7px; }
.section-head h2 { margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -.01em; color: var(--text); }
.block + .block { margin-top: 28px; }
.block-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.block-head h3 { margin: 0; font-family: var(--font-mono); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.narrative { margin: 0 0 14px; padding-left: 12px; border-left: 2px solid rgba(79, 209, 197, .45); color: var(--body); font-size: 13.5px; }

/* Chips */
.chip { display: inline-flex; align-items: center; border-radius: 999px; padding: 3px 10px; font-family: var(--font-mono); font-size: 10.5px; border: 1px solid var(--line); color: var(--muted); background: var(--panel-2); }
.chip-ok { color: var(--green); border-color: rgba(117, 216, 138, .35); }
.chip-warn { color: var(--amber); border-color: rgba(240, 176, 83, .38); }
.chip-info { color: var(--blue); border-color: rgba(110, 168, 254, .35); }
.chip-neutral { color: var(--muted); }

/* KPI strip */
.kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); background: var(--panel); border: 1px solid var(--line); border-radius: 9px; padding: 14px; margin-bottom: 14px; }
.kpi { padding: 0 14px; min-width: 0; }
.kpi:first-child { padding-left: 0; }
.kpi + .kpi { border-left: 1px solid var(--line); }
.kpi-label { font-family: var(--font-mono); font-size: 10px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); margin-bottom: 4px; }
.kpi-value { font-size: 26px; font-weight: 650; line-height: 1.25; color: var(--text); letter-spacing: -.02em; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.kpi-unit { font-size: 11px; font-weight: 400; color: var(--muted); margin-left: 3px; }
.kpi-hint { font-size: 10.5px; color: var(--muted); margin-top: 2px; }

/* Panels & charts */
.panel { background: linear-gradient(180deg, var(--panel), var(--panel-2)); border: 1px solid var(--line); border-radius: 9px; padding: 14px 16px; margin-bottom: 12px; }
.chart-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-bottom: 12px; }
.chart-panel { padding: 12px 14px 6px; margin-bottom: 0; }
.chart-panel figcaption { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; margin-bottom: 4px; }
.chart-title { font-size: 11px; font-weight: 700; color: var(--text); font-family: var(--font-mono); }
.chart-sub { font-family: var(--font-mono); font-size: 10.5px; color: var(--muted); }
.chart { width: 100%; height: 300px; min-height: 260px; }
img.chart-snapshot { width: 100%; border-radius: 6px; display: block; }

/* Tables */
.table-panel h4 { margin: 0 0 8px; font-size: 11px; font-weight: 500; color: var(--muted); font-family: var(--font-mono); letter-spacing: .04em; }
.table-panel.inner { background: transparent; border: none; border-top: 1px solid var(--line); border-radius: 0; padding: 12px 0 0; margin: 12px 0 0; }
table.dt { border-collapse: collapse; width: 100%; font-size: 12.5px; }
table.dt th { font-family: var(--font-mono); font-size: 10px; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); text-align: left; padding: 7px 8px; border-bottom: 1px solid var(--line); font-weight: 500; }
table.dt td { padding: 7px 8px; border-bottom: 1px solid var(--line-soft); color: var(--body); vertical-align: top; }
table.dt tbody tr:hover { background: rgba(110, 168, 254, .05); }
table.dt th.num, table.dt td.num { text-align: right; font-variant-numeric: tabular-nums; }
table.dt td.num { font-family: var(--font-mono); }

/* Details & metrics */
.details { margin-top: 10px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel-2); }
.details summary { cursor: pointer; list-style: none; display: flex; align-items: center; gap: 7px; padding: 9px 12px; font-family: var(--font-mono); font-size: 11px; color: var(--cyan); }
.details summary::-webkit-details-marker { display: none; }
.details summary::before { content: "▸"; font-size: 10px; transition: transform .18s; }
.details[open] summary::before { transform: rotate(90deg); }
.details > *:not(summary) { margin-left: 12px; margin-right: 12px; }
.details > :last-child { margin-bottom: 12px; }
.metric-list { display: grid; grid-template-columns: minmax(120px, auto) 1fr; gap: 5px 14px; margin: 10px 12px; font-size: 12px; }
.metric-list dt { color: var(--muted); }
.metric-list dd { margin: 0; color: var(--body); text-align: right; font-variant-numeric: tabular-nums; }

/* Summary */
.verdict { border: 1px solid rgba(79, 209, 197, .25); background: linear-gradient(120deg, rgba(79, 209, 197, .08), rgba(110, 168, 254, .05)); border-radius: 10px; padding: 16px 18px; margin-bottom: 12px; }
.verdict-top { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.verdict h3 { margin: 0; font-size: 24px; color: var(--text); letter-spacing: -.02em; }
.verdict-sub { font-family: var(--font-mono); font-size: 11px; color: var(--muted); }
.verdict-line { margin: 5px 0 10px; font-size: 13px; color: var(--body); }
.chips { display: flex; flex-wrap: wrap; gap: 7px; }
.summary-groups { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.summary-group { background: var(--panel); border: 1px solid var(--line); border-radius: 9px; padding: 12px 14px; }
.group-title { font-family: var(--font-mono); font-size: 10px; letter-spacing: .1em; text-transform: uppercase; color: var(--cyan); margin-bottom: 8px; }
.summary-group dl { margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 5px 10px; font-size: 11.5px; }
.summary-group dt { color: var(--muted); white-space: nowrap; }
.summary-group dd { margin: 0; color: var(--text); text-align: right; }

/* Empty / placeholder / caveat */
.empty { text-align: center; padding: 28px 18px; color: var(--muted); }
.empty-icon { font-size: 22px; opacity: .6; margin-bottom: 6px; }
.placeholder-line { margin: 0; padding: 10px 14px; border-left: 3px solid var(--cyan); background: rgba(79, 209, 197, .06); border-radius: 0 8px 8px 0; color: var(--muted); font-size: 13px; }
.caveat { margin: 10px 0; padding: 9px 14px; font-size: 12px; color: #d9c09a; background: rgba(240, 176, 83, .07); border-left: 3px solid var(--amber); border-radius: 0 8px 8px 0; }

/* Appendix / footer */
#appendix .panel h3 { font-size: 11px; font-family: var(--font-mono); letter-spacing: .08em; text-transform: uppercase; color: var(--muted); margin: 20px 0 8px; }
#appendix .panel h3:first-child { margin-top: 0; }
#appendix ul { margin: 6px 0 0; padding-left: 20px; color: var(--body); font-size: 13px; }
footer { margin-top: 42px; padding-top: 20px; border-top: 1px solid var(--line); color: var(--muted); font-size: 12px; }
footer p { margin: 6px 0; }

/* Motion */
.reveal { opacity: 0; transform: translateY(14px); transition: opacity .5s ease, transform .5s ease; }
.reveal.in { opacity: 1; transform: none; }

/* Responsive */
@media (max-width: 1000px) {
  .shell { display: block; padding: 0 18px; }
  .toc { position: sticky; top: 0; z-index: 10; max-height: none; padding: 10px 0; background: rgba(11, 16, 23, .94); border-bottom: 1px solid var(--line); backdrop-filter: blur(8px); }
  .toc-brand { display: none; }
  .toc nav { flex-direction: row; overflow-x: auto; gap: 0; }
  .toc a { white-space: nowrap; border-left: none; border-bottom: 2px solid transparent; }
  .toc a.active { border-left: none; border-bottom-color: var(--cyan); }
  main { padding-top: 22px; }
  .chart-grid { grid-template-columns: 1fr; }
  .summary-groups { grid-template-columns: 1fr; }
}
@media (max-width: 720px) {
  .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 0; }
  .kpi:nth-child(3) { padding-left: 0; border-left: none; }
  .hero h1 { font-size: 44px; }
}

@media (prefers-reduced-motion: reduce) {
  .reveal { opacity: 1; transform: none; transition: none; }
  html { scroll-behavior: auto; }
}
```

- [ ] **Step 4: 运行测试**

Run: `uv run pytest tests/unit/test_dashboard_css.py -v`

Expected: PASS。

- [ ] **Step 5: 视觉冒烟检查**

Run:

```bash
uv run pytest tests/unit/test_render.py -q
uv run target-profile run EGFR --offline --no-llm --force
```

Expected: 测试通过；`out/EGFR_<date>/report.html` 生成。用浏览器打开确认：KPI 条、双列图、主表、折叠明细、摘要三分组均正常，无横向溢出。

---

### Task 6: PDF 精简模板与渲染函数

**Files:**
- Create: `src/target_profile/report/templates/print.html.j2`
- Create: `src/target_profile/report/static/print-speedread.css`
- Modify: `src/target_profile/report/render.py`
- Test: `tests/unit/test_print_report.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/test_print_report.py`：

```python
from target_profile.models import ChartSpec, GeneContext, ModuleResult
from target_profile.report.chapter_specs import PRINT_CHART_IDS, MODULE_SPECS
from target_profile.report.render import render_print_report


def _ctx():
    return GeneContext(symbol="EGFR", ensembl_id="ENSG00000146648", entrez_id="1956",
                       uniprot_id="P00533", chromosome="7", start=55019017, end=55211628)


def _modules():
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
    for chart_id in PRINT_CHART_IDS:
        owner = next(
            (module for module in modules if chart_id in MODULE_SPECS.get(module.name, MODULE_SPECS["basic"]).primary_charts),
            None,
        )
        if owner is None:
            owner = by_name["basic"]
        owner.charts.append(ChartSpec(id=chart_id, title=chart_titles[chart_id], option={"series": []}))
    return modules


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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_print_report.py -v`

Expected: FAIL，`ImportError: cannot import name 'render_print_report'`。

- [ ] **Step 3: 创建 `print.html.j2`**

创建 `src/target_profile/report/templates/print.html.j2`：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{{ gene.symbol }} 靶点画像 · 精简版</title>
<style>{{ css | safe }}</style>
</head>
<body>
<div class="pdf-page cover-page">
  <div class="page-eyebrow">TARGET PROFILE · 靶点全方位画像</div>
  <h1>{{ gene.symbol }}</h1>
  <p class="lede">{{ summary.verdict.line }}</p>
  <div class="chips">
    {% for chip in summary.verdict.chips %}<span class="chip chip-{{ chip.level }}">{{ chip.text }}</span>{% endfor %}
  </div>
  <div class="kpis">
    {% for kpi in cover_kpis %}
    <div class="kpi">
      <div class="kpi-label">{{ kpi.label }}</div>
      <div class="kpi-value">{{ kpi.value }}{% if kpi.unit %}<span class="kpi-unit">{{ kpi.unit }}</span>{% endif %}</div>
    </div>
    {% endfor %}
  </div>
  <div class="groups">
    {% for group in summary.groups %}
    <div class="group">
      <div class="group-title">{{ group.title }}</div>
      {% for item in group.items %}
      <div class="item"><span>{{ item.label }}</span><b>{{ item.value }}</b></div>
      {% endfor %}
    </div>
    {% endfor %}
  </div>
  <div class="page-num">1 / {{ page_count }}</div>
</div>

<div class="pdf-page">
  <div class="page-head"><h2>维度速览</h2><span class="page-kicker">12 DIMENSIONS</span></div>
  <table class="speed-table">
    <thead><tr><th>维度</th><th>核心指标</th><th class="num">数值</th><th>状态</th></tr></thead>
    <tbody>
    {% for row in speed_rows %}
    <tr><td>{{ row.title }}</td><td>{{ row.metric }}</td><td class="num">{{ row.value }}</td><td>{{ row.status }}</td></tr>
    {% endfor %}
    </tbody>
  </table>
  <div class="page-num">2 / {{ page_count }}</div>
</div>

<div class="pdf-page">
  <div class="page-head"><h2>核心图表 I</h2><span class="page-kicker">CORE EVIDENCE</span></div>
  <div class="chart-grid">
    {% for chart in print_charts[:4] %}
    <figure><figcaption>{{ chart.title }}</figcaption><div class="chart" data-chart-id="{{ chart.id }}"></div></figure>
    {% endfor %}
  </div>
  <div class="page-num">3 / {{ page_count }}</div>
</div>

{% if print_charts | length > 4 %}
<div class="pdf-page">
  <div class="page-head"><h2>核心图表 II</h2><span class="page-kicker">CORE EVIDENCE</span></div>
  <div class="chart-grid">
    {% for chart in print_charts[4:8] %}
    <figure><figcaption>{{ chart.title }}</figcaption><div class="chart" data-chart-id="{{ chart.id }}"></div></figure>
    {% endfor %}
  </div>
  <div class="page-num">4 / {{ page_count }}</div>
</div>
{% endif %}

<div class="pdf-page">
  <div class="page-head"><h2>数据源与局限</h2><span class="page-kicker">METHODS &amp; LICENSES</span></div>
  <h3>数据源与许可</h3>
  <table class="source-table">
    <thead><tr><th>来源</th><th>许可</th><th>署名</th></tr></thead>
    <tbody>
    {% for source in appendix.sources %}
    <tr><td>{{ source.name }}</td><td>{{ source.license }}</td><td>{{ source.attribution }}</td></tr>
    {% endfor %}
    </tbody>
  </table>
  <h3>标签阈值</h3>
  <table class="source-table">
    <thead><tr><th>标签</th><th>阈值</th></tr></thead>
    <tbody>
    {% for item in appendix.thresholds %}
    <tr><td>{{ item.label }}</td><td>{{ item.value }}</td></tr>
    {% endfor %}
    </tbody>
  </table>
  <h3>方法学局限</h3>
  <ul>{% for item in appendix.limitations %}<li>{{ item }}</li>{% endfor %}</ul>
  <h3>LLM 使用情况</h3>
  <p>{{ appendix.llm_text }}</p>
  <div class="page-num">{% if print_charts | length > 4 %}5{% else %}4{% endif %} / {{ page_count }}</div>
</div>

<script id="chart-data" type="application/json">{{ chart_payload | tojson }}</script>
<script>{{ echarts_js | safe }}</script>
<script>{{ dashboard_js | safe }}</script>
</body>
</html>
```

- [ ] **Step 4: 创建 `print-speedread.css`**

创建 `src/target_profile/report/static/print-speedread.css`：

```css
@font-face {
  font-family: "Space Grotesk";
  font-style: normal;
  font-weight: 500;
  font-display: swap;
  src: url(data:font/woff2;base64,__FONT_500_B64__) format("woff2");
}
@font-face {
  font-family: "Space Grotesk";
  font-style: normal;
  font-weight: 700;
  font-display: swap;
  src: url(data:font/woff2;base64,__FONT_700_B64__) format("woff2");
}

@page { size: A4; margin: 12mm; }
* { box-sizing: border-box; }
body {
  margin: 0;
  background: #fffdf8;
  color: #39414d;
  font-family: "Space Grotesk", system-ui, -apple-system, "PingFang SC",
    "Noto Sans SC", "Microsoft YaHei", sans-serif;
  font-size: 8.5px;
  line-height: 1.55;
}
.pdf-page {
  width: 186mm;
  min-height: 273mm;
  padding: 6mm 6mm 10mm;
  background: #fffdf8;
  page-break-after: always;
  position: relative;
  overflow: hidden;
}
.pdf-page:last-child { page-break-after: auto; }
h1 { margin: 4mm 0 1mm; font-size: 34px; line-height: 1; color: #0f6b5c; letter-spacing: -.02em; }
h2 { margin: 0; font-size: 15px; color: #20242c; }
h3 { margin: 4mm 0 1.5mm; font-size: 8px; letter-spacing: .1em; text-transform: uppercase; color: #0f6b5c; }
p { margin: 1mm 0; }
.page-eyebrow { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 7px; letter-spacing: .18em; text-transform: uppercase; color: #0f6b5c; }
.page-head { display: flex; align-items: baseline; justify-content: space-between; border-bottom: 1.5px solid #0f6b5c; padding-bottom: 2mm; margin-bottom: 4mm; }
.page-kicker { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 6.5px; letter-spacing: .14em; color: #7b7365; }
.lede { font-size: 10px; color: #39414d; max-width: 150mm; margin: 2mm 0 3mm; }
.chips { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 4mm; }
.chip { border: 1px solid #e2dbcd; border-radius: 999px; padding: 1px 6px; font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 6.5px; color: #7b7365; }
.chip-ok { color: #0f6b5c; border-color: #b7d8d0; }
.chip-warn { color: #9a5b1e; border-color: #e6c9a8; }
.chip-info { color: #1f4f8f; border-color: #bcd1ee; }
.kpis { display: grid; grid-template-columns: repeat(4, 1fr); border-top: 2px solid #20242c; border-bottom: 1px solid #e2dbcd; padding: 2.5mm 0; margin-bottom: 4mm; }
.kpi { padding: 0 3mm; }
.kpi:first-child { padding-left: 0; }
.kpi + .kpi { border-left: 1px solid #e2dbcd; }
.kpi-label { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 6px; letter-spacing: .08em; text-transform: uppercase; color: #7b7365; }
.kpi-value { font-size: 18px; font-weight: 700; color: #20242c; font-variant-numeric: tabular-nums; }
.kpi-unit { font-size: 7px; font-weight: 400; color: #7b7365; margin-left: 2px; }
.groups { display: grid; grid-template-columns: repeat(3, 1fr); gap: 3mm; }
.group { border: 1px solid #e2dbcd; background: #fff; padding: 2.5mm 3mm; }
.group-title { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 6.5px; letter-spacing: .1em; text-transform: uppercase; color: #0f6b5c; margin-bottom: 1.5mm; }
.item { display: flex; justify-content: space-between; gap: 4px; font-size: 7.5px; padding: 1px 0; border-bottom: 1px dotted #ece6da; }
.item:last-child { border-bottom: none; }
.item span { color: #7b7365; }
.item b { color: #20242c; text-align: right; font-weight: 600; }
.speed-table, .source-table { width: 100%; border-collapse: collapse; font-size: 7.5px; }
.speed-table th, .source-table th { text-align: left; font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 6px; letter-spacing: .08em; text-transform: uppercase; color: #7b7365; border-bottom: 1px solid #20242c; padding: 1.5mm 1mm; }
.speed-table td, .source-table td { padding: 1.6mm 1mm; border-bottom: 1px solid #e2dbcd; vertical-align: top; }
.speed-table th.num, .speed-table td.num { text-align: right; font-variant-numeric: tabular-nums; }
.chart-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4mm; }
.chart-grid figure { margin: 0; border: 1px solid #e2dbcd; background: #fff; padding: 2mm; }
.chart-grid figcaption { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 6.5px; color: #7b7365; margin-bottom: 1mm; }
.chart { width: 100%; height: 52mm; }
img.chart-snapshot { width: 100%; height: 52mm; object-fit: contain; display: block; }
ul { margin: 1mm 0 0; padding-left: 4mm; }
li { margin-bottom: 0.8mm; }
.page-num { position: absolute; bottom: 4mm; right: 6mm; font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 6.5px; color: #7b7365; }
```

- [ ] **Step 5: 在 `render.py` 增加 `render_print_report`**

在 `render.py` 顶部加入常量：

```python
PRINT_CSS_PATH = Path(__file__).parent / "static" / "print-speedread.css"
```

在文件末尾追加：

```python
def _cover_kpis(summary_view: dict[str, Any]) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    for group in summary_view["groups"]:
        for item in group["items"][:2]:
            cards.append({"label": item["label"], "value": item["value"], "unit": ""})
    return cards[:4]


def _speed_rows(sections: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for section in sections:
        for block in section["blocks"]:
            if block["status"] == "no_data" or not block["kpis"]:
                continue
            first = block["kpis"][0]
            status = block["status_chip"]["text"] if block["status_chip"] else ""
            rows.append(
                {
                    "title": section["title"] if len(section["blocks"]) == 1 else block["title"],
                    "metric": first["label"],
                    "value": f"{first['value']}{first['unit']}",
                    "status": status,
                }
            )
    rows.append({"title": "扩展证据", "metric": "PGx / 文献 / GWAS", "value": "后续版本", "status": ""})
    return rows[:12]


def render_print_report(
    gene: GeneContext,
    modules: list[ModuleResult],
    out_dir: Path,
    *,
    llm_info: dict | None = None,
) -> Path:
    context = build_report_context(gene, modules, llm_info=llm_info)
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template("print.html.j2")

    css = PRINT_CSS_PATH.read_text(encoding="utf-8")
    css = css.replace(
        "__FONT_500_B64__", _b64(VENDOR_DIR / "fonts" / "space-grotesk-500.woff2")
    ).replace(
        "__FONT_700_B64__", _b64(VENDOR_DIR / "fonts" / "space-grotesk-700.woff2")
    )
    dashboard_js = (STATIC_DIR / "dashboard.js").read_text(encoding="utf-8")
    echarts_js = (VENDOR_DIR / "echarts.min.js").read_text(encoding="utf-8")

    print_charts = []
    selected_payload = {}
    for chart_id in PRINT_CHART_IDS:
        entry = context["chart_payload"].get(chart_id)
        if entry is None:
            continue
        print_charts.append({"id": chart_id, "title": entry["title"]})
        selected_payload[chart_id] = entry

    page_count = 5 if len(print_charts) > 4 else 4
    html = template.render(
        **context,
        css=css,
        dashboard_js=dashboard_js,
        echarts_js=echarts_js,
        chart_payload=selected_payload,
        print_charts=print_charts,
        cover_kpis=_cover_kpis(context["summary_view"]),
        speed_rows=_speed_rows(context["sections"]),
        page_count=page_count,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "_print.html"
    path.write_text(html, encoding="utf-8")
    return path
```

在 `render.py` 顶部加入导入：

```python
from target_profile.report.chapter_specs import PRINT_CHART_IDS
```

（如果 Task 3 的导入行已存在，直接追加 `PRINT_CHART_IDS`。）

- [ ] **Step 6: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_print_report.py -v`

Expected: 1 passed。若断言 chart 数不是 8，检查 `PRINT_CHART_IDS` 与模块 `primary_charts` 是否对应。

---

### Task 7: CLI PDF 流程

**Files:**
- Modify: `src/target_profile/cli.py:52,245-253`
- Test: `tests/test_cli_run.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/test_cli_run.py` 末尾追加（复用该文件已有的 `_build_home`）：

```python
def test_pdf_uses_speedread_template_and_cleans_up(tmp_path, monkeypatch):
    home = _build_home(tmp_path)
    monkeypatch.setenv("TARGET_PROFILE_HOME", str(home))
    captured = {}

    def fake_pdf(html_path, pdf_path):
        captured["path"] = html_path
        assert html_path.name == "_print.html"
        pdf_path.write_bytes(b"%PDF-1.4\n")
        return True

    monkeypatch.setattr("target_profile.cli.html_to_pdf", fake_pdf)
    result = CliRunner().invoke(app, ["run", "KRAS", "--offline", "--no-llm", "--format", "pdf"])
    assert result.exit_code == 0, result.output
    assert captured["path"].name == "_print.html"
    assert not captured["path"].exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_cli_run.py::test_pdf_uses_speedread_template_and_cleans_up -v`

Expected: FAIL（当前 PDF 使用 `report.html`，且不会清理）。

- [ ] **Step 3: 修改 `cli.py`**

把导入行：

```python
from target_profile.report.render import render_report
```

改为：

```python
from target_profile.report.render import render_print_report, render_report
```

把 PDF 分支：

```python
    if format in {"both", "pdf"}:
        pdf_path = out_dir / "report.pdf"
        if not html_to_pdf(html_path, pdf_path):
            typer.echo("PDF export failed; HTML retained", err=True)
            raise typer.Exit(code=4)
```

改为：

```python
    if format in {"both", "pdf"}:
        pdf_path = out_dir / "report.pdf"
        print_path = render_print_report(ctx, modules, out_dir, llm_info=llm_info)
        try:
            ok = html_to_pdf(print_path, pdf_path)
        finally:
            print_path.unlink(missing_ok=True)
        if not ok:
            typer.echo("PDF export failed; HTML retained", err=True)
            raise typer.Exit(code=4)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_cli_run.py::test_pdf_uses_speedread_template_and_cleans_up -v`

Expected: PASS。

- [ ] **Step 5: 运行 PDF 相关测试**

Run: `uv run pytest tests/test_pdf.py tests/test_cli_run.py -q`

Expected: 全部通过。

---

### Task 8: 全量回归与真实数据验收

**Files:**
- Verify only

- [ ] **Step 1: 运行全量测试**

Run: `uv run pytest -q`

Expected: 全部通过（原 86 个 + 新增测试）。若旧断言失败，逐条确认是结构变化导致，并更新测试而非降低覆盖。

- [ ] **Step 2: 生成四份真实报告**

Run:

```bash
for GENE in EGFR KRAS TP53 TOP1; do
  uv run target-profile run "$GENE" --offline --no-llm --format both --force
done
```

Expected: `out/<GENE>_<date>/` 下存在 `report.html`、`facts.json`、`report.pdf`、`run.log`，且没有 `_print.html` 残留。

- [ ] **Step 3: 检查 PDF 页数**

Run:

```bash
for GENE in EGFR KRAS TP53 TOP1; do
  PDF=$(ls out/${GENE}_*/report.pdf | head -1)
  echo "$GENE: $(pdfinfo "$PDF" | grep Pages)"
done
```

Expected: 每份 4–5 pages。若 `pdfinfo` 不存在，用 Playwright/`pypdf` 手动确认，或记录为已知环境限制。

- [ ] **Step 4: 检查自包含与结构**

Run:

```bash
uv run python - <<'PY'
import re
from pathlib import Path
for path in sorted(Path("out").glob("*/report.html")):
    html = path.read_text(encoding="utf-8")
    assert "data:font/woff2;base64," in html
    assert not re.search(r'(src|href)\s*=\s*["\']https?://', html)
    assert "<details" in html
    assert 'class="kpis"' in html
    print(path, "ok")
PY
```

Expected: 每个 `report.html` 输出 `ok`。

- [ ] **Step 5: 视觉检查**

用 Playwright 截取 EGFR 的「表达」「疾病」「执行摘要」三屏与 PDF 第 1、2 页，确认：

- KPI 条不折行、数值对齐；
- 图表双列无溢出；
- 主表列头中文、数值右对齐；
- 折叠区打开后表格完整；
- 执行摘要三分组高度一致；
- PDF 浅色、5 页以内、无空白页。

- [ ] **Step 6: 最终检查点**

Run: `uv run pytest -q`

Expected: 全部通过。不做 git commit（用户要求）。

---

## 完成定义

- `chapter_specs.py` 覆盖全部 11 个分析模块，表头/格式/状态集中管理。
- 网页默认每章 ≤ 1 张主表（≤ 8 行）+ 1 个折叠明细；全部图表双列保留。
- 执行摘要为结论横幅 + 三分组，不再有卡片墙。
- PDF 为 4–5 页浅色精简版，临时文件自动清理。
- 全量 pytest 通过，真实数据四基因验收通过。
