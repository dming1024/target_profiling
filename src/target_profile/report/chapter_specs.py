"""Presentation metadata for the target profile report."""
from __future__ import annotations

import html
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from target_profile.models import ModuleResult

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
    hidden_tables: tuple[str, ...] = ()


MODULE_SPECS: dict[str, ModuleSpec] = {
    "summary": ModuleSpec(),
    "basic": ModuleSpec(
        kpi=(
            "protein_length",
            "target_class",
            "subcellular_locations",
            "alphafold_mean_plddt",
            "alphafold_very_high_pct",
        ),
        status="target_class",
        secondary_tables=("alphafold_categories",),
        hidden_tables=("alphafold_plddt",),
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
    "alphafold_categories": "AlphaFold 置信度分级",
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
    "alphafold_categories": {"category": "置信度等级", "residues": "残基数", "pct": "占比"},
}

VALUE_LABELS: dict[str, dict[str, str]] = {
    "stage": {
        "Approved": "已批准",
        "Phase 4": "IV 期",
        "Phase 3": "III 期",
        "Phase 2": "II 期",
        "Phase 1": "I 期",
        "Preclinical": "临床前",
        "Unknown": "未知",
        "APPROVAL": "已批准",
        "PHASE_4": "IV 期",
        "PHASE_3": "III 期",
        "PHASE_2": "II 期",
        "PHASE_1": "I 期",
        "PRECLINICAL": "临床前",
        "UNKNOWN": "未知",
    },
    "type": {"ortholog": "直系同源", "within_species_paralog": "种内旁系同源"},
}

KPI_VALUE_LABELS: dict[str, dict[str, str]] = {
    "tractable": {"Yes": "是", "No": "否"},
    "constrained": {"Yes": "是", "No": "否"},
    "common_essential": {"Yes": "是", "No": "否"},
    "essential": {"Yes": "是", "No": "否", "Unknown": "未知"},
    "max_clinical_stage": dict(VALUE_LABELS["stage"]),
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
    "alphafold_very_high_pct": "高置信残基占比 (≥90)",
    "alphafold_confident_pct": "可信残基占比 (70–90)",
    "alphafold_low_pct": "低置信残基占比 (50–70)",
    "alphafold_very_low_pct": "极低置信残基占比 (<50)",
    "alphafold_entry_id": "AlphaFold 模型 ID",
    "alphafold_model_version": "AlphaFold 模型版本",
    "alphafold_coverage": "结构覆盖范围",
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


_PCT_KEYS = {
    "overall_freq_pct", "top_cancer_freq_pct", "pan_cancer_freq_pct",
    "freq_pct", "expression_freq_pct", "pct",
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


def _is_missing_number(value: Any) -> bool:
    return isinstance(value, float) and math.isnan(value)


def format_value(key: str, value: Any) -> str:
    if value is None or value == "":
        return "—"
    if _is_missing_number(value):
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
        value = KPI_VALUE_LABELS.get(key, {}).get(value, value)
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
        value = facts.get("constrained")
        if value == "Yes":
            return _chip("强约束", "info")
        if value == "No":
            return _chip("无强约束", "neutral")
        return None
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
