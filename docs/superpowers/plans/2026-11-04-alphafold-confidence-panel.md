# AlphaFold 结构置信度面板实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在第 2 章增加 AlphaFold 逐残基 pLDDT 曲线与四档置信度分布，并把结构信息提升到 KPI、摘要和 PDF 速览。

**Architecture:** 沿用现有 `api → analysis → figures → report` 分层。`fetch` 阶段多缓存一份逐残基 confidence JSON；`analyze_basic` 产出 facts/表格/链接；`build_basic` 生成两张纯 JSON ECharts 图；`chapter_specs` 与模板负责展示。报告生成保持离线。

**Tech Stack:** Python 3.13、pandas、Typer、Jinja2、ECharts 5.5.1、pytest。

**项目约定：** 用户要求暂不使用 git，因此本计划所有任务**跳过 commit 步骤**；测试与验收以 `uv run pytest` 为准。

**Spec:** `docs/superpowers/specs/2026-11-04-alphafold-confidence-panel-design.md`

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `src/target_profile/api/alphafold.py` | AlphaFold API 与缓存读取 |
| `src/target_profile/cli.py` | fetch 步骤、分析器/图表 builder 注册 |
| `src/target_profile/models.py` | `ModuleResult.links` |
| `src/target_profile/analysis/basic.py` | AlphaFold facts、表格、链接、caveats |
| `src/target_profile/figures/chart_specs.py` | `build_basic` 两张图 |
| `src/target_profile/report/chapter_specs.py` | KPI、标签、隐藏表 |
| `src/target_profile/report/render.py` | links、摘要项、PDF 速览行、局限 |
| `src/target_profile/report/templates/report.html.j2` | 外链行 |
| `src/target_profile/report/static/dashboard.css` | `.block-links` |
| `src/target_profile/report/print.css` | 打印隐藏外链 |

---

### Task 1: AlphaFold 逐残基置信度抓取

**Files:**
- Modify: `src/target_profile/api/alphafold.py`
- Test: `tests/test_api_sources.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_api_sources.py` 顶部导入改为：

```python
from target_profile.api.alphafold import alphafold_confidence, alphafold_prediction
```

在文件末尾追加：

```python
def test_alphafold_confidence_reads_cache(tmp_path):
    global_dir = tmp_path / "_global"
    global_dir.mkdir(parents=True)
    (global_dir / "alphafold_plddt_P01116.json").write_text(
        json.dumps(
            {
                "residueNumber": [1, 2],
                "confidenceScore": [90.0, 91.5],
                "confidenceCategory": ["A", "A"],
            }
        )
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    confidence = alphafold_confidence(
        "P01116",
        {"plddtDocUrl": "https://alphafold.ebi.ac.uk/files/confidence.json"},
        fetcher,
    )
    assert confidence["confidenceScore"] == [90.0, 91.5]


def test_alphafold_confidence_without_url_returns_none(tmp_path):
    fetcher = CachedFetcher(tmp_path, offline=True)
    assert alphafold_confidence("P01116", {}, fetcher) is None
    assert alphafold_confidence(None, None, fetcher) is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_api_sources.py -k alphafold_confidence -v`

Expected: FAIL（`ImportError: cannot import name 'alphafold_confidence'`）

- [ ] **Step 3: 实现**

在 `src/target_profile/api/alphafold.py` 末尾追加：

```python
def alphafold_confidence(
    acc: str | None,
    prediction: dict[str, Any] | None,
    fetcher: CachedFetcher,
    refresh: bool = False,
) -> dict[str, Any] | None:
    """Fetch the per-residue pLDDT document referenced by the prediction entry."""
    if not acc or not prediction:
        return None
    url = prediction.get("plddtDocUrl")
    if not url:
        return None
    return fetcher.request_json(
        f"alphafold_plddt_{acc}",
        "GET",
        url,
        gene="_global",
        refresh=refresh,
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_api_sources.py -v`

Expected: 全部 PASS

---

### Task 2: `ModuleResult.links`

**Files:**
- Modify: `src/target_profile/models.py`

- [ ] **Step 1: 加字段**

```python
@dataclass
class ModuleResult:
    name: str
    status: Literal["ok", "no_data"] = "ok"
    facts: dict[str, Any] = field(default_factory=dict)
    tables: dict[str, Any] = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)
    charts: list[ChartSpec] = field(default_factory=list)
    narrative: str | None = None
    label_cards: list[dict[str, Any]] = field(default_factory=list)
    links: list[dict[str, str]] = field(default_factory=list)

    def degrade(self, reason: str) -> "ModuleResult":
        self.status = "no_data"
        self.caveats.append(reason)
        return self
```

- [ ] **Step 2: 全量测试确认无回归**

Run: `uv run pytest -q`

Expected: 全部 PASS（112 左右）

---

### Task 3: `analyze_basic` 产出结构 facts / 表格 / 链接

**Files:**
- Modify: `src/target_profile/analysis/basic.py`
- Test: `tests/test_basic.py`

- [ ] **Step 1: 更新测试 fixture**

在 `tests/test_basic.py` 的 `_settings` 中，把 AlphaFold 缓存写入替换为：

```python
    (global_dir / "alphafold_P01116.json").write_text(
        json.dumps(
            [
                {
                    "globalMetricValue": 91.5,
                    "fractionPlddtVeryHigh": 0.8,
                    "fractionPlddtConfident": 0.1,
                    "fractionPlddtLow": 0.05,
                    "fractionPlddtVeryLow": 0.05,
                    "entryId": "AF-P01116-F1",
                    "latestVersion": 6,
                    "uniprotStart": 1,
                    "uniprotEnd": 189,
                    "plddtDocUrl": "https://example/confidence.json",
                    "pdbUrl": "https://example/model.pdb",
                    "cifUrl": "https://example/model.cif",
                }
            ]
        )
    )
    (global_dir / "alphafold_plddt_P01116.json").write_text(
        json.dumps(
            {
                "residueNumber": [1, 2, 3, 4, 5],
                "confidenceScore": [90.0, 91.0, 92.0, 93.0, 94.0],
                "confidenceCategory": ["A", "A", "A", "A", "A"],
            }
        )
    )
```

- [ ] **Step 2: 追加失败测试**

在 `tests/test_basic.py` 末尾追加：

```python
def test_basic_alphafold_panel(tmp_path):
    ctx = GeneContext(
        symbol="KRAS",
        ensembl_id="ENSG00000133703",
        uniprot_id="P01116",
    )
    result = analyze_basic(ctx, _settings(tmp_path), offline=True)

    assert result.facts["alphafold_very_high_pct"] == 80.0
    assert result.facts["alphafold_confident_pct"] == 10.0
    assert result.facts["alphafold_low_pct"] == 5.0
    assert result.facts["alphafold_very_low_pct"] == 5.0
    assert result.facts["alphafold_entry_id"] == "AF-P01116-F1"
    assert result.facts["alphafold_model_version"] == "v6"
    assert result.facts["alphafold_coverage"] == "1–189 aa (100%)"

    categories = result.tables["alphafold_categories"]
    assert list(categories["category"])[0] == "Very high (≥90)"
    assert int(categories["residues"].iloc[0]) == 5

    plddt = result.tables["alphafold_plddt"]
    assert list(plddt.columns) == ["residue", "plddt", "category"]
    assert len(plddt) == 5

    labels = {link["label"] for link in result.links}
    assert labels == {"AlphaFold DB", "PDB", "CIF"}
    assert any("单模型逐残基置信度" in caveat for caveat in result.caveats)


def test_basic_alphafold_degrades_without_confidence_doc(tmp_path):
    settings = _settings(tmp_path)
    (tmp_path / "data" / "cache" / "_global" / "alphafold_plddt_P01116.json").unlink()
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703", uniprot_id="P01116")
    result = analyze_basic(ctx, settings, offline=True)

    assert result.status == "ok"
    assert "alphafold_plddt" not in result.tables
    assert result.tables["alphafold_categories"]["residues"].isna().all()
    assert any("逐残基置信度缓存" in caveat for caveat in result.caveats)
```

- [ ] **Step 3: 运行测试确认失败**

Run: `uv run pytest tests/test_basic.py -k alphafold -v`

Expected: FAIL（KeyError / 缺 facts）

- [ ] **Step 4: 实现**

在 `src/target_profile/analysis/basic.py` 中：

1. 导入改为：

```python
import pandas as pd

from target_profile.api.alphafold import alphafold_confidence, alphafold_prediction
from target_profile.api.cache import CachedFetcher
from target_profile.api.opentargets import target_basic
from target_profile.api.uniprot import uniprot_record
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult
```

2. 在 `analyze_basic` 之前加入常量与辅助函数：

```python
CONFIDENCE_CATEGORIES = (
    ("Very high (≥90)", "fractionPlddtVeryHigh", "A", "alphafold_very_high_pct"),
    ("Confident (70–90)", "fractionPlddtConfident", "B", "alphafold_confident_pct"),
    ("Low (50–70)", "fractionPlddtLow", "C", "alphafold_low_pct"),
    ("Very low (<50)", "fractionPlddtVeryLow", "D", "alphafold_very_low_pct"),
)


def _coverage(prediction: dict, protein_length: int | None) -> tuple[str | None, float | None]:
    start = prediction.get("uniprotStart") or prediction.get("sequenceStart")
    end = prediction.get("uniprotEnd") or prediction.get("sequenceEnd")
    if start is None or end is None:
        return None, None
    span = f"{start}–{end} aa"
    if not protein_length:
        return span, None
    pct = (int(end) - int(start) + 1) / int(protein_length) * 100
    return f"{span} ({pct:.0f}%)", pct


def _confidence_tables(
    prediction: dict, confidence: dict | None
) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    counts: dict[str, int] = {}
    if confidence:
        for category in confidence.get("confidenceCategory") or []:
            counts[str(category)] = counts.get(str(category), 0) + 1

    rows = []
    for label, fraction_key, code, _ in CONFIDENCE_CATEGORIES:
        fraction = prediction.get(fraction_key)
        if fraction is None:
            continue
        rows.append(
            {
                "category": label,
                "residues": counts.get(code),
                "pct": round(float(fraction) * 100, 1),
            }
        )
    categories = pd.DataFrame(rows) if rows else None

    plddt = None
    if confidence:
        residues = confidence.get("residueNumber") or []
        scores = confidence.get("confidenceScore") or []
        cats = confidence.get("confidenceCategory") or []
        if residues and len(residues) == len(scores):
            plddt = pd.DataFrame(
                {
                    "residue": [int(value) for value in residues],
                    "plddt": [float(value) for value in scores],
                    "category": list(cats[: len(residues)]) if cats else [""] * len(residues),
                }
            )
    return categories, plddt
```

3. 把现有 AlphaFold 片段：

```python
    try:
        prediction = alphafold_prediction(ctx.uniprot_id, fetcher)
    except Exception:
        prediction = None
    result.facts["alphafold_available"] = "Yes" if prediction else "No"
    if prediction and prediction.get("globalMetricValue") is not None:
        result.facts["alphafold_mean_plddt"] = round(
            float(prediction["globalMetricValue"]), 1
        )
```

替换为：

```python
    try:
        prediction = alphafold_prediction(ctx.uniprot_id, fetcher)
    except Exception:
        prediction = None
    result.facts["alphafold_available"] = "Yes" if prediction else "No"
    if prediction:
        if prediction.get("globalMetricValue") is not None:
            result.facts["alphafold_mean_plddt"] = round(
                float(prediction["globalMetricValue"]), 1
            )
        if prediction.get("entryId"):
            result.facts["alphafold_entry_id"] = prediction["entryId"]
        if prediction.get("latestVersion") is not None:
            result.facts["alphafold_model_version"] = f"v{prediction['latestVersion']}"

        coverage_text, coverage_pct = _coverage(
            prediction, result.facts.get("protein_length")
        )
        if coverage_text:
            result.facts["alphafold_coverage"] = coverage_text

        for _, fraction_key, _, fact_key in CONFIDENCE_CATEGORIES:
            fraction = prediction.get(fraction_key)
            if fraction is not None:
                result.facts[fact_key] = round(float(fraction) * 100, 1)

        confidence = None
        try:
            confidence = alphafold_confidence(ctx.uniprot_id, prediction, fetcher)
        except Exception:
            confidence = None

        categories, plddt = _confidence_tables(prediction, confidence)
        if categories is not None and not categories.empty:
            result.tables["alphafold_categories"] = categories
        if plddt is not None and not plddt.empty:
            result.tables["alphafold_plddt"] = plddt

        if confidence is None:
            result.caveats.append(
                "未找到逐残基置信度缓存，本面板仅展示分段占比；运行 fetch 可补齐。"
            )
        result.caveats.append(
            "AlphaFold pLDDT 是单模型逐残基置信度，不代表实验结构精度或残基功能重要性；"
            "低 pLDDT 不等于无序。"
        )
        if coverage_pct is not None and coverage_pct < 95:
            result.caveats.append(
                f"AlphaFold 模型仅覆盖 UniProt 序列的 {coverage_pct:.0f}%，"
                "未覆盖区域没有结构置信度。"
            )

        links = [
            {
                "label": "AlphaFold DB",
                "url": f"https://alphafold.ebi.ac.uk/entry/{ctx.uniprot_id}",
            }
        ]
        for label, key in (("PDB", "pdbUrl"), ("CIF", "cifUrl")):
            url = prediction.get(key)
            if url:
                links.append({"label": label, "url": url})
        result.links = links
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/test_basic.py -v`

Expected: 全部 PASS

---

### Task 4: `build_basic` 图表

**Files:**
- Modify: `src/target_profile/figures/chart_specs.py`
- Create: `tests/unit/test_chart_specs_alphafold.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/test_chart_specs_alphafold.py`：

```python
import json

import pandas as pd

from target_profile.figures.chart_specs import build_basic
from target_profile.models import ModuleResult


def _result():
    return ModuleResult(
        name="basic",
        facts={
            "alphafold_mean_plddt": 75.1,
            "alphafold_entry_id": "AF-P04637-F1",
            "alphafold_model_version": "v6",
        },
        tables={
            "alphafold_plddt": pd.DataFrame(
                {
                    "residue": [1, 2, 3],
                    "plddt": [90.0, 60.0, 30.0],
                    "category": ["A", "C", "D"],
                }
            ),
            "alphafold_categories": pd.DataFrame(
                {
                    "category": [
                        "Very high (≥90)",
                        "Confident (70–90)",
                        "Low (50–70)",
                        "Very low (<50)",
                    ],
                    "residues": [1, 0, 1, 1],
                    "pct": [52.7, 7.1, 10.4, 29.8],
                }
            ),
        },
    )


def test_build_basic_creates_both_charts():
    charts = build_basic(_result())
    assert [chart.id for chart in charts] == [
        "alphafold-residue",
        "alphafold-confidence",
    ]
    for chart in charts:
        json.dumps(chart.option, allow_nan=False)


def test_residue_chart_has_confidence_bands():
    chart = build_basic(_result())[0]
    series = chart.option["series"][0]
    assert series["data"] == [[1, 90.0], [2, 60.0], [3, 30.0]]
    assert len(series["markArea"]["data"]) == 4
    assert chart.option["yAxis"]["max"] == 100


def test_confidence_chart_uses_category_colors():
    chart = build_basic(_result())[1]
    data = chart.option["series"][0]["data"]
    assert data[0]["name"] == "Very high (≥90)"
    assert data[0]["itemStyle"]["color"] == "#55d6be"


def test_build_basic_returns_empty_without_alphafold_data():
    assert build_basic(ModuleResult(name="basic")) == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_chart_specs_alphafold.py -v`

Expected: FAIL（`ImportError: cannot import name 'build_basic'`）

- [ ] **Step 3: 实现**

在 `src/target_profile/figures/chart_specs.py` 末尾追加：

```python
_AF_BANDS = (
    ("Very high (≥90)", 90, 100, "rgba(85,214,190,.08)"),
    ("Confident (70–90)", 70, 90, "rgba(110,168,254,.07)"),
    ("Low (50–70)", 50, 70, "rgba(240,176,83,.07)"),
    ("Very low (<50)", 0, 50, "rgba(242,125,154,.06)"),
)

_AF_COLORS = {
    "Very high (≥90)": "#55d6be",
    "Confident (70–90)": "#6ea8fe",
    "Low (50–70)": "#f0b053",
    "Very low (<50)": "#f27d9a",
}


def build_basic(result: ModuleResult) -> list[ChartSpec]:
    charts: list[ChartSpec] = []

    plddt = result.tables.get("alphafold_plddt")
    if isinstance(plddt, pd.DataFrame) and not plddt.empty:
        frame = plddt.dropna(subset=["residue", "plddt"])
        data = [
            [int(row.residue), round(float(row.plddt), 1)]
            for row in frame.itertuples(index=False)
        ]
        if data:
            entry = str(result.facts.get("alphafold_entry_id") or "")
            version = str(result.facts.get("alphafold_model_version") or "")
            subtitle = "Source: AlphaFold DB"
            if entry:
                subtitle += f" · {entry}"
            if version:
                subtitle += f" · {version}"
            bands = [
                [
                    {
                        "name": name,
                        "yAxis": high,
                        "itemStyle": {"color": color},
                        "label": {
                            "show": True,
                            "position": "insideTopLeft",
                            "color": "#8b9bb0",
                            "fontSize": 10,
                        },
                    },
                    {"yAxis": low},
                ]
                for name, high, low, color in _AF_BANDS
            ]
            option = {
                "grid": {"left": 48, "right": 16, "top": 30, "bottom": 30, "containLabel": True},
                "tooltip": {"trigger": "axis", "axisPointer": {"type": "line"}},
                "xAxis": {
                    "type": "value",
                    "name": "Residue",
                    "min": 1,
                    "nameTextStyle": {"color": "#8b9bb0"},
                    "axisLabel": {"color": "#8b9bb0"},
                    "splitLine": {"lineStyle": {"color": "rgba(120,160,200,.12)"}},
                },
                "yAxis": {
                    "type": "value",
                    "name": "pLDDT",
                    "min": 0,
                    "max": 100,
                    "nameTextStyle": {"color": "#8b9bb0"},
                    "axisLabel": {"color": "#8b9bb0"},
                    "splitLine": {"lineStyle": {"color": "rgba(120,160,200,.12)"}},
                },
                "series": [
                    {
                        "type": "line",
                        "name": "pLDDT",
                        "data": data,
                        "showSymbol": False,
                        "lineStyle": {"width": 1.6, "color": "#55d6be"},
                        "areaStyle": {
                            "color": {
                                "type": "linear",
                                "x": 0,
                                "y": 0,
                                "x2": 0,
                                "y2": 1,
                                "colorStops": [
                                    {"offset": 0, "color": "rgba(85,214,190,.28)"},
                                    {"offset": 1, "color": "rgba(85,214,190,.02)"},
                                ],
                            }
                        },
                        "markArea": {"silent": True, "data": bands},
                    }
                ],
            }
            charts.append(
                ChartSpec(
                    id="alphafold-residue",
                    title="AlphaFold per-residue pLDDT",
                    subtitle=subtitle,
                    option=option,
                )
            )

    categories = result.tables.get("alphafold_categories")
    if isinstance(categories, pd.DataFrame) and not categories.empty:
        data = [
            {
                "name": str(row.category),
                "value": round(float(row.pct), 1),
                "itemStyle": {"color": _AF_COLORS.get(str(row.category), PALETTE[0])},
            }
            for row in categories.itertuples(index=False)
        ]
        mean = result.facts.get("alphafold_mean_plddt")
        graphic = []
        if mean is not None:
            graphic = [
                {
                    "type": "text",
                    "left": "center",
                    "top": "33%",
                    "style": {
                        "text": f"{float(mean):.1f}",
                        "fill": "#e7eef7",
                        "fontSize": 26,
                        "fontWeight": 700,
                        "textAlign": "center",
                    },
                },
                {
                    "type": "text",
                    "left": "center",
                    "top": "43%",
                    "style": {
                        "text": "mean pLDDT",
                        "fill": "#8b9bb0",
                        "fontSize": 11,
                        "textAlign": "center",
                    },
                },
            ]
        option = {
            "tooltip": {"trigger": "item"},
            "legend": {
                "bottom": 0,
                "textStyle": {"color": "#8b9bb0", "fontSize": 10},
                "itemWidth": 10,
                "itemHeight": 10,
            },
            "graphic": graphic,
            "series": [
                {
                    "type": "pie",
                    "radius": ["52%", "76%"],
                    "center": ["50%", "44%"],
                    "avoidLabelOverlap": True,
                    "label": {
                        "formatter": "{b}\n{c}%",
                        "color": "#c9d6e5",
                        "fontSize": 11,
                    },
                    "labelLine": {"lineStyle": {"color": "rgba(120,160,200,.35)"}},
                    "data": data,
                }
            ],
        }
        charts.append(
            ChartSpec(
                id="alphafold-confidence",
                title="AlphaFold confidence distribution",
                subtitle="Source: AlphaFold DB",
                option=option,
            )
        )

    return charts
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_chart_specs_alphafold.py -v`

Expected: 全部 PASS

---

### Task 5: 注册分析与图表 builder

**Files:**
- Modify: `src/target_profile/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_cli.py` 末尾追加：

```python
def test_basic_module_has_chart_builder():
    from target_profile.cli import BUILDERS, MODULES

    assert any(module.__name__ == "analyze_basic" for module in MODULES)
    assert "basic" in BUILDERS
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_cli.py -k chart_builder -v`

Expected: FAIL（`KeyError` 或断言失败）

- [ ] **Step 3: 实现**

在 `src/target_profile/cli.py` 的 builder 导入中加入 `build_basic`：

```python
from target_profile.figures.chart_specs import (
    build_basic,
    build_cancer,
    build_comparative,
    build_dependency,
    build_disease,
    build_expression,
    build_mutation,
    build_pathway,
    build_ptm,
    build_safety,
    build_tractability,
)
```

在 `BUILDERS` 字典开头加入：

```python
BUILDERS = {
    "basic": build_basic,
    "expression": build_expression,
    ...
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_cli.py -v`

Expected: 全部 PASS

---

### Task 6: 章节标签与 KPI

**Files:**
- Modify: `src/target_profile/report/chapter_specs.py`
- Test: `tests/unit/test_chapter_specs.py`

- [ ] **Step 1: 追加失败测试**

在 `tests/unit/test_chapter_specs.py` 末尾追加：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_chapter_specs.py -k alphafold -v`

Expected: FAIL（KeyError）

- [ ] **Step 3: 实现**

1. `ModuleSpec` 增加字段：

```python
@dataclass(frozen=True)
class ModuleSpec:
    kpi: tuple[str, ...] = ()
    status: str | None = None
    primary_table: str | None = None
    secondary_tables: tuple[str, ...] = ()
    primary_charts: tuple[str, ...] = ()
    table_rows: int = 8
    hidden_tables: tuple[str, ...] = ()
```

2. `MODULE_SPECS["basic"]` 改为：

```python
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
```

3. `TABLE_TITLES` 增加：

```python
    "alphafold_categories": "AlphaFold 置信度分级",
```

4. `COLUMN_LABELS` 增加：

```python
    "alphafold_categories": {"category": "置信度等级", "residues": "残基数", "pct": "占比"},
```

5. `FACT_LABELS` 在 `alphafold_mean_plddt` 之后加入：

```python
    "alphafold_very_high_pct": "高置信残基占比 (≥90)",
    "alphafold_confident_pct": "可信残基占比 (70–90)",
    "alphafold_low_pct": "低置信残基占比 (50–70)",
    "alphafold_very_low_pct": "极低置信残基占比 (<50)",
    "alphafold_entry_id": "AlphaFold 模型 ID",
    "alphafold_model_version": "AlphaFold 模型版本",
    "alphafold_coverage": "结构覆盖范围",
```

6. `_PCT_KEYS` 加入 `"pct"`：

```python
_PCT_KEYS = {
    "overall_freq_pct", "top_cancer_freq_pct", "pan_cancer_freq_pct",
    "freq_pct", "expression_freq_pct", "pct",
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_chapter_specs.py -v`

Expected: 全部 PASS

---

### Task 7: 渲染层（隐藏表、外链、摘要、PDF 速览、局限）

**Files:**
- Modify: `src/target_profile/report/render.py`
- Create: `tests/unit/test_render_alphafold.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/unit/test_render_alphafold.py`：

```python
import pandas as pd

from target_profile.models import GeneContext, ModuleResult
from target_profile.report.render import _speed_rows, build_report_context


def _context():
    gene = GeneContext(
        symbol="TP53",
        ensembl_id="ENSG00000141510",
        uniprot_id="P04637",
    )
    basic = ModuleResult(
        name="basic",
        facts={
            "protein_length": 393,
            "target_class": "Transcription factor",
            "subcellular_locations": "Nucleus",
            "alphafold_mean_plddt": 75.1,
            "alphafold_very_high_pct": 52.7,
            "alphafold_coverage": "1–393 aa (100%)",
        },
        tables={
            "alphafold_categories": pd.DataFrame(
                {"category": ["Very high (≥90)"], "residues": [207], "pct": [52.7]}
            ),
            "alphafold_plddt": pd.DataFrame(
                {"residue": [1], "plddt": [90.0], "category": ["A"]}
            ),
        },
        links=[
            {
                "label": "AlphaFold DB",
                "url": "https://alphafold.ebi.ac.uk/entry/P04637",
            }
        ],
    )
    return build_report_context(gene, [basic])


def test_basic_block_has_links_and_hides_plddt_table():
    context = _context()
    section = next(s for s in context["sections"] if s["id"] == "ch-2")
    block = section["blocks"][0]

    assert block["links"][0]["label"] == "AlphaFold DB"
    table_ids = [table["id"] for table in block["details"]["tables"]]
    assert "alphafold_categories" in table_ids
    assert "alphafold_plddt" not in table_ids


def test_summary_has_alphafold_item():
    context = _context()
    group = next(g for g in context["summary_view"]["groups"] if g["title"] == "靶点定位")
    item = next(item for item in group["items"] if item["label"] == "AlphaFold pLDDT")
    assert item["value"] == "75.1 · 高置信 52.7%"


def test_print_speed_rows_include_structure_row():
    context = _context()
    rows = _speed_rows(context["sections"])
    row = next(row for row in rows if row["title"] == "结构置信度")
    assert "75.100" in row["value"]
    assert "高置信 52.70%" in row["value"]
    assert row["status"] == "覆盖 100%"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_render_alphafold.py -v`

Expected: FAIL（缺 links / 摘要项 / 速览行）

- [ ] **Step 3: 实现**

1. `_block` 的 `no_data` 返回字典加入：

```python
            "links": [],
```

2. `_block` 在读取 spec 之后加入隐藏表集合，并在自动补充明细表时跳过：

```python
    spec = MODULE_SPECS.get(module.name, ModuleSpec())
    hidden = set(spec.hidden_tables)
```

```python
    for key, frame in module.tables.items():
        if key in seen or key in hidden or not hasattr(frame, "head") or frame.empty:
            continue
```

3. `_block` 的 `"ok"` 返回字典加入：

```python
        "links": list(module.links),
```

4. `_summary_view` 在 `groups = [...]` 定义之后、`return` 之前加入：

```python
    af_mean = _number_for_summary(facts("basic", "alphafold_mean_plddt"))
    if af_mean is not None:
        af_value = f"{af_mean:.1f}"
        af_high = _number_for_summary(facts("basic", "alphafold_very_high_pct"))
        if af_high is not None:
            af_value += f" · 高置信 {af_high:.1f}%"
        groups[0]["items"].append({"label": "AlphaFold pLDDT", "value": af_value})
```

5. `LIMITATIONS` 追加：

```python
    "AlphaFold 结构为计算预测（monomer），pLDDT 仅反映局部置信度；"
    "不得据此推断实验构象、功能位点或临床意义。",
```

6. 在 `_speed_rows` 之前加入辅助函数：

```python
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
```

7. `_speed_rows` 循环内，在 `rows.append(...)` 之后加入：

```python
            if block["id"] == "basic":
                af_row = _alphafold_speed_row(block)
                if af_row:
                    rows.append(af_row)
```

并把最后一行改为：

```python
    return rows[:13]
```

8. `facts_payload` 的每个 module 字典加入：

```python
                "links": module.links,
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_render_alphafold.py -v`

Expected: 全部 PASS

---

### Task 8: 模板与样式

**Files:**
- Modify: `src/target_profile/report/templates/report.html.j2`
- Modify: `src/target_profile/report/static/dashboard.css`
- Modify: `src/target_profile/report/print.css`

- [ ] **Step 1: 模板加外链行**

在 `report.html.j2` 的 `{% if block.charts %}...{% endif %}` 之后、`{% if block.primary_table %}` 之前加入：

```jinja
            {% if block.links %}
            <div class="block-links">
              {% for link in block.links %}
              <a href="{{ link.url }}" target="_blank" rel="noopener">{{ link.label }}</a>
              {% endfor %}
            </div>
            {% endif %}
```

- [ ] **Step 2: 仪表盘样式**

在 `dashboard.css` 的 `.chart-panel` 规则之后加入：

```css
.block-links { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0 4px; }
.block-links a {
  font-size: 11px; letter-spacing: .04em; color: #8b9bb0;
  border: 1px solid rgba(120,160,200,.22); border-radius: 6px;
  padding: 4px 9px; text-decoration: none;
  transition: color .2s, border-color .2s;
}
.block-links a:hover { color: #55d6be; border-color: rgba(85,214,190,.45); }
```

- [ ] **Step 3: 打印隐藏**

在 `print.css` 末尾加入：

```css
.block-links { display: none !important; }
```

- [ ] **Step 4: 运行现有测试确认无回归**

Run: `uv run pytest -q`

Expected: 全部 PASS（集成测试可能因现有“禁止 http href”断言失败，进入 Task 9 修正）

---

### Task 9: 集成 fixture 与自包含断言

**Files:**
- Modify: `tests/integration/test_vertical_slice.py`

- [ ] **Step 1: 更新 AlphaFold fixture**

在 `_build_home` 中把：

```python
        (global_dir / f"alphafold_{acc}.json").write_text(
            json.dumps([{"globalMetricValue": 90.0}])
        )
```

替换为：

```python
        (global_dir / f"alphafold_{acc}.json").write_text(
            json.dumps(
                [
                    {
                        "globalMetricValue": 90.0,
                        "fractionPlddtVeryHigh": 0.8,
                        "fractionPlddtConfident": 0.1,
                        "fractionPlddtLow": 0.05,
                        "fractionPlddtVeryLow": 0.05,
                        "entryId": f"AF-{acc}-F1",
                        "latestVersion": 6,
                        "uniprotStart": 1,
                        "uniprotEnd": 189,
                        "plddtDocUrl": f"https://example/{acc}/confidence.json",
                        "pdbUrl": f"https://example/{acc}/model.pdb",
                        "cifUrl": f"https://example/{acc}/model.cif",
                    }
                ]
            )
        )
        (global_dir / f"alphafold_plddt_{acc}.json").write_text(
            json.dumps(
                {
                    "residueNumber": list(range(1, 11)),
                    "confidenceScore": [90.0 + index for index in range(10)],
                    "confidenceCategory": ["A"] * 10,
                }
            )
        )
```

- [ ] **Step 2: 收窄自包含断言**

在 `test_full_chain_offline` 中把：

```python
        assert 'src="http' not in html
        assert 'href="http' not in html
```

替换为：

```python
        assert not re.search(r'<script[^>]+src\s*=\s*["\']https?://', html)
        assert not re.search(r'<link[^>]+href\s*=\s*["\']https?://', html)
```

在 `test_report_is_self_contained` 中把：

```python
    assert not re.search(r'(src|href)\s*=\s*["\']https?://', html)
```

替换为：

```python
    assert not re.search(r'<script[^>]+src\s*=\s*["\']https?://', html)
    assert not re.search(r'<link[^>]+href\s*=\s*["\']https?://', html)
    assert 'rel="noopener"' in html  # AlphaFold 外链存在，但不加载资源
```

- [ ] **Step 3: 增加图表与内容断言**

在 `test_full_chain_offline` 的循环内、`assert facts["modules"]["summary"]["status"] == "ok"` 之后加入：

```python
        assert "alphafold-residue" in html
        assert "alphafold-confidence" in html
        assert "AlphaFold per-residue pLDDT" in html
        assert "AlphaFold 置信度分级" in html
        assert "AlphaFold DB" in html
        assert facts["modules"]["basic"]["facts"]["alphafold_entry_id"] == f"AF-{facts['gene']['uniprot_id']}-F1"
```

注意：若 `uniprot_id` 不在 facts payload 顶层，改用 `acc` 由循环推导；该测试的 fixture 使用 `P01116` / `P04637`，也可直接断言 `facts["modules"]["basic"]["facts"]["alphafold_model_version"] == "v6"`。

- [ ] **Step 4: 运行集成测试**

Run: `uv run pytest tests/integration/test_vertical_slice.py -v`

Expected: 全部 PASS

---

### Task 10: 全量测试与真实数据验收

**Files:** 无代码改动

- [ ] **Step 1: 全量测试**

Run: `uv run pytest -q`

Expected: 全部 PASS，无 warning 失败

- [ ] **Step 2: 刷新真实缓存（联网）**

Run: `uv run target-profile fetch KRAS --refresh && uv run target-profile fetch TP53 --refresh`

Expected: 输出包含：

```text
cached: AlphaFold prediction
cached: AlphaFold confidence
```

- [ ] **Step 3: 离线生成报告**

Run:

```bash
uv run target-profile run KRAS --offline --no-llm --format both --force
uv run target-profile run TP53 --offline --no-llm --format both --force
```

Expected: 退出码 0，产物含 `report.html`、`facts.json`、`report.pdf`、`run.log`。

- [ ] **Step 4: 验收检查**

1. `report.html` 搜索 `AlphaFold per-residue pLDDT`、`AlphaFold confidence distribution`、`高置信残基占比`、`AlphaFold pLDDT` 均存在。
2. `facts.json` 的 `basic.facts` 含平均值、四档占比、entry ID、版本、覆盖度；`basic.links` 长度为 3。
3. `report.pdf` 页数为 5；第 2 页速览表含「结构置信度」行。
4. 无 `_print.html` 残留。
5. 报告中无“结构准确”“高精度”等越界表述。

- [ ] **Step 5: 更新项目记忆**

把本功能的实现状态、缓存键 `alphafold_plddt_<ACC>`、验收结果写入
`/root/.claude/projects/-root-target-profiling/memory/MEMORY.md`。

---

## 自查

### Spec 覆盖

| Spec 章节 | 对应任务 |
|---|---|
| 4 数据流与缓存 | Task 1、Task 3、Task 9 |
| 5 分析层 facts/表格/链接/caveats | Task 2、Task 3 |
| 6.1 KPI | Task 6 |
| 6.2 图表 | Task 4 |
| 6.3 章节装配/隐藏表 | Task 6、Task 7 |
| 6.4 模板与样式 | Task 8 |
| 6.5 执行摘要 | Task 7 |
| 6.6 PDF 速览 | Task 7 |
| 6.7 附录局限 | Task 7 |
| 7 科学口径 | Task 3、Task 7、Task 10 |
| 8 降级与兼容 | Task 1、Task 3、Task 9 |
| 9 测试计划 | Task 1、Task 3、Task 4、Task 6、Task 7、Task 9 |
| 11 验收标准 | Task 10 |

### 占位符扫描

无 TBD/TODO；“实现”步骤均给出完整代码。

### 类型一致性

- 缓存键统一为 `alphafold_plddt_{acc}`。
- facts 键统一以 `alphafold_` 开头。
- 表格键统一为 `alphafold_categories` / `alphafold_plddt`。
- 图表 id 统一为 `alphafold-residue` / `alphafold-confidence`。
