from __future__ import annotations

import base64
import json
import math
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from target_profile.data_prep.manifest import now_iso
from target_profile.models import GeneContext, ModuleResult
from target_profile.report.chapter_specs import (
    DEFAULT_THRESHOLDS,
    MODULE_SPECS,
    PRINT_CHART_IDS,
    ModuleSpec,
    details_summary,
    format_value,
    kpi_cards,
    metric_rows,
    render_table_html,
    status_chip,
    table_title,
    truncate_text,
)

TEMPLATE_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
VENDOR_DIR = Path(__file__).parent / "vendor"
PRINT_CSS_PATH = Path(__file__).parent / "print.css"
SPEEDREAD_CSS_PATH = Path(__file__).parent / "static" / "print-speedread.css"

CHAPTERS = [
    (1, "执行摘要", ["summary"], "summary"),
    (2, "基因与蛋白基础", ["basic"], "default"),
    (3, "疾病关联与遗传证据", ["disease"], "default"),
    (4, "表达", ["expression"], "default"),
    (5, "突变与变异", ["mutation"], "default"),
    (6, "依赖性与癌症特征", ["dependency", "cancer"], "default"),
    (7, "通路与相互作用", ["pathway"], "default"),
    (8, "蛋白修饰", ["ptm"], "default"),
    (9, "可成药性与药物", ["tractability"], "default"),
    (10, "安全性与风险", ["safety"], "default"),
    (11, "比较基因组学", ["comparative"], "default"),
    (12, "药物基因组学/文献", [], "placeholder"),
]

SECTION_TITLES = {
    "basic": "基因与蛋白基础",
    "disease": "疾病关联与遗传证据",
    "expression": "表达",
    "mutation": "突变与变异",
    "dependency": "依赖性",
    "cancer": "癌症特征",
    "pathway": "通路与相互作用",
    "ptm": "蛋白修饰",
    "tractability": "可成药性与药物",
    "safety": "安全性与风险",
    "comparative": "比较基因组学",
    "summary": "执行摘要",
}

THRESHOLD_LABELS = {
    "tissue_specific_tau": "组织特异 τ 阈值",
    "tissue_partial_tau": "偏特异 τ 下限",
    "pan_cancer_hotspot_pct": "泛癌高频突变阈值 (%)",
    "strong_dependency_effect": "强依赖效应阈值",
    "loeuf_constrained": "强约束 LOEUF 阈值",
}

LIMITATIONS = [
    "本报告基于开放数据源的汇总结果，未经原始实验复现或临床验证。",
    "TCGA 突变率为 PanCancer Atlas 研究的样本级汇总，可能受队列构成影响。",
    "DepMap 依赖性基于细胞系 CRISPR 筛选，体内环境与临床效应可能不同。",
    "可成药性与安全维度天然稀疏；无安全记录不代表安全。",
    "癌症驱动状态为规则推导（泛癌突变率与 Open Targets hallmark），非直接注释。",
    "PTM 位点仅来自 UniProt 人工审阅注释，不代表全部已知修饰。",
    "AlphaFold 结构为计算预测（monomer），pLDDT 仅反映局部置信度；"
    "不得据此推断实验构象、功能位点或临床意义。",
    "PDF 中的图表为交互图的静态快照，不保留 tooltip 与缩放能力。",
]

FALLBACK_SOURCES = [
    {"name": "gtex", "license": "CC BY 4.0", "attribution": "GTEx Consortium"},
    {"name": "depmap", "license": "CC BY 4.0", "attribution": "Broad Institute DepMap"},
    {"name": "hpa", "license": "CC BY 4.0", "attribution": "Human Protein Atlas"},
    {"name": "cbioportal", "license": "Open access TCGA data", "attribution": "cBioPortal / TCGA"},
    {"name": "opentargets", "license": "CC0 1.0", "attribution": "Open Targets Platform"},
    {"name": "uniprot", "license": "CC BY 4.0", "attribution": "UniProt Consortium"},
    {"name": "string", "license": "CC BY 4.0", "attribution": "STRING Consortium"},
    {"name": "clinvar", "license": "Public domain (NCBI)", "attribution": "NCBI ClinVar"},
    {"name": "alphafold", "license": "CC BY 4.0", "attribution": "AlphaFold DB"},
    {"name": "echarts", "license": "Apache-2.0", "attribution": "ECharts contributors"},
    {"name": "space_grotesk", "license": "SIL OFL 1.1", "attribution": "Florian Karsten Typefaces"},
]


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _assets() -> tuple[str, str, str]:
    css = (STATIC_DIR / "dashboard.css").read_text(encoding="utf-8")
    css = css.replace(
        "__FONT_500_B64__", _b64(VENDOR_DIR / "fonts" / "space-grotesk-500.woff2")
    ).replace(
        "__FONT_700_B64__", _b64(VENDOR_DIR / "fonts" / "space-grotesk-700.woff2")
    )
    css = css + "\n" + PRINT_CSS_PATH.read_text(encoding="utf-8")
    js = (STATIC_DIR / "dashboard.js").read_text(encoding="utf-8")
    echarts = (VENDOR_DIR / "echarts.min.js").read_text(encoding="utf-8")
    return css, js, echarts


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
            "links": [],
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
    hidden = set(spec.hidden_tables)
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
        if key in seen or key in hidden or not hasattr(frame, "head") or frame.empty:
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
        "charts": [
            {"id": spec.id, "title": spec.title, "subtitle": spec.subtitle, "option": spec.option}
            for spec in module.charts
        ],
        "kpis": kpi_cards(module),
        "links": list(module.links),
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

    name = str(facts("basic", "approved_name") or "单基因靶点")
    line = str(facts("basic", "function_summary") or facts("basic", "target_class") or "")
    line = truncate_text(line, 120)

    chips = []
    tractable = facts("tractability", "tractable")
    if tractable == "Yes":
        chips.append({"text": "可成药", "level": "ok"})
    elif tractable == "No":
        chips.append({"text": "未证实可成药", "level": "neutral"})
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
    if constrained == "Yes":
        chips.append({"text": "强约束", "level": "info"})
    elif constrained == "No":
        chips.append({"text": "无强约束", "level": "neutral"})
    essential = facts("safety", "common_essential")
    if essential == "Yes":
        chips.append({"text": "泛癌必需", "level": "warn"})

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
                {
                    "label": "可成药性",
                    "value": f"{_summary_tractable(facts('tractability', 'tractable'))} · "
                    f"{format_value('approved_drug_count', facts('tractability', 'approved_drug_count'))} 药",
                },
                {"label": "安全事件", "value": format_value("n_safety_liabilities", facts("safety", "n_safety_liabilities"))},
                {"label": "小鼠表型", "value": format_value("n_mouse_phenotypes", facts("safety", "n_mouse_phenotypes"))},
                {"label": "癌症驱动", "value": str(facts("cancer", "driver_status") or "—")},
            ],
        },
    ]

    af_mean = _number_for_summary(facts("basic", "alphafold_mean_plddt"))
    if af_mean is not None:
        af_value = f"{af_mean:.1f}"
        af_high = _number_for_summary(facts("basic", "alphafold_very_high_pct"))
        if af_high is not None:
            af_value += f" · 高置信 {af_high:.1f}%"
        groups[0]["items"].append({"label": "AlphaFold pLDDT", "value": af_value})

    return {
        "verdict": {"name": name, "subtitle": str(facts("basic", "protein_name") or ""), "line": line, "chips": chips},
        "groups": groups,
    }


def _summary_tractable(value: Any) -> str:
    text = str(value) if value is not None else ""
    return {"Yes": "是", "No": "否"}.get(text, text or "—")


def _number_for_summary(value: Any) -> float | None:
    try:
        number = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    if number is None or math.isnan(number):
        return None
    return number


def _load_sources() -> list[dict[str, str]]:
    import os

    root = Path(os.environ.get("TARGET_PROFILE_HOME", Path.cwd()))
    path = root / "config" / "licenses.yaml"
    if not path.exists():
        return FALLBACK_SOURCES
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sources = data.get("sources") or {}
    if not sources:
        return FALLBACK_SOURCES
    return [
        {
            "name": str(name),
            "license": str(item.get("license") or ""),
            "attribution": str(item.get("attribution") or ""),
        }
        for name, item in sources.items()
    ]


def _llm_text(llm_info: dict | None) -> str:
    if not llm_info:
        return "本次运行使用规则模板生成解读，未调用 LLM。"
    if not llm_info.get("enabled") or not llm_info.get("model"):
        return "本次运行使用规则模板生成解读，未调用 LLM。"
    if llm_info.get("error"):
        return f"LLM 未启用：{llm_info['error']}。解读由规则模板生成。"
    return (
        f"LLM 润色已启用，模型 {llm_info.get('model')}；"
        f"新生成 {llm_info.get('used', 0)} 段，缓存命中 {llm_info.get('cached', 0)} 段，"
        f"守卫拒绝/调用失败后回退模板 {llm_info.get('fallback', 0)} 段。"
    )


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
                "links": module.links,
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


def _cover_kpis(summary_view: dict[str, Any]) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    for group in summary_view["groups"]:
        for item in group["items"][:2]:
            cards.append({"label": item["label"], "value": item["value"]})
    return cards[:4]


def _alphafold_speed_row(block: dict[str, Any]) -> dict[str, str] | None:
    kpis = {item["label"]: item["value"] for item in block["kpis"]}
    mean = kpis.get("平均 pLDDT")
    if not mean:
        return None
    value = mean
    high = kpis.get("高置信残基占比 (≥90)")
    if high:
        value = f"{mean} (高置信 {high})"
    coverage = next(
        (
            item["value"]
            for item in block["details"]["metrics"]
            if item["label"] == "结构覆盖范围"
        ),
        "",
    )
    status = ""
    if coverage:
        pct = coverage.rsplit("(", 1)[-1].rstrip(")") if "(" in coverage else coverage
        status = f"覆盖 {pct}"
    return {
        "title": "结构置信度",
        "metric": "AlphaFold 平均 pLDDT",
        "value": value,
        "status": status,
    }


def _speed_rows(sections: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for section in sections:
        for block in section["blocks"]:
            if block["status"] == "no_data" or not block["kpis"]:
                continue
            first = block["kpis"][0]
            status = block["status_chip"]["text"] if block["status_chip"] else ""
            unit = first["unit"]
            value = f"{first['value']}{unit}"
            if unit and unit[0].isascii() and unit[0].isalpha():
                value = f"{first['value']} {unit}"
            rows.append(
                {
                    "title": section["title"] if len(section["blocks"]) == 1 else block["title"],
                    "metric": first["label"],
                    "value": value,
                    "status": status,
                }
            )
            if block["id"] == "basic":
                af_row = _alphafold_speed_row(block)
                if af_row:
                    rows.append(af_row)
    rows.append({"title": "扩展证据", "metric": "PGx / 文献 / GWAS", "value": "后续版本", "status": ""})
    return rows[:13]


_PRINT_COLOR_MAP = {
    "#8b9bb0": "#7b7365",
    "#c9d6e5": "#39414d",
    "#e7eef7": "#20242c",
    "#0f1620": "#ffffff",
    "rgba(120,160,200,.12)": "rgba(57,65,77,.12)",
    "rgba(120,160,200,.2)": "rgba(57,65,77,.2)",
    "rgba(120,160,200,.25)": "rgba(57,65,77,.25)",
    "rgba(120,160,200,.3)": "rgba(57,65,77,.3)",
}


def _print_option(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _print_option(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_print_option(item) for item in value]
    if isinstance(value, str):
        return _PRINT_COLOR_MAP.get(value, value)
    return value


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

    css = SPEEDREAD_CSS_PATH.read_text(encoding="utf-8")
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
        selected_payload[chart_id] = {"title": entry["title"], "option": _print_option(entry["option"])}

    page_count = 5 if len(print_charts) > 4 else 4
    render_context = {
        **context,
        "chart_payload": selected_payload,
        "summary": context["summary_view"],
    }
    html = template.render(
        **render_context,
        css=css,
        dashboard_js=dashboard_js,
        echarts_js=echarts_js,
        print_charts=print_charts,
        cover_kpis=_cover_kpis(context["summary_view"]),
        speed_rows=_speed_rows(context["sections"]),
        page_count=page_count,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "_print.html"
    path.write_text(html, encoding="utf-8")
    return path
