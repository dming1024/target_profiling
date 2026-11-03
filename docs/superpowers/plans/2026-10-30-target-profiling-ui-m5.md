# Target Profiling — UI 改版与 M5 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将报告改为深色、可导航、ECharts 交互式的自包含单文件 HTML，并一次性补齐 M5（癌症特征、比较基因组、执行摘要标签卡、LLM 润色、12 章 + 附录）。

**Architecture:** 分析层继续产出 `ModuleResult`；新增 `figures/chart_specs.py` 只负责把 `tables`/`facts` 转成 JSON 可序列化的 ECharts `option`；`report/render.py` 按固定章节表组装、内联 ECharts/CSS/JS/字体后交给 Jinja 渲染。新增 `analysis/{cancer,comparative,summary}.py` 与 `llm/` 包。matplotlib 报告图全部移除。

**Tech Stack:** Python 3.13、uv、Jinja2、ECharts 5.5.1（vendor 内联）、Space Grotesk woff2（内联）、Playwright（PDF best-effort）。

**Project constraint:** 不使用 git，本计划所有任务不含 commit/branch/PR 步骤；每个任务以「运行目标测试」作为检查点。

---

## 文件结构

新增：

```
src/target_profile/report/vendor/echarts.min.js          # 内联用的 ECharts 5.5.1
src/target_profile/report/vendor/fonts/space-grotesk-500.woff2
src/target_profile/report/vendor/fonts/space-grotesk-700.woff2
src/target_profile/report/static/dashboard.css          # 深色仪表盘样式（含 @font-face 占位符）
src/target_profile/report/static/dashboard.js           # 图表初始化 / 目录高亮 / 快照
src/target_profile/figures/chart_specs.py               # ECharts option builders
src/target_profile/analysis/cancer.py
src/target_profile/analysis/comparative.py
src/target_profile/analysis/summary.py
src/target_profile/llm/__init__.py
src/target_profile/llm/client.py
src/target_profile/llm/cache.py
src/target_profile/llm/guard.py
src/target_profile/llm/prompts.py
tests/unit/test_models.py
tests/unit/test_echarts.py
tests/unit/test_summary.py
tests/unit/test_llm_guard.py
tests/unit/test_llm_pipeline.py
tests/unit/test_cancer.py
tests/unit/test_comparative.py
tests/unit/test_render.py
```

修改：

```
src/target_profile/models.py
src/target_profile/cli.py
src/target_profile/api/opentargets.py
src/target_profile/report/render.py
src/target_profile/report/templates/report.html.j2
src/target_profile/report/print.css
src/target_profile/report/pdf.py
config/licenses.yaml
pyproject.toml
tests/integration/test_vertical_slice.py
tests/test_cli_run.py
tests/test_render.py（旧文件删除，由 tests/unit/test_render.py 取代）
```

移除：

```
src/target_profile/figures/charts.py
src/target_profile/figures/theme.py
tests/test_figures.py
```

---

### Task 1: 扩展数据模型（ChartSpec / ModuleResult）

**Files:**
- Modify: `src/target_profile/models.py`
- Test: `tests/unit/test_models.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_models.py
from target_profile.models import ChartSpec, ModuleResult


def test_chart_spec_defaults():
    spec = ChartSpec(id="expression-gtex", title="GTEx tissue expression")
    assert spec.subtitle == ""
    assert spec.option == {}


def test_chart_spec_is_frozen():
    spec = ChartSpec(id="x", title="X")
    try:
        spec.option = {"a": 1}
    except Exception as exc:
        assert exc.__class__.__name__ == "FrozenInstanceError"
    else:
        raise AssertionError("ChartSpec must be frozen")


def test_module_result_new_fields():
    result = ModuleResult(name="expression")
    assert result.charts == []
    assert result.narrative is None
    assert result.label_cards == []
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/unit/test_models.py`
Expected: FAIL — `ImportError: cannot import name 'ChartSpec'`

- [ ] **Step 3: 实现模型扩展**

```python
# src/target_profile/models.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class GeneContext:
    symbol: str
    ensembl_id: str
    entrez_id: str | None = None
    uniprot_id: str | None = None
    chromosome: str | None = None
    start: int | None = None
    end: int | None = None
    biotype: str | None = None
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChartSpec:
    """A JSON-serialisable ECharts option produced by figures.chart_specs."""

    id: str
    title: str
    subtitle: str = ""
    option: dict[str, Any] = field(default_factory=dict)


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
    figure_paths: list[Path] = field(default_factory=list)  # removed in Task 15

    def degrade(self, reason: str) -> "ModuleResult":
        self.status = "no_data"
        self.caveats.append(reason)
        return self
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest tests/unit/test_models.py`
Expected: 3 passed

---

### Task 2: Vendor 资源（ECharts + 字体 + 许可）

**Files:**
- Create: `src/target_profile/report/vendor/echarts.min.js`
- Create: `src/target_profile/report/vendor/fonts/space-grotesk-500.woff2`
- Create: `src/target_profile/report/vendor/fonts/space-grotesk-700.woff2`
- Modify: `config/licenses.yaml`

- [ ] **Step 1: 创建目录并下载资源**

Run:

```bash
cd /root/target_profiling
mkdir -p src/target_profile/report/vendor/fonts
curl -fsSL -o src/target_profile/report/vendor/echarts.min.js \
  https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js
curl -fsSL -o src/target_profile/report/vendor/fonts/space-grotesk-500.woff2 \
  https://cdn.jsdelivr.net/npm/@fontsource/space-grotesk@5.1.1/files/space-grotesk-latin-500-normal.woff2
curl -fsSL -o src/target_profile/report/vendor/fonts/space-grotesk-700.woff2 \
  https://cdn.jsdelivr.net/npm/@fontsource/space-grotesk@5.1.1/files/space-grotesk-latin-700-normal.woff2
```

Expected: 三个文件均非空（echarts ≈ 1,030,855 bytes；两个字体各 ≈ 13KB）

- [ ] **Step 2: 校验文件完整性与可内联性**

Run:

```bash
wc -c src/target_profile/report/vendor/echarts.min.js \
      src/target_profile/report/vendor/fonts/*.woff2
grep -c "</script" src/target_profile/report/vendor/echarts.min.js || true
head -c 4 src/target_profile/report/vendor/fonts/space-grotesk-500.woff2
```

Expected: echarts 约 1.0MB；字体各约 13KB；grep 输出 `0`；head 输出 `wOF2`

- [ ] **Step 3: 登记许可**

```yaml
# config/licenses.yaml
sources:
  gtex:
    license: CC BY 4.0
    attribution: "GTEx Consortium"
  depmap:
    license: CC BY 4.0
    attribution: "Broad Institute DepMap"
  hpa:
    license: CC BY 4.0
    attribution: "Human Protein Atlas"
  cbioportal:
    license: Open access TCGA data
    attribution: "cBioPortal / TCGA Research Network"
  opentargets:
    license: CC0 1.0 (upstream per-source terms apply)
    attribution: "Open Targets Platform"
  uniprot:
    license: CC BY 4.0
    attribution: "UniProt Consortium"
  string:
    license: CC BY 4.0
    attribution: "STRING Consortium"
  clinvar:
    license: Public domain (NCBI)
    attribution: "NCBI ClinVar"
  alphafold:
    license: CC BY 4.0
    attribution: "AlphaFold Protein Structure Database"
  echarts:
    license: Apache-2.0
    attribution: "Apache Software Foundation / ECharts contributors"
  space_grotesk:
    license: SIL Open Font License 1.1
    attribution: "Florian Karsten Typefaces"
not_for_delivery:
  - DisGeNET
  - OMIM
  - MSigDB
```

- [ ] **Step 4: 检查点（无需测试，确认文件存在）**

Run: `ls -l src/target_profile/report/vendor src/target_profile/report/vendor/fonts`
Expected: 3 个资源文件存在。

---

### Task 3: ECharts builders（expression / mutation / dependency / pathway）

**Files:**
- Create: `src/target_profile/figures/chart_specs.py`
- Test: `tests/unit/test_echarts.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_echarts.py
import json

import pandas as pd

from target_profile.figures.chart_specs import (
    build_dependency,
    build_expression,
    build_mutation,
    build_pathway,
)
from target_profile.models import ModuleResult


def _result(name, tables=None, facts=None):
    result = ModuleResult(name=name)
    result.tables.update(tables or {})
    result.facts.update(facts or {})
    return result


def test_expression_builders():
    result = _result(
        "expression",
        {
            "gtex": pd.DataFrame({"Tissue": ["Lung", "Liver"], "median": [10.0, 2.0]}),
            "depmap_lineage": pd.DataFrame(
                {"OncotreeLineage": ["Lung", "Bowel"], "median": [5.0, 6.0], "count": [10, 8]}
            ),
        },
    )
    specs = build_expression(result)
    assert [spec.id for spec in specs] == ["expression-gtex", "expression-depmap"]
    assert specs[0].option["yAxis"]["data"] == ["Lung", "Liver"]
    assert specs[0].option["series"][0]["data"] == [10.0, 2.0]
    json.dumps(specs[0].option)


def test_expression_empty_state():
    specs = build_expression(_result("expression"))
    assert specs[0].option["graphic"]["style"]["text"] == "No data available"
    assert specs[0].option["series"] == []


def test_mutation_builders():
    result = _result(
        "mutation",
        {
            "cancers": pd.DataFrame(
                {"cancer": ["LUAD", "PAAD"], "freq_pct": [30.0, 60.0]}
            ),
            "protein_changes": pd.DataFrame(
                {"proteinChange": ["G12D", "G12C"], "count": [20, 10]}
            ),
        },
    )
    specs = build_mutation(result)
    assert [spec.id for spec in specs] == ["mutation-cancers", "mutation-proteins"]
    assert specs[0].option["series"][0]["data"] == [30.0, 60.0]
    assert specs[0].option["xAxis"]["axisLabel"]["formatter"] == "{value}%"


def test_dependency_histogram():
    result = _result(
        "dependency",
        {
            "distribution": pd.DataFrame({"effect": [-1.5, -0.5, 0.0, 0.2]}),
            "by_lineage": pd.DataFrame(
                {"OncotreeLineage": ["Lung", "Bowel"], "median": [-0.8, -0.2], "count": [10, 8]}
            ),
        },
    )
    specs = build_dependency(result)
    assert specs[0].id == "dependency-dist"
    assert len(specs[0].option["xAxis"]["data"]) == 30
    assert sum(specs[0].option["series"][0]["data"]) == 4


def test_pathway_graph():
    result = _result(
        "pathway",
        {
            "top_levels": pd.DataFrame(
                {"topLevelTerm": ["Signal Transduction", "Disease"], "count": [36, 24]}
            ),
            "partners": pd.DataFrame(
                {"preferredName_B": ["RAF1", "PIK3CA"], "score": [0.99, 0.95]}
            ),
        },
        {"symbol": "KRAS"},
    )
    specs = build_pathway(result)
    assert specs[1].id == "pathway-network"
    graph = specs[1].option["series"][0]
    assert len(graph["data"]) == 3
    assert len(graph["links"]) == 2
    assert graph["data"][0]["name"] == "KRAS"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/unit/test_echarts.py`
Expected: FAIL — `ModuleNotFoundError: target_profile.figures.chart_specs`

- [ ] **Step 3: 实现 helpers 与 4 个 builder**

```python
# src/target_profile/figures/chart_specs.py
"""Build JSON-serialisable ECharts options from ModuleResult tables/facts."""
from __future__ import annotations

import numpy as np
import pandas as pd

from target_profile.models import ChartSpec, ModuleResult

PALETTE = ["#55d6be", "#6ea8fe", "#f0b053", "#f27d9a", "#75d88a", "#a78bfa"]
GRID = {"left": 8, "right": 64, "top": 20, "bottom": 12, "containLabel": True}


def empty_option(text: str = "No data available") -> dict:
    return {
        "graphic": {
            "type": "text",
            "left": "center",
            "top": "middle",
            "style": {"text": text, "fill": "#8b9bb0", "fontSize": 14},
        },
        "xAxis": {"show": False},
        "yAxis": {"show": False},
        "series": [],
    }


def _barh(categories, values, *, color=PALETTE[0], name="", x_name="", suffix=""):
    axis_label = {"color": "#8b9bb0"}
    if suffix:
        axis_label["formatter"] = "{value}" + suffix
    return {
        "grid": dict(GRID),
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "xAxis": {
            "type": "value",
            "name": x_name,
            "nameTextStyle": {"color": "#8b9bb0"},
            "axisLabel": axis_label,
            "splitLine": {"lineStyle": {"color": "rgba(120,160,200,.12)"}},
        },
        "yAxis": {
            "type": "category",
            "inverse": True,
            "data": list(categories),
            "axisLabel": {"color": "#c9d6e5", "width": 180, "overflow": "truncate"},
            "axisLine": {"lineStyle": {"color": "rgba(120,160,200,.2)"}},
            "splitLine": {"show": False},
        },
        "series": [
            {
                "type": "bar",
                "name": name or x_name,
                "data": list(values),
                "barMaxWidth": 18,
                "itemStyle": {"color": color, "borderRadius": [0, 4, 4, 0]},
            }
        ],
    }


def _bar(categories, values, *, color=PALETTE[1], name="", x_name="", y_name=""):
    return {
        "grid": dict(GRID),
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "xAxis": {
            "type": "category",
            "data": list(categories),
            "axisLabel": {
                "color": "#8b9bb0",
                "width": 96,
                "overflow": "truncate",
                "interval": 0,
                "rotate": 30,
            },
            "axisLine": {"lineStyle": {"color": "rgba(120,160,200,.25)"}},
        },
        "yAxis": {
            "type": "value",
            "name": y_name,
            "nameTextStyle": {"color": "#8b9bb0"},
            "axisLabel": {"color": "#8b9bb0"},
            "splitLine": {"lineStyle": {"color": "rgba(120,160,200,.12)"}},
        },
        "series": [
            {
                "type": "bar",
                "name": name or x_name,
                "data": list(values),
                "barMaxWidth": 26,
                "itemStyle": {"color": color, "borderRadius": [4, 4, 0, 0]},
            }
        ],
    }


def _num(value, default=0.0):
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def build_expression(result: ModuleResult) -> list[ChartSpec]:
    gtex = result.tables.get("gtex")
    if isinstance(gtex, pd.DataFrame) and not gtex.empty:
        top = gtex.dropna(subset=["Tissue", "median"]).head(20)
        option = _barh(
            [str(value) for value in top["Tissue"]],
            [round(_num(value), 3) for value in top["median"]],
            x_name="Median TPM",
        )
    else:
        option = empty_option()
    specs = [
        ChartSpec(
            id="expression-gtex",
            title="GTEx tissue expression",
            subtitle="Source: GTEx v8",
            option=option,
        )
    ]

    lineage = result.tables.get("depmap_lineage")
    if isinstance(lineage, pd.DataFrame) and not lineage.empty:
        top = lineage.dropna(subset=["OncotreeLineage", "median"]).head(12)
        option = _barh(
            [str(value) for value in top["OncotreeLineage"]],
            [round(_num(value), 3) for value in top["median"]],
            color=PALETTE[1],
            x_name="Median log2(TPM+1)",
        )
    else:
        option = empty_option()
    specs.append(
        ChartSpec(
            id="expression-depmap",
            title="DepMap cell-line expression",
            subtitle="Source: DepMap / CCLE",
            option=option,
        )
    )
    return specs


def build_mutation(result: ModuleResult) -> list[ChartSpec]:
    cancers = result.tables.get("cancers")
    if isinstance(cancers, pd.DataFrame) and not cancers.empty:
        top = cancers.dropna(subset=["cancer", "freq_pct"]).head(15)
        option = _barh(
            [str(value) for value in top["cancer"]],
            [round(_num(value), 2) for value in top["freq_pct"]],
            x_name="% mutated samples",
            suffix="%",
        )
    else:
        option = empty_option()
    specs = [
        ChartSpec(
            id="mutation-cancers",
            title="TCGA PanCancer mutation frequency",
            subtitle="Source: cBioPortal / TCGA PanCancer Atlas",
            option=option,
        )
    ]

    proteins = result.tables.get("protein_changes")
    if isinstance(proteins, pd.DataFrame) and not proteins.empty:
        top = proteins.dropna(subset=["proteinChange", "count"]).head(10)
        option = _barh(
            [str(value) for value in top["proteinChange"]],
            [int(_num(value)) for value in top["count"]],
            color=PALETTE[2],
            x_name="Mutation count",
        )
    else:
        option = empty_option()
    specs.append(
        ChartSpec(
            id="mutation-proteins",
            title="Top protein changes",
            subtitle="Source: cBioPortal / TCGA PanCancer Atlas",
            option=option,
        )
    )
    return specs


def build_dependency(result: ModuleResult) -> list[ChartSpec]:
    distribution = result.tables.get("distribution")
    if isinstance(distribution, pd.DataFrame) and not distribution.empty:
        values = distribution["effect"].dropna().to_numpy(dtype=float)
        counts, edges = np.histogram(values, bins=30)
        labels = [f"{edges[index]:.2f}" for index in range(len(counts))]
        option = _bar(
            labels,
            [int(value) for value in counts],
            color=PALETTE[1],
            y_name="Cell lines",
        )
    else:
        option = empty_option()
    specs = [
        ChartSpec(
            id="dependency-dist",
            title="DepMap CRISPR gene effect",
            subtitle="Source: DepMap Chronos; bin = 0.02 effect units",
            option=option,
        )
    ]

    lineage = result.tables.get("by_lineage")
    if isinstance(lineage, pd.DataFrame) and not lineage.empty:
        top = lineage.dropna(subset=["OncotreeLineage", "median"]).head(12)
        option = _barh(
            [str(value) for value in top["OncotreeLineage"]],
            [round(_num(value), 3) for value in top["median"]],
            color=PALETTE[0],
            x_name="Median effect",
        )
    else:
        option = empty_option()
    specs.append(
        ChartSpec(
            id="dependency-lineage",
            title="Dependency by lineage",
            subtitle="Source: DepMap Chronos",
            option=option,
        )
    )
    return specs


def build_pathway(result: ModuleResult) -> list[ChartSpec]:
    levels = result.tables.get("top_levels")
    if isinstance(levels, pd.DataFrame) and not levels.empty:
        top = levels.dropna(subset=["topLevelTerm", "count"]).head(10)
        option = _barh(
            [str(value) for value in top["topLevelTerm"]],
            [int(_num(value)) for value in top["count"]],
            color=PALETTE[5],
            x_name="Pathway count",
        )
    else:
        option = empty_option()
    specs = [
        ChartSpec(
            id="pathway-levels",
            title="Reactome top-level pathways",
            subtitle="Source: Open Targets / Reactome",
            option=option,
        )
    ]

    partners = result.tables.get("partners")
    if isinstance(partners, pd.DataFrame) and not partners.empty:
        symbol = str(result.facts.get("symbol", "TARGET"))
        frame = partners.dropna(subset=["preferredName_B", "score"]).head(30)
        nodes = [
            {
                "name": symbol,
                "symbolSize": 46,
                "itemStyle": {"color": PALETTE[1]},
                "label": {"fontSize": 12},
            }
        ]
        links = []
        for row in frame.itertuples():
            score = _num(row.score)
            name = str(row.preferredName_B)
            nodes.append(
                {
                    "name": name,
                    "symbolSize": round(14 + score * 26, 1),
                    "itemStyle": {"color": PALETTE[0]},
                }
            )
            links.append(
                {
                    "source": symbol,
                    "target": name,
                    "value": round(score, 3),
                    "lineStyle": {
                        "width": round(1 + score * 5, 2),
                        "color": "rgba(110,168,254,.5)",
                    },
                }
            )
        option = {
            "tooltip": {"trigger": "item"},
            "series": [
                {
                    "type": "graph",
                    "layout": "circular",
                    "roam": True,
                    "edgeSymbol": ["none", "none"],
                    "label": {"show": True, "color": "#c9d6e5", "fontSize": 10},
                    "lineStyle": {"curveness": 0.1, "opacity": 0.8},
                    "data": nodes,
                    "links": links,
                }
            ],
        }
    else:
        option = empty_option()
    specs.append(
        ChartSpec(
            id="pathway-network",
            title="STRING interaction partners",
            subtitle="Source: STRING (combined score >= 0.7); edge width ~ score",
            option=option,
        )
    )
    return specs
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest tests/unit/test_echarts.py`
Expected: 5 passed

---

### Task 4: ECharts builders（ptm / disease / tractability / safety / cancer / comparative）

**Files:**
- Modify: `src/target_profile/figures/chart_specs.py`
- Test: `tests/unit/test_echarts.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/unit/test_echarts.py
from target_profile.figures.chart_specs import (
    build_cancer,
    build_comparative,
    build_disease,
    build_ptm,
    build_safety,
    build_tractability,
)


def test_ptm_lollipop_with_domains():
    result = _result(
        "ptm",
        {
            "ptm_types": pd.DataFrame(
                {"type": ["Modified residue", "Lipidation"], "count": [2, 1]}
            ),
            "ptm_sites": pd.DataFrame(
                {
                    "type": ["Modified residue", "Modified residue", "Lipidation"],
                    "position": [104, 186, 186],
                    "end": [104, 186, 186],
                }
            ),
            "domains": pd.DataFrame(
                {"type": ["Region"], "name": ["Hypervariable region"], "start": [166], "end": [185]}
            ),
        },
        {"sequence_length": 189},
    )
    specs = build_ptm(result)
    assert [spec.id for spec in specs] == ["ptm-types", "ptm-sites"]
    assert len(specs[1].option["series"]) == 2
    assert specs[1].option["series"][0]["markArea"]["data"] == [[{"xAxis": 166}, {"xAxis": 185}]]
    assert specs[1].option["xAxis"]["max"] == 191


def test_disease_builders():
    result = _result(
        "disease",
        {
            "diseases": pd.DataFrame(
                {"disease": ["Noonan syndrome", "NSCLC"], "score": [0.83, 0.8]}
            ),
            "datasources": pd.DataFrame(
                {"datasource": ["Genetic association", "Literature"], "diseases": [2, 2]}
            ),
        },
    )
    specs = build_disease(result)
    assert [spec.id for spec in specs] == ["disease-top", "disease-sources"]


def test_tractability_heatmap():
    result = _result(
        "tractability",
        {
            "tractability": pd.DataFrame(
                {
                    "modality": ["Small molecule", "Small molecule", "Antibody"],
                    "bucket": ["Approved Drug", "Structure with Ligand", "Advanced Clinical"],
                    "available": [True, True, True],
                }
            ),
            "drug_stages": pd.DataFrame({"stage": ["Approved", "Phase 2"], "count": [1, 1]}),
        },
    )
    specs = build_tractability(result)
    heatmap = specs[0]
    assert heatmap.id == "tractability-heat"
    assert len(heatmap.option["series"][0]["data"]) == 6  # 2 modalities x 3 buckets
    assert specs[1].id == "tractability-stages"


def test_safety_builders():
    result = _result(
        "safety",
        {
            "mouse_phenotypes": pd.DataFrame(
                {"phenotype_class": ["cardiovascular system phenotype"], "models": [22]}
            ),
            "expression_breadth": pd.DataFrame(
                {"tissue": ["Lung", "Liver"], "median": [12.0, 2.0]}
            ),
        },
    )
    specs = build_safety(result)
    assert [spec.id for spec in specs] == ["safety-mouse", "safety-breadth"]


def test_cancer_hallmarks_stacked():
    result = _result(
        "cancer",
        {
            "hallmarks": pd.DataFrame(
                {
                    "label": ["proliferative signalling", "invasion and metastasis"],
                    "promotes": [2, 1],
                    "suppresses": [0, 1],
                    "total": [2, 2],
                }
            )
        },
    )
    specs = build_cancer(result)
    assert specs[0].id == "cancer-hallmarks"
    assert [series["name"] for series in specs[0].option["series"]] == ["promotes", "suppresses"]
    assert specs[0].option["yAxis"]["data"] == ["proliferative signalling", "invasion and metastasis"]


def test_comparative_identity():
    result = _result(
        "comparative",
        {
            "homologues": pd.DataFrame(
                {
                    "species": ["Chimpanzee", "Mouse"],
                    "type": ["ortholog", "ortholog"],
                    "identity": [99.5, 88.1],
                }
            )
        },
    )
    specs = build_comparative(result)
    assert specs[0].id == "comparative-identity"
    assert specs[0].option["series"][0]["data"] == [99.5, 88.1]
    assert specs[0].option["xAxis"]["axisLabel"]["formatter"] == "{value}%"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/unit/test_echarts.py`
Expected: FAIL — `ImportError: cannot import name 'build_ptm'`

- [ ] **Step 3: 追加实现**

```python
# 追加到 src/target_profile/figures/chart_specs.py


def build_ptm(result: ModuleResult) -> list[ChartSpec]:
    types = result.tables.get("ptm_types")
    if isinstance(types, pd.DataFrame) and not types.empty:
        frame = types.dropna(subset=["type", "count"])
        option = _barh(
            [str(value) for value in frame["type"]],
            [int(_num(value)) for value in frame["count"]],
            color=PALETTE[3],
            x_name="Site count",
        )
    else:
        option = empty_option()
    specs = [
        ChartSpec(
            id="ptm-types",
            title="Curated PTM types",
            subtitle="Source: UniProt (curated features)",
            option=option,
        )
    ]

    sites = result.tables.get("ptm_sites")
    if isinstance(sites, pd.DataFrame) and not sites.empty:
        frame = sites.dropna(subset=["type", "position"])
        categories = list(dict.fromkeys(frame["type"].astype(str)))
        series = []
        for index, category in enumerate(categories):
            subset = frame[frame["type"].astype(str) == category]
            series.append(
                {
                    "type": "scatter",
                    "name": category,
                    "data": [[int(value), index] for value in subset["position"]],
                    "symbolSize": 11,
                    "itemStyle": {"color": PALETTE[index % len(PALETTE)]},
                }
            )
        default_max = int(sites["end"].max()) if "end" in sites else 0
        length = int(_num(result.facts.get("sequence_length"), default_max))
        option = {
            "tooltip": {"trigger": "item"},
            "grid": dict(GRID),
            "xAxis": {
                "type": "value",
                "min": 0,
                "max": length + 2,
                "name": "Residue position",
                "nameTextStyle": {"color": "#8b9bb0"},
                "axisLabel": {"color": "#8b9bb0"},
                "splitLine": {"lineStyle": {"color": "rgba(120,160,200,.12)"}},
            },
            "yAxis": {
                "type": "category",
                "data": categories,
                "axisLabel": {"color": "#c9d6e5", "width": 150, "overflow": "truncate"},
                "axisLine": {"lineStyle": {"color": "rgba(120,160,200,.2)"}},
            },
            "series": series,
        }
        domains = result.tables.get("domains")
        if isinstance(domains, pd.DataFrame) and not domains.empty and series:
            series[0]["markArea"] = {
                "silent": True,
                "itemStyle": {"color": "rgba(110,168,254,.10)"},
                "data": [
                    [{"xAxis": int(row.start)}, {"xAxis": int(row.end)}]
                    for row in domains.itertuples()
                ],
            }
    else:
        option = empty_option()
    specs.append(
        ChartSpec(
            id="ptm-sites",
            title="Curated PTM sites (shaded: domains / regions)",
            subtitle="Source: UniProt (curated features)",
            option=option,
        )
    )
    return specs


def build_disease(result: ModuleResult) -> list[ChartSpec]:
    diseases = result.tables.get("diseases")
    if isinstance(diseases, pd.DataFrame) and not diseases.empty:
        top = diseases.dropna(subset=["disease", "score"]).head(12)
        option = _barh(
            [str(value) for value in top["disease"]],
            [round(_num(value), 3) for value in top["score"]],
            x_name="Open Targets association score",
        )
    else:
        option = empty_option()
    specs = [
        ChartSpec(
            id="disease-top",
            title="Top associated diseases",
            subtitle="Source: Open Targets Platform",
            option=option,
        )
    ]

    sources = result.tables.get("datasources")
    if isinstance(sources, pd.DataFrame) and not sources.empty:
        top = sources.dropna(subset=["datasource", "diseases"]).head(12)
        option = _barh(
            [str(value) for value in top["datasource"]],
            [int(_num(value)) for value in top["diseases"]],
            color=PALETTE[5],
            x_name="Top-ranked diseases with evidence",
        )
    else:
        option = empty_option()
    specs.append(
        ChartSpec(
            id="disease-sources",
            title="Evidence by data source",
            subtitle="Source: Open Targets Platform",
            option=option,
        )
    )
    return specs


def build_tractability(result: ModuleResult) -> list[ChartSpec]:
    frame = result.tables.get("tractability")
    if isinstance(frame, pd.DataFrame) and not frame.empty:
        frame = frame.dropna(subset=["modality", "bucket"])
        modalities = list(dict.fromkeys(frame["modality"].astype(str)))
        buckets = list(dict.fromkeys(frame["bucket"].astype(str)))
        lookup = {
            (str(row.modality), str(row.bucket)): 1 if bool(row.available) else 0
            for row in frame.itertuples()
        }
        data = [
            [x_index, y_index, lookup.get((modality, bucket), 0)]
            for x_index, modality in enumerate(modalities)
            for y_index, bucket in enumerate(buckets)
        ]
        option = {
            "tooltip": {"position": "top"},
            "grid": {
                "left": 8,
                "right": 24,
                "top": 16,
                "bottom": 64,
                "containLabel": True,
            },
            "xAxis": {
                "type": "category",
                "data": modalities,
                "axisLabel": {"color": "#8b9bb0", "interval": 0, "rotate": 20},
                "axisLine": {"lineStyle": {"color": "rgba(120,160,200,.2)"}},
            },
            "yAxis": {
                "type": "category",
                "data": buckets,
                "axisLabel": {"color": "#c9d6e5", "width": 170, "overflow": "truncate"},
                "axisLine": {"lineStyle": {"color": "rgba(120,160,200,.2)"}},
            },
            "visualMap": {
                "min": 0,
                "max": 1,
                "show": False,
                "inRange": {"color": ["#0f1620", "#55d6be"]},
            },
            "series": [
                {
                    "type": "heatmap",
                    "data": data,
                    "label": {"show": True, "formatter": "{c}", "color": "#0b1118"},
                    "itemStyle": {"borderColor": "rgba(8,11,16,.6)", "borderWidth": 2},
                }
            ],
        }
    else:
        option = empty_option()
    specs = [
        ChartSpec(
            id="tractability-heat",
            title="Tractability buckets by modality",
            subtitle="Source: Open Targets Platform; 1 = available",
            option=option,
        )
    ]

    stages = result.tables.get("drug_stages")
    if isinstance(stages, pd.DataFrame) and not stages.empty:
        frame = stages.dropna(subset=["stage", "count"])
        option = _barh(
            [str(value) for value in frame["stage"]],
            [int(_num(value)) for value in frame["count"]],
            color=PALETTE[2],
            x_name="Count",
        )
    else:
        option = empty_option()
    specs.append(
        ChartSpec(
            id="tractability-stages",
            title="Drugs and clinical candidates",
            subtitle="Source: Open Targets Platform",
            option=option,
        )
    )
    return specs


def build_safety(result: ModuleResult) -> list[ChartSpec]:
    phenotypes = result.tables.get("mouse_phenotypes")
    if isinstance(phenotypes, pd.DataFrame) and not phenotypes.empty:
        top = phenotypes.dropna(subset=["phenotype_class", "models"]).head(12)
        option = _barh(
            [str(value) for value in top["phenotype_class"]],
            [int(_num(value)) for value in top["models"]],
            color=PALETTE[3],
            x_name="Models affected",
        )
    else:
        option = empty_option()
    specs = [
        ChartSpec(
            id="safety-mouse",
            title="IMPC mouse phenotypes",
            subtitle="Source: Open Targets / IMPC",
            option=option,
        )
    ]

    breadth = result.tables.get("expression_breadth")
    if isinstance(breadth, pd.DataFrame) and not breadth.empty:
        top = breadth.dropna(subset=["tissue", "median"]).head(15)
        option = _barh(
            [str(value) for value in top["tissue"]],
            [round(_num(value), 3) for value in top["median"]],
            color=PALETTE[1],
            x_name="Median TPM",
        )
    else:
        option = empty_option()
    specs.append(
        ChartSpec(
            id="safety-breadth",
            title="GTEx expression breadth",
            subtitle="Source: GTEx v8",
            option=option,
        )
    )
    return specs


def build_cancer(result: ModuleResult) -> list[ChartSpec]:
    frame = result.tables.get("hallmarks")
    if isinstance(frame, pd.DataFrame) and not frame.empty:
        top = frame.dropna(subset=["label"]).head(12)
        categories = [str(value) for value in top["label"]]
        promotes = [int(_num(value)) for value in top["promotes"]]
        suppresses = [int(_num(value)) for value in top["suppresses"]]
        option = {
            "grid": dict(GRID),
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "legend": {
                "data": ["promotes", "suppresses"],
                "textStyle": {"color": "#8b9bb0"},
                "top": 0,
            },
            "xAxis": {
                "type": "value",
                "axisLabel": {"color": "#8b9bb0"},
                "splitLine": {"lineStyle": {"color": "rgba(120,160,200,.12)"}},
            },
            "yAxis": {
                "type": "category",
                "inverse": True,
                "data": categories,
                "axisLabel": {"color": "#c9d6e5", "width": 200, "overflow": "truncate"},
                "axisLine": {"lineStyle": {"color": "rgba(120,160,200,.2)"}},
            },
            "series": [
                {
                    "type": "bar",
                    "name": "promotes",
                    "stack": "impact",
                    "data": promotes,
                    "barMaxWidth": 18,
                    "itemStyle": {"color": PALETTE[2]},
                },
                {
                    "type": "bar",
                    "name": "suppresses",
                    "stack": "impact",
                    "data": suppresses,
                    "barMaxWidth": 18,
                    "itemStyle": {"color": PALETTE[1]},
                },
            ],
        }
    else:
        option = empty_option()
    return [
        ChartSpec(
            id="cancer-hallmarks",
            title="Cancer hallmarks by impact",
            subtitle="Source: Open Targets Platform; counts of curated hallmark entries",
            option=option,
        )
    ]


def build_comparative(result: ModuleResult) -> list[ChartSpec]:
    frame = result.tables.get("homologues")
    if isinstance(frame, pd.DataFrame) and not frame.empty:
        top = frame.dropna(subset=["species", "identity"]).head(12)
        categories = [
            f"{row.species} · {str(row.type).replace('_', ' ')}" for row in top.itertuples()
        ]
        option = _barh(
            categories,
            [round(_num(value), 2) for value in top["identity"]],
            color=PALETTE[4],
            x_name="Query identity (%)",
            suffix="%",
        )
    else:
        option = empty_option()
    return [
        ChartSpec(
            id="comparative-identity",
            title="Homologue sequence identity",
            subtitle="Source: Open Targets Platform",
            option=option,
        )
    ]
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest tests/unit/test_echarts.py`
Expected: 11 passed

---

### Task 5: 静态资源（dashboard.css / dashboard.js / print.css）

**Files:**
- Create: `src/target_profile/report/static/dashboard.css`
- Create: `src/target_profile/report/static/dashboard.js`
- Modify: `src/target_profile/report/print.css`

- [ ] **Step 1: 写 dashboard.css**

```css
/* src/target_profile/report/static/dashboard.css */
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
  --bg: #080b10;
  --bg-2: #0c1118;
  --panel: #111822;
  --panel-2: #0f1620;
  --line: rgba(120, 160, 200, .14);
  --text: #e7eef7;
  --muted: #8b9bb0;
  --cyan: #55d6be;
  --amber: #f0b053;
  --blue: #6ea8fe;
  --rose: #f27d9a;
  --green: #75d88a;
  --violet: #a78bfa;
  --accent-grad: linear-gradient(120deg, #55d6be, #6ea8fe);
  --font-sans: "Space Grotesk", system-ui, -apple-system, "PingFang SC",
    "Noto Sans SC", "Microsoft YaHei", sans-serif;
  --font-mono: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-sans);
  font-size: 15px;
  line-height: 1.7;
  -webkit-font-smoothing: antialiased;
}
.bg-grid {
  position: fixed;
  inset: 0;
  z-index: -1;
  background-image:
    linear-gradient(rgba(110, 168, 254, .045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(110, 168, 254, .045) 1px, transparent 1px),
    radial-gradient(ellipse 60% 40% at 50% 0%, rgba(85, 214, 190, .10), transparent 70%);
  background-size: 40px 40px, 40px 40px, 100% 100%;
}

.shell {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 42px;
  max-width: 1400px;
  margin: 0 auto;
  padding: 0 32px;
}
main { max-width: 1080px; padding: 48px 0 80px; min-width: 0; }

/* ---------- TOC ---------- */
.toc {
  position: sticky;
  top: 0;
  align-self: start;
  max-height: 100vh;
  padding: 48px 0 32px;
  overflow-y: auto;
}
.toc-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: .18em;
  color: var(--muted);
  margin-bottom: 22px;
}
.toc-brand .dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--cyan);
  box-shadow: 0 0 12px var(--cyan);
}
.toc nav { display: flex; flex-direction: column; gap: 2px; }
.toc a {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 10px 6px 12px;
  border-left: 2px solid transparent;
  color: var(--muted);
  text-decoration: none;
  font-size: 13px;
  transition: color .18s ease, border-color .18s ease, background .18s ease;
}
.toc a .num {
  font-family: var(--font-mono);
  font-size: 10px;
  color: rgba(139, 155, 176, .7);
}
.toc a:hover { color: var(--text); background: rgba(110, 168, 254, .06); }
.toc a.active {
  color: var(--text);
  border-left-color: var(--cyan);
  background: rgba(85, 214, 190, .07);
}

/* ---------- Hero ---------- */
.hero { padding: 12px 0 40px; border-bottom: 1px solid var(--line); margin-bottom: 44px; }
.eyebrow {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: .22em;
  color: var(--cyan);
  text-transform: uppercase;
}
.hero h1 {
  margin: 8px 0 4px;
  font-size: clamp(56px, 9vw, 104px);
  line-height: .95;
  font-weight: 700;
  letter-spacing: -.02em;
  background: var(--accent-grad);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.hero .subtitle { margin: 6px 0 20px; color: var(--muted); font-size: 16px; }
.badges { display: flex; flex-wrap: wrap; gap: 8px; }
.badge {
  font-family: var(--font-mono);
  font-size: 10.5px;
  letter-spacing: .04em;
  color: var(--muted);
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 4px 11px;
  background: var(--panel-2);
}

/* ---------- Sections ---------- */
section { margin-bottom: 54px; scroll-margin-top: 24px; }
.section-head { display: flex; align-items: baseline; gap: 14px; margin-bottom: 18px; }
.section-num {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--cyan);
  border: 1px solid rgba(85, 214, 190, .35);
  border-radius: 6px;
  padding: 1px 7px;
}
.section-head h2 { margin: 0; font-size: 24px; font-weight: 700; letter-spacing: -.01em; }
.block + .block { margin-top: 30px; }
.block > h3 {
  font-size: 14px;
  font-family: var(--font-mono);
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--muted);
  margin: 0 0 12px;
}
.narrative {
  margin: 0 0 18px;
  padding-left: 14px;
  border-left: 2px solid rgba(85, 214, 190, .45);
  color: #cdd9e6;
}

/* ---------- Panels & charts ---------- */
.panel {
  background: linear-gradient(180deg, var(--panel), var(--panel-2));
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 18px 22px;
  margin-bottom: 18px;
}
.chart-panel { padding: 16px 18px 8px; }
.chart-panel figcaption {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}
.chart-title { font-size: 14px; font-weight: 700; color: var(--text); }
.chart-sub { font-family: var(--font-mono); font-size: 10.5px; color: var(--muted); }
.chart { width: 100%; height: min(46vh, 420px); min-height: 280px; }
img.chart-snapshot { width: 100%; border-radius: 10px; display: block; }

/* ---------- Cards ---------- */
.cards { display: grid; gap: 12px; margin: 0 0 18px; }
.cards.g2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.cards.g3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.cards.g4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.card {
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px 14px;
  min-width: 0;
}
.card-label {
  font-family: var(--font-mono);
  font-size: 10.5px;
  letter-spacing: .06em;
  color: var(--muted);
  text-transform: uppercase;
  margin-bottom: 5px;
}
.card-value { font-size: 15px; font-weight: 500; color: var(--text); overflow-wrap: anywhere; }
.card.level-ok { border-color: rgba(117, 216, 138, .34); }
.card.level-ok .card-value { color: var(--green); }
.card.level-warn { border-color: rgba(240, 176, 83, .38); background: rgba(240, 176, 83, .05); }
.card.level-warn .card-value { color: var(--amber); }
.card.level-info .card-value { color: var(--blue); }

/* ---------- Tables ---------- */
.table-panel h4 { margin: 2px 0 10px; font-size: 13px; font-weight: 500; color: var(--muted); }
table.dt, table.facts { border-collapse: collapse; width: 100%; font-size: 13px; }
table.dt th, table.facts th {
  font-family: var(--font-mono);
  font-size: 10.5px;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: var(--muted);
  text-align: left;
  padding: 7px 10px;
  border-bottom: 1px solid var(--line);
  font-weight: 500;
}
table.dt td, table.facts td {
  padding: 7px 10px;
  border-bottom: 1px solid rgba(120, 160, 200, .08);
  color: #c9d6e5;
  vertical-align: top;
}
table.dt tbody tr:hover, table.facts tbody tr:hover { background: rgba(110, 168, 254, .06); }
table.dt td:last-child, table.facts td:last-child { text-align: right; font-family: var(--font-mono); }

/* ---------- Caveat / empty ---------- */
.caveat {
  margin: 10px 0;
  padding: 9px 14px;
  font-size: 12.5px;
  color: #d9c09a;
  background: rgba(240, 176, 83, .07);
  border-left: 3px solid var(--amber);
  border-radius: 0 8px 8px 0;
}
.empty { text-align: center; padding: 40px 20px; color: var(--muted); }
.empty-icon { font-size: 26px; opacity: .6; margin-bottom: 8px; }

/* ---------- Appendix / footer ---------- */
#appendix .panel h3 {
  font-size: 13px;
  font-family: var(--font-mono);
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--muted);
  margin: 22px 0 8px;
}
#appendix .panel h3:first-child { margin-top: 0; }
#appendix ul { margin: 6px 0 0; padding-left: 20px; color: #c9d6e5; font-size: 13.5px; }
footer {
  margin-top: 46px;
  padding-top: 22px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 12px;
}
footer p { margin: 6px 0; }

/* ---------- Motion ---------- */
.reveal { opacity: 0; transform: translateY(14px); transition: opacity .5s ease, transform .5s ease; }
.reveal.in { opacity: 1; transform: none; }

/* ---------- Responsive ---------- */
@media (max-width: 1000px) {
  .shell { display: block; padding: 0 18px; }
  .toc {
    position: sticky;
    top: 0;
    z-index: 10;
    max-height: none;
    padding: 10px 0;
    background: rgba(8, 11, 16, .94);
    border-bottom: 1px solid var(--line);
    backdrop-filter: blur(8px);
  }
  .toc-brand { display: none; }
  .toc nav { flex-direction: row; overflow-x: auto; gap: 0; }
  .toc a { white-space: nowrap; border-left: none; border-bottom: 2px solid transparent; }
  .toc a.active { border-left: none; border-bottom-color: var(--cyan); }
  main { padding-top: 24px; }
  .cards.g3, .cards.g4 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 620px) {
  .cards.g2, .cards.g3, .cards.g4 { grid-template-columns: 1fr; }
  .hero h1 { font-size: 56px; }
}

@media (prefers-reduced-motion: reduce) {
  .reveal { opacity: 1; transform: none; transition: none; }
  html { scroll-behavior: auto; }
}
```

- [ ] **Step 2: 写 dashboard.js**

```javascript
/* src/target_profile/report/static/dashboard.js */
(function () {
  "use strict";

  var dataEl = document.getElementById("chart-data");
  var payload = dataEl ? JSON.parse(dataEl.textContent) : {};
  var palette = ["#55d6be", "#6ea8fe", "#f0b053", "#f27d9a", "#75d88a", "#a78bfa"];

  if (window.echarts) {
    echarts.registerTheme("target", {
      color: palette,
      backgroundColor: "transparent",
      textStyle: {
        color: "#c9d6e5",
        fontFamily: '"Space Grotesk", system-ui, "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif'
      },
      title: { textStyle: { color: "#e7eef7" } },
      tooltip: {
        backgroundColor: "#0f1620",
        borderColor: "rgba(120,160,200,.3)",
        textStyle: { color: "#e7eef7", fontSize: 12 }
      },
      categoryAxis: {
        axisLine: { lineStyle: { color: "rgba(120,160,200,.25)" } },
        axisLabel: { color: "#8b9bb0" },
        splitLine: { show: false }
      },
      valueAxis: {
        axisLine: { show: false },
        axisLabel: { color: "#8b9bb0" },
        splitLine: { lineStyle: { color: "rgba(120,160,200,.12)" } }
      },
      legend: { textStyle: { color: "#8b9bb0" } }
    });
  }

  var charts = [];
  Array.prototype.forEach.call(
    document.querySelectorAll(".chart[data-chart-id]"),
    function (el) {
      var id = el.getAttribute("data-chart-id");
      var entry = payload[id];
      if (!window.echarts || !entry) {
        el.innerHTML = '<div class="empty"><div class="empty-icon">×</div><p>Chart unavailable</p></div>';
        return;
      }
      var chart = echarts.init(el, "target", { renderer: "canvas" });
      chart.setOption(entry.option || {});
      charts.push(chart);
    }
  );

  var resizeTimer = null;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      charts.forEach(function (chart) { chart.resize(); });
    }, 120);
  });

  window.__chartsReady = true;

  window.__snapshotCharts = function () {
    charts.forEach(function (chart) {
      var url = chart.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#0b1118" });
      var img = document.createElement("img");
      img.src = url;
      img.className = "chart-snapshot";
      img.alt = "chart";
      chart.getDom().replaceWith(img);
    });
    charts = [];
  };

  var links = Array.prototype.slice.call(document.querySelectorAll(".toc a[href^='#']"));
  var byId = {};
  links.forEach(function (link) {
    byId[link.getAttribute("href").slice(1)] = link;
  });
  var sections = Array.prototype.slice.call(document.querySelectorAll("section[id]"));

  if ("IntersectionObserver" in window && sections.length) {
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          links.forEach(function (link) { link.classList.remove("active"); });
          var link = byId[entry.target.id];
          if (link) link.classList.add("active");
        });
      },
      { rootMargin: "-18% 0px -72% 0px", threshold: 0 }
    );
    sections.forEach(function (section) { observer.observe(section); });
  }

  var reduceMotion =
    window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var revealTargets = document.querySelectorAll(".reveal");
  if (!reduceMotion && "IntersectionObserver" in window) {
    var revealObserver = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("in");
            revealObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.08 }
    );
    Array.prototype.forEach.call(revealTargets, function (el) { revealObserver.observe(el); });
  } else {
    Array.prototype.forEach.call(revealTargets, function (el) { el.classList.add("in"); });
  }
})();
```

- [ ] **Step 3: 重写 print.css（打印覆盖）**

```css
/* src/target_profile/report/print.css */
@media print {
  @page { size: A4; margin: 14mm 12mm; }
  html, body {
    background: #ffffff !important;
    color: #101820 !important;
    font-size: 11.5px;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  .bg-grid, .toc, .hero .badges { display: none !important; }
  .shell { display: block !important; max-width: none; padding: 0; }
  main { max-width: none; padding: 0; }
  .hero { border-bottom: 1px solid #d6dde6; padding-top: 0; }
  .hero h1 { color: #0f4d43 !important; -webkit-text-fill-color: #0f4d43; background: none; }
  .eyebrow { color: #0f6b5c !important; }
  .hero .subtitle, .badge { color: #475569 !important; }
  .badge { border-color: #d6dde6; background: #f8fafc; }
  section { break-inside: avoid-page; margin-bottom: 26px; }
  .reveal { opacity: 1 !important; transform: none !important; }
  .panel, .card, table.dt, table.facts {
    background: #ffffff !important;
    border-color: #d6dde6 !important;
    box-shadow: none !important;
  }
  .section-num { color: #0f6b5c !important; border-color: #b7d8d0 !important; }
  .section-head h2, .block > h3, .card-value, table.dt td, table.facts td { color: #101820 !important; }
  .card-label, .chart-sub, table.dt th, table.facts th { color: #5b6b7d !important; }
  .narrative { color: #334155 !important; border-left-color: #0f6b5c !important; }
  .caveat { color: #7a4a06 !important; background: #fff8ea !important; border-left-color: #c98a12 !important; }
  .chart-panel, .chart, img.chart-snapshot { break-inside: avoid; page-break-inside: avoid; }
  .chart { display: none !important; }
  img.chart-snapshot { width: 100%; margin: 4px 0; }
  footer { color: #5b6b7d !important; border-top-color: #d6dde6 !important; }
}
```

- [ ] **Step 4: 检查点**

Run: `ls -l src/target_profile/report/static src/target_profile/report/print.css`
Expected: 两个新文件存在，print.css 已更新。

---

### Task 6: 渲染管线重写（12 章 / 内联资源 / 附录）

**Files:**
- Modify: `src/target_profile/report/render.py`
- Modify: `src/target_profile/report/templates/report.html.j2`
- Delete: `tests/test_render.py`
- Create: `tests/unit/test_render.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_render.py
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/unit/test_render.py`
Expected: FAIL — `TypeError: render_report() got an unexpected keyword argument 'llm_info'`

- [ ] **Step 3: 重写 render.py**

```python
# src/target_profile/report/render.py
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from target_profile.data_prep.manifest import now_iso
from target_profile.models import GeneContext, ModuleResult

TEMPLATE_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
VENDOR_DIR = Path(__file__).parent / "vendor"
PRINT_CSS_PATH = Path(__file__).parent / "print.css"

CHAPTERS = [
    (1, "执行摘要", ["summary"], "cards"),
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

FACT_LABELS = {
    "symbol": "基因符号",
    "ensembl_id": "Ensembl ID",
    "biotype": "基因类型",
    "tau": "组织特异性 τ",
    "gtex_top_tissue": "最高表达组织",
    "gtex_top_median_tpm": "最高组织中位 TPM",
    "gtex_tissue_count": "GTEx 组织数",
    "gtex_mean_percentile": "平均组织内百分位",
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
    "n_label_cards": "标签卡数量",
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


def _table_html(df, max_rows: int = 20) -> str:
    return df.head(max_rows).to_html(index=False, classes="dt", border=0, escape=True)


def _block(module: ModuleResult) -> dict[str, Any]:
    title = SECTION_TITLES.get(module.name, module.name)
    if module.status == "no_data":
        return {
            "id": module.name,
            "title": title,
            "status": "no_data",
            "narrative": None,
            "charts": [],
            "fact_rows": [],
            "tables": [],
            "caveats": module.caveats,
            "label_cards": [],
        }
    fact_rows = [
        {"label": FACT_LABELS.get(key, key), "value": value}
        for key, value in module.facts.items()
        if key not in {"symbol", "thresholds"}
    ]
    tables = [
        {"title": key.replace("_", " "), "html": _table_html(df)}
        for key, df in module.tables.items()
        if hasattr(df, "head")
    ]
    charts = [
        {"id": spec.id, "title": spec.title, "subtitle": spec.subtitle, "option": spec.option}
        for spec in module.charts
    ]
    return {
        "id": module.name,
        "title": title,
        "status": "ok",
        "narrative": module.narrative,
        "charts": charts,
        "fact_rows": fact_rows,
        "tables": tables,
        "caveats": module.caveats,
        "label_cards": module.label_cards,
    }


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


def render_report(
    gene: GeneContext,
    modules: list[ModuleResult],
    out_dir: Path,
    *,
    llm_info: dict | None = None,
) -> tuple[Path, Path]:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template("report.html.j2")
    by_name = {module.name: module for module in modules}

    sections: list[dict[str, Any]] = []
    chart_payload: dict[str, Any] = {}
    for number, title, names, mode in CHAPTERS:
        present = [by_name[name] for name in names if name in by_name]
        if mode == "placeholder":
            sections.append(
                {
                    "id": f"ch-{number}",
                    "number": number,
                    "title": title,
                    "mode": mode,
                    "blocks": [],
                    "missing": False,
                }
            )
            continue
        blocks = [_block(module) for module in present]
        for block in blocks:
            for chart in block["charts"]:
                chart_payload[chart["id"]] = {
                    "title": chart["title"],
                    "option": chart["option"],
                }
        sections.append(
            {
                "id": f"ch-{number}",
                "number": number,
                "title": title,
                "mode": mode,
                "blocks": blocks,
                "missing": (not present) or all(m.status == "no_data" for m in present),
            }
        )

    missing = [
        f"{SECTION_TITLES.get(module.name, module.name)}：暂无可用数据"
        for module in modules
        if module.status == "no_data" and module.name != "summary"
    ]
    summary = by_name.get("summary")
    thresholds = []
    if summary is not None:
        for key, value in (summary.facts.get("thresholds") or {}).items():
            thresholds.append(
                {"label": THRESHOLD_LABELS.get(key, key), "value": value}
            )

    basic = by_name.get("basic")
    hero_subtitle = (
        (basic.facts.get("approved_name") if basic is not None else None)
        or "单基因靶点全方位画像"
    )

    css, dashboard_js, echarts_js = _assets()
    appendix = {
        "sources": _load_sources(),
        "missing": missing,
        "thresholds": thresholds,
        "llm_text": _llm_text(llm_info),
        "limitations": LIMITATIONS,
    }

    html = template.render(
        gene=gene,
        hero_subtitle=hero_subtitle,
        sections=sections,
        appendix=appendix,
        chart_payload=chart_payload,
        css=css,
        dashboard_js=dashboard_js,
        echarts_js=echarts_js,
        generated_at=now_iso(),
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
        "generated_at": now_iso(),
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

- [ ] **Step 4: 重写模板**

```html
<!-- src/target_profile/report/templates/report.html.j2 -->
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
      </div>

      {% if section.mode == "placeholder" %}
      <div class="panel empty">
        <div class="empty-icon">⌁</div>
        <p>暂未包含：药物基因组学与文献维度属于后续版本（Tier 3），当前版本不提供该章节数据。</p>
      </div>

      {% elif section.missing %}
      <div class="panel empty">
        <div class="empty-icon">×</div>
        <p>该章节暂无可用数据。</p>
      </div>

      {% elif section.mode == "cards" %}
        {% for block in section.blocks %}
          {% if block.status == "no_data" %}
          <div class="panel empty">
            <div class="empty-icon">×</div>
            <p>暂无可用数据。</p>
            {% for caveat in block.caveats %}<p class="caveat">注：{{ caveat }}</p>{% endfor %}
          </div>
          {% else %}
          <div class="cards g4">
            {% for card in block.label_cards %}
            <div class="card level-{{ card.level }}">
              <div class="card-label">{{ card.label }}</div>
              <div class="card-value">{{ card.value }}</div>
            </div>
            {% endfor %}
          </div>
          {% endif %}
        {% endfor %}

      {% else %}
        {% for block in section.blocks %}
          {% if block.status == "no_data" %}
          <div class="panel empty">
            <div class="empty-icon">×</div>
            <p>暂无可用数据。</p>
            {% for caveat in block.caveats %}<p class="caveat">注：{{ caveat }}</p>{% endfor %}
          </div>
          {% else %}
          <div class="block">
            {% if section.blocks | length > 1 %}<h3>{{ block.title }}</h3>{% endif %}
            {% if block.narrative %}<p class="narrative">{{ block.narrative }}</p>{% endif %}
            {% for chart in block.charts %}
            <figure class="panel chart-panel">
              <figcaption>
                <span class="chart-title">{{ chart.title }}</span>
                {% if chart.subtitle %}<span class="chart-sub">{{ chart.subtitle }}</span>{% endif %}
              </figcaption>
              <div class="chart" data-chart-id="{{ chart.id }}"></div>
            </figure>
            {% endfor %}
            {% if block.fact_rows %}
            <div class="cards g3">
              {% for fact in block.fact_rows %}
              <div class="card">
                <div class="card-label">{{ fact.label }}</div>
                <div class="card-value">{{ fact.value }}</div>
              </div>
              {% endfor %}
            </div>
            {% endif %}
            {% for table in block.tables %}
            <div class="panel table-panel">
              <h4>{{ table.title }}</h4>
              {{ table.html | safe }}
            </div>
            {% endfor %}
            {% for caveat in block.caveats %}<p class="caveat">注：{{ caveat }}</p>{% endfor %}
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
        <h3>缺失维度</h3>
        {% if appendix.missing %}
        <ul>{% for item in appendix.missing %}<li>{{ item }}</li>{% endfor %}</ul>
        {% else %}
        <p>本次运行所有维度均返回数据。</p>
        {% endif %}
        <h3>标签阈值（执行摘要）</h3>
        <table class="dt">
          <thead><tr><th>标签</th><th>阈值</th></tr></thead>
          <tbody>
          {% for item in appendix.thresholds %}
          <tr><td>{{ item.label }}</td><td>{{ item.value }}</td></tr>
          {% endfor %}
          </tbody>
        </table>
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

- [ ] **Step 5: 删除旧渲染测试并运行新测试**

Run:

```bash
rm tests/test_render.py
uv run pytest tests/unit/test_render.py
```

Expected: 3 passed

- [ ] **Step 6: 运行现有相关测试，确认未被破坏**

Run: `uv run pytest tests/test_cli_run.py tests/test_pdf.py`
Expected: 全部通过（旧 CLI 仍传 figure_paths，但 render 已忽略）

---

### Task 7: LLM 数字守卫

**Files:**
- Create: `src/target_profile/llm/__init__.py`
- Create: `src/target_profile/llm/guard.py`
- Test: `tests/unit/test_llm_guard.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_llm_guard.py
from target_profile.llm.guard import validate_numbers


FACTS = {
    "overall_freq_pct": 6.96,
    "n_lines": 1183,
    "top_partner": "PIK3CA",
    "tau": 0.575,
    "top_disease": "Noonan syndrome",
}


def test_guard_accepts_fact_numbers():
    text = "KRAS 泛癌突变率为 6.96%，在 1183 个细胞系中评估，组织特异性 τ 为 0.575。"
    assert validate_numbers(text, FACTS, "KRAS") == []


def test_guard_rejects_invented_number():
    assert validate_numbers("KRAS 突变率为 99.9%。", FACTS, "KRAS") == ["99.9"]


def test_guard_ignores_gene_symbols_and_variants():
    text = "KRAS 与 PIK3CA 互作，G12D 变异常见，突变率 6.96%。"
    assert validate_numbers(text, FACTS, "KRAS") == []


def test_guard_accepts_integers_within_float_facts():
    assert validate_numbers("共 1183 条记录。", FACTS, "KRAS") == []
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/unit/test_llm_guard.py`
Expected: FAIL — `ModuleNotFoundError: target_profile.llm`

- [ ] **Step 3: 实现 guard 与包初始化**

```python
# src/target_profile/llm/__init__.py
"""Optional LLM polishing with strict numeric guard and template fallback."""
```

```python
# src/target_profile/llm/guard.py
"""Reject LLM output that introduces numbers not present in module facts."""
from __future__ import annotations

import re
from typing import Any

NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
GENE_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9\-]*")


def _normalise(value: float) -> str:
    return f"{float(value):.10g}"


def _collect(value: Any, out: set[str]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        out.add(_normalise(value))
        return
    if isinstance(value, str):
        for match in NUMBER_RE.findall(value):
            out.add(_normalise(float(match)))
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect(item, out)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _collect(item, out)


def allowed_numbers(facts: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    _collect(facts, out)
    return out


def validate_numbers(text: str, facts: dict[str, Any], gene_symbol: str) -> list[str]:
    """Return offending numeric literals (empty list means the text is safe)."""
    cleaned = text.replace(gene_symbol, " ")
    cleaned = GENE_TOKEN_RE.sub(" ", cleaned)
    allowed = allowed_numbers(facts)
    offenders: list[str] = []
    for match in NUMBER_RE.findall(cleaned):
        if _normalise(float(match)) not in allowed:
            offenders.append(match)
    return offenders
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest tests/unit/test_llm_guard.py`
Expected: 4 passed

---

### Task 8: LLM client 与缓存

**Files:**
- Create: `src/target_profile/llm/client.py`
- Create: `src/target_profile/llm/cache.py`
- Test: `tests/unit/test_llm_pipeline.py`（本任务只写缓存测试）

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_llm_pipeline.py
from target_profile.llm.cache import NarrativeCache, cache_key


def test_cache_key_is_stable_and_facts_sensitive():
    first = cache_key("KRAS", {"a": 1}, "model", "v1")
    second = cache_key("KRAS", {"a": 1}, "model", "v1")
    third = cache_key("KRAS", {"a": 2}, "model", "v1")
    assert first == second
    assert first != third


def test_cache_roundtrip(tmp_path):
    cache = NarrativeCache(tmp_path / "cache")
    key = cache_key("KRAS", {"a": 1}, "model", "v1")
    assert cache.get(key) is None
    cache.put(key, "解读文本")
    assert cache.get(key) == "解读文本"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/unit/test_llm_pipeline.py`
Expected: FAIL — `ModuleNotFoundError: target_profile.llm.cache`

- [ ] **Step 3: 实现 client 与 cache**

```python
# src/target_profile/llm/client.py
from __future__ import annotations

from typing import Any

import httpx


class LLMClient:
    """Minimal OpenAI-compatible chat client."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        timeout: float = 60.0,
        http_client: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.http_client = http_client or httpx.Client(timeout=timeout)

    def complete(self, system: str, user: str) -> str:
        response = self.http_client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload["choices"][0]["message"]["content"]).strip()
```

```python
# src/target_profile/llm/cache.py
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def cache_key(gene: str, facts: dict[str, Any], model: str, prompt_version: str) -> str:
    payload = json.dumps(
        {"gene": gene, "facts": facts, "model": model, "prompt_version": prompt_version},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


class NarrativeCache:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> str | None:
        path = self._path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("text")
        except (json.JSONDecodeError, OSError):
            return None

    def put(self, key: str, text: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._path(key).write_text(
            json.dumps({"text": text}, ensure_ascii=False), encoding="utf-8"
        )
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest tests/unit/test_llm_pipeline.py`
Expected: 2 passed

---

### Task 9: LLM prompts 与润色管线（含模板回退）

**Files:**
- Create: `src/target_profile/llm/prompts.py`
- Modify: `src/target_profile/llm/__init__.py`
- Test: `tests/unit/test_llm_pipeline.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/unit/test_llm_pipeline.py
from target_profile.config import LLMSettings, Settings
from target_profile.llm import build_narratives
from target_profile.models import ModuleResult


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        if not self.replies:
            raise AssertionError("unexpected LLM call")
        return self.replies.pop(0)


def _settings(tmp_path, enabled=True):
    return Settings(
        lake_root=tmp_path / "lake",
        data_root=tmp_path / "data",
        out_root=tmp_path / "out",
        llm=LLMSettings(enabled=enabled, base_url="http://example.invalid/v1", model="gpt-test"),
    )


def _mutation_module():
    return ModuleResult(
        name="mutation",
        facts={
            "overall_freq_pct": 6.96,
            "top_cancer": "PAAD",
            "top_cancer_freq_pct": 63.59,
            "top_protein_change": "G12D",
            "top_protein_change_count": 197,
        },
    )


def test_pipeline_uses_valid_llm_output(tmp_path, monkeypatch):
    monkeypatch.setenv("TARGET_PROFILE_LLM_API_KEY", "key")
    client = FakeClient(["KRAS 泛癌突变率为 6.96%。"])
    modules = [_mutation_module()]
    info = build_narratives("KRAS", modules, _settings(tmp_path), enabled=True, client=client)
    assert modules[0].narrative == "KRAS 泛癌突变率为 6.96%。"
    assert info["used"] == 1
    assert client.calls == 1


def test_pipeline_falls_back_on_guard_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("TARGET_PROFILE_LLM_API_KEY", "key")
    client = FakeClient(["KRAS 突变率为 99.9%。", "KRAS 突变率高达 88.8%。"])
    modules = [_mutation_module()]
    info = build_narratives("KRAS", modules, _settings(tmp_path), enabled=True, client=client)
    assert modules[0].narrative.startswith("TCGA PanCancer")
    assert info["fallback"] == 1
    assert client.calls == 2


def test_pipeline_uses_cache_on_second_run(tmp_path, monkeypatch):
    monkeypatch.setenv("TARGET_PROFILE_LLM_API_KEY", "key")
    first = FakeClient(["KRAS 泛癌突变率为 6.96%。"])
    build_narratives("KRAS", [_mutation_module()], _settings(tmp_path), enabled=True, client=first)
    second = FakeClient([])
    modules = [_mutation_module()]
    info = build_narratives("KRAS", modules, _settings(tmp_path), enabled=True, client=second)
    assert modules[0].narrative == "KRAS 泛癌突变率为 6.96%。"
    assert info["cached"] == 1
    assert second.calls == 0


def test_pipeline_no_llm_uses_template(tmp_path):
    modules = [_mutation_module()]
    info = build_narratives("KRAS", modules, _settings(tmp_path), enabled=False, client=None)
    assert modules[0].narrative.startswith("TCGA PanCancer")
    assert info["used"] == 0


def test_pipeline_missing_api_key_falls_back(tmp_path, monkeypatch):
    monkeypatch.delenv("TARGET_PROFILE_LLM_API_KEY", raising=False)
    modules = [_mutation_module()]
    info = build_narratives("KRAS", modules, _settings(tmp_path), enabled=True, client=None)
    assert modules[0].narrative.startswith("TCGA PanCancer")
    assert "error" in info
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/unit/test_llm_pipeline.py`
Expected: FAIL — `ImportError: cannot import name 'build_narratives'`

- [ ] **Step 3: 实现 prompts 与管线**

```python
# src/target_profile/llm/prompts.py
from __future__ import annotations

import json

from target_profile.models import ModuleResult

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = (
    "你是生物医药靶点分析写作助手。只能改写措辞，不得新增、删除或修改任何数字、"
    "基因符号与数据事实；不得引入外部知识；不得给出临床或用药建议。"
    "使用简体中文，1 到 3 句，专业、克制、客观。"
)


def _value(facts: dict, key: str, default: str = "—"):
    value = facts.get(key)
    return default if value is None else value


def template_narrative(gene: str, module: ModuleResult) -> str:
    facts = module.facts
    name = module.name
    if name == "basic":
        return (
            f"{gene} 属于 {_value(facts, 'target_class')}，蛋白长度 "
            f"{_value(facts, 'protein_length')} aa，亚细胞定位为 "
            f"{_value(facts, 'subcellular_locations')}。"
        )
    if name == "disease":
        return (
            f"Open Targets 关联 {_value(facts, 'disease_count')} 种疾病，最高为 "
            f"{_value(facts, 'top_disease')}（评分 {_value(facts, 'top_disease_score')}）；"
            f"LoF pLI {_value(facts, 'pli')}、LOEUF {_value(facts, 'loeuf')}，"
            f"ClinVar 记录 {_value(facts, 'clinvar_total')} 条。"
        )
    if name == "expression":
        return (
            f"{gene} 在 {_value(facts, 'gtex_tissue_count')} 个 GTEx 组织中可检测，"
            f"最高表达于 {_value(facts, 'gtex_top_tissue')}（中位 "
            f"{_value(facts, 'gtex_top_median_tpm')} TPM），组织特异性 τ 为 "
            f"{_value(facts, 'tau')}。"
        )
    if name == "mutation":
        return (
            f"TCGA PanCancer 合并样本中 {gene} 的突变率为 "
            f"{_value(facts, 'overall_freq_pct')}%，最高见于 "
            f"{_value(facts, 'top_cancer')}（{_value(facts, 'top_cancer_freq_pct')}%）；"
            f"最常见蛋白改变为 {_value(facts, 'top_protein_change')}"
            f"（{_value(facts, 'top_protein_change_count')} 次）。"
        )
    if name == "dependency":
        return (
            f"DepMap 共 {_value(facts, 'n_lines')} 个细胞系中，{gene} 的中位 Chronos "
            f"效应为 {_value(facts, 'median_effect')}，强依赖（≤ "
            f"{_value(facts, 'threshold_effect')}）细胞系 "
            f"{_value(facts, 'strong_dependency_count')} 个，占比 "
            f"{_value(facts, 'strong_dependency_fraction')}。"
        )
    if name == "cancer":
        return (
            f"{gene} 命中 {_value(facts, 'n_cancer_hallmarks')} 项癌症 hallmark，"
            f"代表性为 {_value(facts, 'top_hallmark')}；驱动状态评估为 "
            f"{_value(facts, 'driver_status')}，泛癌必需为 "
            f"{_value(facts, 'essential')}。"
        )
    if name == "pathway":
        return (
            f"{gene} 参与 {_value(facts, 'n_pathways')} 条 Reactome 通路，主要类别为 "
            f"{_value(facts, 'top_level_term')}；高置信互作伙伴 "
            f"{_value(facts, 'n_partners_high_conf')} 个，最强为 "
            f"{_value(facts, 'top_partner')}（{_value(facts, 'top_partner_score')}）。"
        )
    if name == "ptm":
        return (
            f"UniProt 注释了 {gene} 的 {_value(facts, 'n_ptm_sites')} 个 PTM 位点，"
            f"主要为 {_value(facts, 'top_ptm_type')}；序列长度 "
            f"{_value(facts, 'sequence_length')} aa，注释结构域/区域 "
            f"{_value(facts, 'n_domains')} 个。"
        )
    if name == "tractability":
        return (
            f"{gene} 的可成药性为 {_value(facts, 'tractable')}，已批准药物模态为 "
            f"{_value(facts, 'approved_modalities')}；化学探针 "
            f"{_value(facts, 'n_probes')} 个，药物/临床候选 "
            f"{_value(facts, 'n_drugs')} 个。"
        )
    if name == "safety":
        return (
            f"Open Targets 安全事件记录 {_value(facts, 'n_safety_liabilities')} 条，"
            f"IMPC 小鼠表型 {_value(facts, 'n_mouse_phenotypes')} 个，泛癌必需为 "
            f"{_value(facts, 'common_essential')}。无安全记录不代表安全。"
        )
    if name == "comparative":
        return (
            f"{gene} 共记录 {_value(facts, 'n_homologues')} 个同源基因，最高一致性为 "
            f"{_value(facts, 'top_homologue')}（{_value(facts, 'top_homologue_identity')}%），"
            f"最近旁系一致性为 {_value(facts, 'top_paralogue_identity')}%。"
        )
    return ""


def build_user_prompt(gene: str, module: ModuleResult, draft: str) -> str:
    facts = json.dumps(module.facts, ensure_ascii=False, sort_keys=True, default=str)
    return (
        f"基因：{gene}\n"
        f"维度：{module.name}\n"
        f"事实 JSON：{facts}\n"
        f"模板草稿：{draft}\n"
        "请仅改写模板草稿的措辞，保留全部数字、基因符号与事实，输出 1-3 句简体中文。"
    )
```

```python
# src/target_profile/llm/__init__.py
"""Optional LLM polishing with strict numeric guard and template fallback."""
from __future__ import annotations

import logging
import os

from target_profile.config import Settings
from target_profile.llm.cache import NarrativeCache, cache_key
from target_profile.llm.client import LLMClient
from target_profile.llm.guard import validate_numbers
from target_profile.llm.prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_user_prompt,
    template_narrative,
)
from target_profile.models import ModuleResult

__all__ = ["build_narratives", "template_narrative", "validate_numbers"]


def build_narratives(
    gene: str,
    modules: list[ModuleResult],
    settings: Settings,
    *,
    enabled: bool = True,
    client=None,
) -> dict:
    info: dict = {
        "enabled": bool(enabled),
        "model": settings.llm.model,
        "used": 0,
        "cached": 0,
        "fallback": 0,
    }
    llm_client = None
    if enabled and settings.llm.enabled and settings.llm.model:
        api_key = os.environ.get(settings.llm.api_key_env, "")
        if api_key:
            llm_client = client or LLMClient(
                settings.llm.base_url, settings.llm.model, api_key
            )
        else:
            info["error"] = f"missing {settings.llm.api_key_env}"

    cache = NarrativeCache(settings.data_root / "cache" / "_llm")
    for module in modules:
        if module.status != "ok":
            continue
        draft = template_narrative(gene, module)
        if not draft:
            continue
        text: str | None = None
        if llm_client is not None:
            key = cache_key(gene, module.facts, settings.llm.model, PROMPT_VERSION)
            cached = cache.get(key)
            if cached:
                text = cached
                info["cached"] += 1
            else:
                for _attempt in range(2):
                    try:
                        candidate = llm_client.complete(
                            SYSTEM_PROMPT, build_user_prompt(gene, module, draft)
                        )
                    except Exception as exc:  # network / API failure
                        logging.warning("llm %s failed: %s", module.name, exc)
                        break
                    offenders = validate_numbers(candidate, module.facts, gene)
                    if offenders:
                        logging.warning(
                            "llm guard rejected %s: %s", module.name, offenders[:5]
                        )
                        continue
                    text = candidate
                    cache.put(key, text)
                    info["used"] += 1
                    break
        if text is None:
            module.narrative = draft
            if llm_client is not None:
                info["fallback"] += 1
        else:
            module.narrative = text
    return info
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest tests/unit/test_llm_pipeline.py tests/unit/test_llm_guard.py`
Expected: 11 passed

---

### Task 10: Open Targets cancer API

**Files:**
- Modify: `src/target_profile/api/opentargets.py`
- Test: `tests/test_opentargets.py`

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/test_opentargets.py
from target_profile.api.opentargets import target_cancer


def test_target_cancer_reads_cache(tmp_path):
    cache = tmp_path / "ENSG00000133703"
    cache.mkdir(parents=True)
    (cache / "opentargets_cancer.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "id": "ENSG00000133703",
                        "hallmarks": {
                            "attributes": [{"name": "role in cancer"}],
                            "cancerHallmarks": [
                                {"label": "proliferative signalling", "impact": "promotes"},
                                {"label": "proliferative signalling", "impact": "promotes"},
                                {"label": "invasion and metastasis", "impact": "suppresses"},
                            ],
                        },
                    }
                }
            }
        )
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    details = target_cancer("ENSG00000133703", fetcher)
    assert details["hallmarks"]["cancerHallmarks"][0]["label"] == "proliferative signalling"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/test_opentargets.py`
Expected: FAIL — `ImportError: cannot import name 'target_cancer'`

- [ ] **Step 3: 实现 target_cancer**

```python
# 追加到 src/target_profile/api/opentargets.py
CANCER_QUERY = """
query Cancer($id: String!) {
  target(ensemblId: $id) {
    id
    hallmarks {
      attributes { name description }
      cancerHallmarks { label impact description pmid }
    }
  }
}
"""


def target_cancer(
    ensembl_id: str, fetcher: CachedFetcher, refresh: bool = False
) -> dict[str, Any] | None:
    return _target_query(ensembl_id, CANCER_QUERY, "opentargets_cancer", fetcher, refresh)
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest tests/test_opentargets.py`
Expected: 全部通过

---

### Task 11: cancer 分析模块

**Files:**
- Create: `src/target_profile/analysis/cancer.py`
- Test: `tests/unit/test_cancer.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_cancer.py
import json

import pandas as pd

from target_profile.analysis.cancer import analyze_cancer
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult

ENSG = "ENSG00000133703"


def _settings(tmp_path, hallmarks, essential=True):
    ensg = tmp_path / "data" / "cache" / ENSG
    ensg.mkdir(parents=True)
    (ensg / "opentargets_cancer.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "id": ENSG,
                        "hallmarks": {
                            "attributes": [{"name": "role in cancer"}],
                            "cancerHallmarks": hallmarks,
                        },
                    }
                }
            }
        )
    )
    (ensg / "opentargets_safety.json").write_text(
        json.dumps(
            {"data": {"target": {"id": ENSG, "isEssential": essential, "homologues": []}}}
        )
    )
    return Settings(lake_root=tmp_path / "lake", data_root=tmp_path / "data", out_root=tmp_path / "out")


def _hallmarks():
    return [
        {"label": "proliferative signalling", "impact": "promotes"},
        {"label": "proliferative signalling", "impact": "promotes"},
        {"label": "invasion and metastasis", "impact": "suppresses"},
    ]


def test_cancer_facts_and_table(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id=ENSG)
    prior = {"mutation": ModuleResult(name="mutation", facts={"overall_freq_pct": 6.96})}
    result = analyze_cancer(ctx, _settings(tmp_path, _hallmarks()), offline=True, prior=prior)
    assert result.status == "ok"
    assert result.facts["n_cancer_hallmarks"] == 2
    assert result.facts["top_hallmark"] == "proliferative signalling"
    assert result.facts["essential"] == "Yes"
    assert result.facts["pan_cancer_freq_pct"] == 6.96
    assert result.facts["driver_status"] == "驱动证据阳性"
    assert any("规则推导" in caveat for caveat in result.caveats)
    frame = result.tables["hallmarks"]
    assert frame.iloc[0]["promotes"] == 1
    assert frame.iloc[0]["suppresses"] == 0
    assert frame.iloc[1]["suppresses"] == 1


def test_cancer_driver_negative_when_below_threshold_and_no_hallmarks(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id=ENSG)
    prior = {"mutation": ModuleResult(name="mutation", facts={"overall_freq_pct": 1.2})}
    result = analyze_cancer(ctx, _settings(tmp_path, []), offline=True, prior=prior)
    assert result.facts["driver_status"] == "证据不足"


def test_cancer_marks_positive_from_hallmarks_when_freq_missing(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id=ENSG)
    result = analyze_cancer(ctx, _settings(tmp_path, _hallmarks()), offline=True, prior={})
    assert result.facts["pan_cancer_freq_pct"] is None
    assert result.facts["driver_status"] == "驱动证据阳性"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/unit/test_cancer.py`
Expected: FAIL — `ModuleNotFoundError: target_profile.analysis.cancer`

- [ ] **Step 3: 实现 cancer 模块**

```python
# src/target_profile/analysis/cancer.py
from __future__ import annotations

import pandas as pd

from target_profile.api.cache import CachedFetcher
from target_profile.api.opentargets import target_cancer, target_safety
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult


def analyze_cancer(
    ctx: GeneContext,
    settings: Settings,
    offline: bool = True,
    fetcher: CachedFetcher | None = None,
    prior: dict[str, ModuleResult] | None = None,
) -> ModuleResult:
    result = ModuleResult(name="cancer")
    fetcher = fetcher or CachedFetcher(settings.data_root / "cache", offline=offline)
    prior = prior or {}

    hallmarks: list[dict] = []
    try:
        payload = target_cancer(ctx.ensembl_id, fetcher)
    except Exception as exc:
        payload = None
        result.caveats.append(f"cancer: Open Targets hallmarks unavailable ({exc})")

    if payload:
        hallmarks = (payload.get("hallmarks") or {}).get("cancerHallmarks") or []

    if hallmarks:
        frame = pd.DataFrame(
            [
                {"label": item.get("label"), "impact": item.get("impact") or "unknown"}
                for item in hallmarks
                if item.get("label")
            ]
        )
        frame = frame.drop_duplicates()
        if not frame.empty:
            counts = (
                frame.groupby(["label", "impact"])
                .size()
                .unstack(fill_value=0)
                .reset_index()
            )
            for column in ("promotes", "suppresses"):
                if column not in counts.columns:
                    counts[column] = 0
            counts["total"] = counts["promotes"] + counts["suppresses"]
            counts = counts.sort_values("total", ascending=False)
            result.tables["hallmarks"] = counts[
                ["label", "promotes", "suppresses", "total"]
            ].reset_index(drop=True)
            result.facts["n_cancer_hallmarks"] = int(frame["label"].nunique())
            result.facts["top_hallmark"] = str(counts.iloc[0]["label"])
            result.facts["cancer_hallmark_impacts"] = "; ".join(
                f"{row.label}: promotes {row.promotes}, suppresses {row.suppresses}"
                for row in counts.itertuples()
            )

    essential = None
    try:
        safety = target_safety(ctx.ensembl_id, fetcher)
        if safety is not None and safety.get("isEssential") is not None:
            essential = bool(safety["isEssential"])
    except Exception as exc:
        result.caveats.append(f"cancer: isEssential unavailable ({exc})")
    result.facts["essential"] = (
        "Yes" if essential else ("No" if essential is not None else "Unknown")
    )

    mutation = prior.get("mutation")
    frequency = None
    if mutation is not None and mutation.status == "ok":
        frequency = mutation.facts.get("overall_freq_pct")
    result.facts["pan_cancer_freq_pct"] = frequency

    threshold = settings.thresholds.pan_cancer_hotspot_pct
    has_hallmarks = "hallmarks" in result.tables
    if frequency is None and not has_hallmarks:
        status = "未知"
        basis = "缺少突变与 hallmark 数据"
    elif frequency is not None and frequency >= threshold:
        status = "驱动证据阳性"
        basis = f"泛癌突变率 {frequency}% 达到阈值 {threshold}%"
    elif has_hallmarks:
        status = "驱动证据阳性"
        basis = "命中 Open Targets 癌症 hallmark"
    else:
        status = "证据不足"
        basis = f"泛癌突变率 {frequency}% 低于阈值 {threshold}%，且无 hallmark 记录"
    result.facts["driver_status"] = status
    result.caveats.append(
        f"cancer: 驱动状态为规则推导（{basis}）；Open Targets v4 未提供 isCancerDriverGene 字段"
    )

    if not result.tables:
        return result.degrade("cancer: no hallmark data")
    return result
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest tests/unit/test_cancer.py`
Expected: 3 passed

---

### Task 12: comparative 分析模块

**Files:**
- Create: `src/target_profile/analysis/comparative.py`
- Test: `tests/unit/test_comparative.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_comparative.py
import json

from target_profile.analysis.comparative import analyze_comparative
from target_profile.config import Settings
from target_profile.models import GeneContext

ENSG = "ENSG00000133703"


def _settings(tmp_path, homologues):
    ensg = tmp_path / "data" / "cache" / ENSG
    ensg.mkdir(parents=True)
    (ensg / "opentargets_safety.json").write_text(
        json.dumps(
            {"data": {"target": {"id": ENSG, "isEssential": False, "homologues": homologues}}}
        )
    )
    return Settings(lake_root=tmp_path / "lake", data_root=tmp_path / "data", out_root=tmp_path / "out")


def test_comparative_facts(tmp_path):
    homologues = [
        {
            "speciesName": "Chimpanzee",
            "homologyType": "ortholog",
            "targetGeneId": "ENSG00000228327",
            "queryPercentageIdentity": 99.5,
        },
        {
            "speciesName": "Human",
            "homologyType": "within_species_paralog",
            "targetGeneId": "ENSG00000126458",
            "queryPercentageIdentity": 53.7,
        },
        {
            "speciesName": "Mouse",
            "homologyType": "ortholog",
            "targetGeneId": "ENSG00000000001",
            "queryPercentageIdentity": 88.1,
        },
    ]
    ctx = GeneContext(symbol="KRAS", ensembl_id=ENSG)
    result = analyze_comparative(ctx, _settings(tmp_path, homologues), offline=True)
    assert result.status == "ok"
    assert result.facts["n_homologues"] == 3
    assert result.facts["top_homologue"] == "Chimpanzee"
    assert result.facts["top_homologue_identity"] == 99.5
    assert result.facts["top_paralogue_identity"] == 53.7
    assert list(result.tables["homologues"]["identity"]) == [99.5, 88.1, 53.7]


def test_comparative_no_homologues_degrades(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id=ENSG)
    result = analyze_comparative(ctx, _settings(tmp_path, []), offline=True)
    assert result.status == "no_data"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/unit/test_comparative.py`
Expected: FAIL — `ModuleNotFoundError: target_profile.analysis.comparative`

- [ ] **Step 3: 实现 comparative 模块**

```python
# src/target_profile/analysis/comparative.py
from __future__ import annotations

import pandas as pd

from target_profile.api.cache import CachedFetcher
from target_profile.api.opentargets import target_safety
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult


def analyze_comparative(
    ctx: GeneContext,
    settings: Settings,
    offline: bool = True,
    fetcher: CachedFetcher | None = None,
    prior: dict[str, ModuleResult] | None = None,
) -> ModuleResult:
    result = ModuleResult(name="comparative")
    fetcher = fetcher or CachedFetcher(settings.data_root / "cache", offline=offline)

    try:
        details = target_safety(ctx.ensembl_id, fetcher)
    except Exception as exc:
        return result.degrade(f"comparative: Open Targets homologues unavailable ({exc})")
    if not details:
        return result.degrade("comparative: no homologues payload")

    rows = []
    for item in details.get("homologues") or []:
        identity = item.get("queryPercentageIdentity")
        if identity is None:
            continue
        if item.get("targetGeneId") == ctx.ensembl_id:
            continue
        rows.append(
            {
                "species": item.get("speciesName") or "Unknown",
                "type": item.get("homologyType") or "unknown",
                "identity": round(float(identity), 1),
                "target_gene_id": item.get("targetGeneId"),
            }
        )
    if not rows:
        return result.degrade("comparative: no homologues with identity scores")

    frame = pd.DataFrame(rows).sort_values("identity", ascending=False)
    frame = frame.reset_index(drop=True)
    result.tables["homologues"] = frame

    orthologues = frame[frame["type"].str.contains("ortholog", case=False, na=False)]
    paralogues = frame[frame["type"].str.contains("paralog", case=False, na=False)]
    top = frame.iloc[0]
    result.facts["n_homologues"] = int(len(frame))
    result.facts["top_homologue"] = str(top["species"])
    result.facts["top_homologue_identity"] = float(top["identity"])
    if not orthologues.empty:
        result.facts["top_orthologue"] = str(orthologues.iloc[0]["species"])
        result.facts["top_orthologue_identity"] = float(orthologues.iloc[0]["identity"])
    if not paralogues.empty:
        result.facts["n_paralogues"] = int(len(paralogues))
        result.facts["top_paralogue_identity"] = float(paralogues.iloc[0]["identity"])
    else:
        result.caveats.append("comparative: 未记录种内旁系同源")
    return result
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest tests/unit/test_comparative.py`
Expected: 2 passed

---

### Task 13: summary 执行摘要标签卡

**Files:**
- Create: `src/target_profile/analysis/summary.py`
- Test: `tests/unit/test_summary.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_summary.py
from target_profile.analysis.summary import build_summary
from target_profile.config import Settings
from target_profile.models import ModuleResult


def _settings(tmp_path):
    return Settings(
        lake_root=tmp_path / "lake", data_root=tmp_path / "data", out_root=tmp_path / "out"
    )


def _module(name, **facts):
    return ModuleResult(name=name, facts=facts)


def test_summary_cards_for_hot_target(tmp_path):
    modules = [
        _module("basic", target_class="Enzyme / Hydrolase"),
        _module("disease", top_disease="Noonan syndrome"),
        _module("expression", tau=0.95),
        _module("mutation", overall_freq_pct=6.96),
        _module("dependency", mean_effect=-0.62),
        _module("tractability", tractable="Yes"),
        _module("safety", common_essential="Yes", loeuf=0.2264, n_safety_liabilities=0),
        _module("cancer", driver_status="驱动证据阳性"),
    ]
    summary = build_summary(modules, _settings(tmp_path))
    cards = {card["label"]: card for card in summary.label_cards}
    assert cards["靶点类别"]["value"] == "Enzyme / Hydrolase"
    assert cards["Top 关联疾病"]["value"] == "Noonan syndrome"
    assert cards["组织表达模式"]["level"] == "ok"
    assert "组织特异" in cards["组织表达模式"]["value"]
    assert cards["泛癌突变率"]["level"] == "warn"
    assert "强依赖" in cards["依赖性"]["value"]
    assert cards["泛癌必需"]["value"] == "Yes"
    assert cards["LoF 约束"]["value"].startswith("强约束")
    assert cards["可成药性"]["value"] == "Yes"
    assert cards["安全警示"]["level"] == "info"
    assert cards["癌症驱动"]["level"] == "warn"
    assert summary.facts["thresholds"]["pan_cancer_hotspot_pct"] == 5.0


def test_summary_general_expression_and_safety_warning(tmp_path):
    modules = [
        _module("expression", tau=0.2),
        _module("mutation", overall_freq_pct=1.0),
        _module("safety", n_safety_liabilities=3, loeuf=1.2),
    ]
    summary = build_summary(modules, _settings(tmp_path))
    cards = {card["label"]: card for card in summary.label_cards}
    assert "广泛表达" in cards["组织表达模式"]["value"]
    assert cards["泛癌突变率"]["level"] == "info"
    assert cards["安全警示"]["level"] == "warn"
    assert cards["LoF 约束"]["value"].startswith("无强约束")


def test_summary_degrades_without_facts(tmp_path):
    summary = build_summary([], _settings(tmp_path))
    assert summary.status == "no_data"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/unit/test_summary.py`
Expected: FAIL — `ModuleNotFoundError: target_profile.analysis.summary`

- [ ] **Step 3: 实现 summary 模块**

```python
# src/target_profile/analysis/summary.py
from __future__ import annotations

from target_profile.config import Settings
from target_profile.models import ModuleResult


def _number(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def build_summary(modules: list[ModuleResult], settings: Settings) -> ModuleResult:
    by_name = {module.name: module for module in modules}
    cards: list[dict] = []

    basic = by_name.get("basic")
    if basic and basic.facts.get("target_class"):
        cards.append(
            {"label": "靶点类别", "value": basic.facts["target_class"], "level": "info"}
        )

    disease = by_name.get("disease")
    if disease and disease.facts.get("top_disease"):
        cards.append(
            {"label": "Top 关联疾病", "value": disease.facts["top_disease"], "level": "info"}
        )

    expression = by_name.get("expression")
    tau = _number(expression.facts.get("tau")) if expression else None
    if tau is not None:
        if tau >= settings.thresholds.tissue_specific_tau:
            level, text = "ok", "组织特异"
        elif tau >= settings.thresholds.tissue_partial_tau:
            level, text = "info", "偏特异表达"
        else:
            level, text = "info", "广泛表达"
        cards.append(
            {"label": "组织表达模式", "value": f"{text} · τ={tau:.3f}", "level": level}
        )

    mutation = by_name.get("mutation")
    frequency = _number(mutation.facts.get("overall_freq_pct")) if mutation else None
    if frequency is not None:
        hot = frequency > settings.thresholds.pan_cancer_hotspot_pct
        cards.append(
            {
                "label": "泛癌突变率",
                "value": f"{frequency:.2f}%" + (" · 高频" if hot else ""),
                "level": "warn" if hot else "info",
            }
        )

    dependency = by_name.get("dependency")
    mean_effect = _number(dependency.facts.get("mean_effect")) if dependency else None
    if mean_effect is not None:
        strong = mean_effect <= settings.thresholds.strong_dependency_effect
        cards.append(
            {
                "label": "依赖性",
                "value": ("强依赖" if strong else "非强依赖") + f" · 平均效应 {mean_effect:.3f}",
                "level": "ok" if strong else "info",
            }
        )

    safety = by_name.get("safety")
    if safety:
        essential = safety.facts.get("common_essential")
        if essential:
            cards.append(
                {
                    "label": "泛癌必需",
                    "value": str(essential),
                    "level": "warn" if essential == "Yes" else "info",
                }
            )
        loeuf = _number(safety.facts.get("loeuf"))
        if loeuf is not None:
            constrained = loeuf < settings.thresholds.loeuf_constrained
            cards.append(
                {
                    "label": "LoF 约束",
                    "value": ("强约束" if constrained else "无强约束") + f" · LOEUF {loeuf:.3f}",
                    "level": "info",
                }
            )
        liabilities = _number(safety.facts.get("n_safety_liabilities"))
        if liabilities is not None:
            if liabilities > 0:
                value = f"{int(liabilities)} 条安全事件记录"
                level = "warn"
            else:
                value = "无安全事件记录（不代表安全）"
                level = "info"
            cards.append({"label": "安全警示", "value": value, "level": level})

    tractability = by_name.get("tractability")
    if tractability and tractability.facts.get("tractable"):
        tractable = str(tractability.facts["tractable"])
        cards.append(
            {
                "label": "可成药性",
                "value": tractable,
                "level": "ok" if tractable == "Yes" else "info",
            }
        )

    cancer = by_name.get("cancer")
    if cancer and cancer.facts.get("driver_status"):
        status = str(cancer.facts["driver_status"])
        cards.append(
            {
                "label": "癌症驱动",
                "value": status,
                "level": "warn" if status == "驱动证据阳性" else "info",
            }
        )

    result = ModuleResult(name="summary")
    result.label_cards = cards
    result.facts = {
        "n_label_cards": len(cards),
        "thresholds": {
            "tissue_specific_tau": settings.thresholds.tissue_specific_tau,
            "tissue_partial_tau": settings.thresholds.tissue_partial_tau,
            "pan_cancer_hotspot_pct": settings.thresholds.pan_cancer_hotspot_pct,
            "strong_dependency_effect": settings.thresholds.strong_dependency_effect,
            "loeuf_constrained": settings.thresholds.loeuf_constrained,
        },
    }
    if not cards:
        return result.degrade("summary: insufficient facts for label cards")
    return result
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `uv run pytest tests/unit/test_summary.py`
Expected: 3 passed

---

### Task 14: CLI 集成（12 模块 / builders / 叙事 / 默认 HTML / PDF 快照）

**Files:**
- Modify: `src/target_profile/cli.py`
- Modify: `src/target_profile/report/pdf.py`
- Modify: `tests/test_cli_run.py`
- Modify: `tests/integration/test_vertical_slice.py`

- [ ] **Step 1: 更新 CLI 测试期望**

```python
# tests/test_cli_run.py —— 替换 test_run_offline_declares_new_sections
def test_run_offline_declares_new_sections(tmp_path, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setenv("TARGET_PROFILE_HOME", str(home))
    result = CliRunner().invoke(app, ["run", "KRAS", "--offline", "--no-llm"])
    assert result.exit_code == 0, result.output
    out_dir = next((home / "out").glob("KRAS_*"))
    facts = json.loads((out_dir / "facts.json").read_text())
    assert set(facts["modules"]) == {
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
    }
    html = (out_dir / "report.html").read_text(encoding="utf-8")
    assert 'id="chart-data"' in html
    assert "echarts" in html.lower()
    assert (out_dir / "report.pdf").exists() is False  # default format is html
```

同时在文件顶部确认已有 `import json` 与 `from typer.testing import CliRunner`。

- [ ] **Step 2: 运行测试，确认失败**

Run: `uv run pytest tests/test_cli_run.py`
Expected: FAIL — 模块集合仍为 9 个

- [ ] **Step 3: 重写 cli.py**

```python
# src/target_profile/cli.py
import logging
from datetime import datetime
from pathlib import Path

import typer

from target_profile import __version__
from target_profile.analysis.basic import analyze_basic
from target_profile.analysis.cancer import analyze_cancer
from target_profile.analysis.comparative import analyze_comparative
from target_profile.analysis.dependency import analyze_dependency
from target_profile.analysis.disease import analyze_disease
from target_profile.analysis.expression import analyze_expression
from target_profile.analysis.mutation import analyze_mutation
from target_profile.analysis.pathway import analyze_pathway
from target_profile.analysis.ptm import analyze_ptm
from target_profile.analysis.safety import analyze_safety
from target_profile.analysis.summary import build_summary
from target_profile.analysis.tractability import analyze_tractability
from target_profile.api.alphafold import alphafold_prediction
from target_profile.api.clinvar import fetch_clinvar
from target_profile.api.opentargets import (
    target_basic,
    target_cancer,
    target_details,
    target_disease,
    target_pathways,
    target_safety,
    target_tractability,
)
from target_profile.api.stringdb import interaction_partners
from target_profile.api.uniprot import uniprot_record
from target_profile.config import load_settings
from target_profile.data_prep.lake import DERIVERS, derive_all
from target_profile.errors import DataMissing, GeneNotFound
from target_profile.figures.chart_specs import (
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
from target_profile.gene_resolve import resolve_gene
from target_profile.llm import build_narratives
from target_profile.models import ModuleResult
from target_profile.report.pdf import html_to_pdf
from target_profile.report.render import render_report

app = typer.Typer(no_args_is_help=True, help="Single-gene target profiling")

MODULES = [
    analyze_basic,
    analyze_disease,
    analyze_expression,
    analyze_mutation,
    analyze_dependency,
    analyze_pathway,
    analyze_ptm,
    analyze_tractability,
    analyze_safety,
]

BUILDERS = {
    "expression": build_expression,
    "mutation": build_mutation,
    "dependency": build_dependency,
    "pathway": build_pathway,
    "ptm": build_ptm,
    "disease": build_disease,
    "tractability": build_tractability,
    "safety": build_safety,
    "cancer": build_cancer,
    "comparative": build_comparative,
}


def _configure_logging(log_path: Path) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()],
        force=True,
    )


@app.command()
def version() -> None:
    """Show version."""
    typer.echo(f"target-profile {__version__}")


@app.command()
def data(
    source: str = typer.Argument("all", help="all or a source name"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    """Derive compact parquet files from the local Biomni data lake."""
    settings = load_settings()
    if source != "all" and source not in DERIVERS:
        typer.echo(f"unknown source: {source}; choose from {', '.join(DERIVERS)}", err=True)
        raise typer.Exit(code=2)
    try:
        entries = derive_all(settings) if source == "all" else [DERIVERS[source](settings)]
    except FileNotFoundError as exc:
        typer.echo(f"missing lake file: {exc}", err=True)
        raise typer.Exit(code=3)
    for entry in entries:
        typer.echo(f"{entry.name}: {entry.rows} rows -> {entry.path}")


@app.command()
def fetch(
    gene: str = typer.Argument(..., help="Gene symbol, alias, Ensembl or UniProt ID"),
    refresh: bool = typer.Option(False, "--refresh"),
) -> None:
    """Warm the per-gene API cache."""
    settings = load_settings()
    try:
        ctx = resolve_gene(gene, settings, offline=False)
    except GeneNotFound as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2)
    from target_profile.api.cache import CachedFetcher
    from target_profile.api.cbioportal import fetch_pancan_mutations

    fetcher = CachedFetcher(settings.data_root / "cache", offline=False)
    steps = [
        ("Open Targets target", lambda: target_details(ctx.ensembl_id, fetcher, refresh=refresh)),
        ("Open Targets basic", lambda: target_basic(ctx.ensembl_id, fetcher, refresh=refresh)),
        ("Open Targets pathways", lambda: target_pathways(ctx.ensembl_id, fetcher, refresh=refresh)),
        ("Open Targets disease", lambda: target_disease(ctx.ensembl_id, fetcher, refresh=refresh)),
        ("Open Targets tractability", lambda: target_tractability(ctx.ensembl_id, fetcher, refresh=refresh)),
        ("Open Targets safety", lambda: target_safety(ctx.ensembl_id, fetcher, refresh=refresh)),
        ("Open Targets cancer", lambda: target_cancer(ctx.ensembl_id, fetcher, refresh=refresh)),
        ("STRING partners", lambda: interaction_partners(ctx.symbol, fetcher, refresh=refresh)),
    ]
    if ctx.uniprot_id:
        steps.append(("UniProt record", lambda: uniprot_record(ctx.uniprot_id, fetcher, refresh=refresh)))
        steps.append(("AlphaFold prediction", lambda: alphafold_prediction(ctx.uniprot_id, fetcher, refresh=refresh)))
    if ctx.entrez_id:
        steps.append(
            (
                "cBioPortal TCGA mutations",
                lambda: fetch_pancan_mutations(ctx.symbol, ctx.entrez_id, fetcher, refresh=refresh),
            )
        )
    steps.append(("ClinVar records", lambda: fetch_clinvar(ctx.symbol, fetcher, refresh=refresh)))
    for label, action in steps:
        try:
            action()
            typer.echo(f"cached: {label}")
        except Exception as exc:
            typer.echo(f"warning: {label} failed: {exc}", err=True)
    typer.echo(f"cached gene: {ctx.symbol}")


@app.command()
def doctor() -> None:
    """Check environment and data availability."""
    settings = load_settings()
    ok = True
    typer.echo(f"lake_root: {settings.lake_root}")
    typer.echo(f"data_root: {settings.data_root}")
    for name in DERIVERS:
        path = settings.data_root / "parquet" / f"{name}.parquet"
        exists = path.exists()
        ok = ok and exists
        typer.echo(f"{'OK ' if exists else 'MISS'} {path}")
    try:
        import playwright  # noqa: F401

        typer.echo("OK  playwright")
    except Exception:
        typer.echo("MISS playwright (PDF disabled; HTML still works)")
    raise typer.Exit(code=0 if ok else 1)


def _run_analyzer(analyzer, ctx, settings, offline, **kwargs) -> ModuleResult:
    name = getattr(analyzer, "__name__", "module").replace("analyze_", "")
    try:
        return analyzer(ctx, settings, offline=offline, **kwargs)
    except DataMissing:
        raise
    except Exception as exc:
        logging.exception("module %s failed", name)
        return ModuleResult(name=name).degrade(f"{name}: internal error ({exc})")


@app.command()
def run(
    gene: str = typer.Argument(..., help="Gene symbol, alias, Ensembl or UniProt ID"),
    out: Path | None = typer.Option(None, "--out", help="Output directory"),
    format: str = typer.Option("html", "--format", help="html|pdf|both"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Disable LLM polishing"),
    force: bool = typer.Option(False, "--force", help="Overwrite output directory"),
    offline: bool = typer.Option(False, "--offline", help="Forbid network access"),
) -> None:
    """Generate a single-gene profiling report."""
    if format not in {"html", "pdf", "both"}:
        typer.echo(f"invalid --format: {format}; choose html|pdf|both", err=True)
        raise typer.Exit(code=2)
    settings = load_settings()
    try:
        ctx = resolve_gene(gene, settings, offline=offline)
    except GeneNotFound as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2)
    except DataMissing as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=3)

    out_dir = out or settings.out_root / f"{ctx.symbol}_{datetime.now():%Y%m%d}"
    if out_dir.exists() and not force:
        typer.echo(f"output exists: {out_dir}; use --force", err=True)
        raise typer.Exit(code=2)
    out_dir.mkdir(parents=True, exist_ok=True)
    _configure_logging(out_dir / "run.log")

    modules = [_run_analyzer(analyzer, ctx, settings, offline) for analyzer in MODULES]
    by_name = {module.name: module for module in modules}

    for analyzer in (analyze_cancer, analyze_comparative):
        result = _run_analyzer(analyzer, ctx, settings, offline, prior=by_name)
        modules.append(result)
        by_name[result.name] = result

    modules.append(build_summary(modules, settings))

    for module in modules:
        module.facts.setdefault("symbol", ctx.symbol)
        builder = BUILDERS.get(module.name)
        if builder and module.status == "ok":
            try:
                module.charts = builder(module)
            except Exception as exc:
                logging.warning("charts %s failed: %s", module.name, exc)

    llm_info = build_narratives(ctx.symbol, modules, settings, enabled=not no_llm)

    html_path, facts_path = render_report(ctx, modules, out_dir, llm_info=llm_info)
    logging.info("wrote %s", html_path)
    logging.info("wrote %s", facts_path)

    if format in {"both", "pdf"}:
        pdf_path = out_dir / "report.pdf"
        if not html_to_pdf(html_path, pdf_path):
            typer.echo("PDF export failed; HTML retained", err=True)
            raise typer.Exit(code=4)

    typer.echo(f"report: {html_path}")
    if format in {"both", "pdf"}:
        typer.echo(f"pdf: {out_dir / 'report.pdf'}")
```

- [ ] **Step 4: 更新 PDF 打印器，支持图表快照**

```python
# src/target_profile/report/pdf.py
from pathlib import Path
from typing import Callable


def _print_with_playwright(html_path: Path, pdf_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.resolve().as_uri(), wait_until="load")
        page.wait_for_function("window.__chartsReady === true", timeout=15000)
        page.evaluate("window.__snapshotCharts && window.__snapshotCharts()")
        page.pdf(path=str(pdf_path), format="A4", print_background=True)
        browser.close()


def html_to_pdf(
    html_path: Path,
    pdf_path: Path,
    printer: Callable[[Path, Path], None] | None = None,
) -> bool:
    printer = printer or _print_with_playwright
    try:
        printer(html_path, pdf_path)
        return True
    except Exception:
        return False
```

- [ ] **Step 5: 更新集成测试 fixture（追加 cancer 缓存、同源基因）**

在 `tests/integration/test_vertical_slice.py` 的 `_build_home` 中，`(ensg_dir / "opentargets_safety.json")` 写入内容里的 `"homologues": []` 改为：

```python
"homologues": [
    {
        "speciesName": "Chimpanzee",
        "homologyType": "ortholog",
        "targetGeneId": "ENSG00000228327",
        "queryPercentageIdentity": 99.5,
    },
    {
        "speciesName": "Human",
        "homologyType": "within_species_paralog",
        "targetGeneId": "ENSG00000126458",
        "queryPercentageIdentity": 53.7,
    },
],
```

并在同一 `for gene, ensg, acc in [...]` 循环内、`opentargets_safety.json` 之后追加：

```python
(ensg_dir / "opentargets_cancer.json").write_text(
    json.dumps(
        {
            "data": {
                "target": {
                    "id": ensg,
                    "hallmarks": {
                        "attributes": [{"name": "role in cancer"}],
                        "cancerHallmarks": [
                            {"label": "proliferative signalling", "impact": "promotes"},
                            {"label": "invasion and metastasis", "impact": "promotes"},
                        ],
                    },
                }
            }
        }
    )
)
```

同时把 `test_full_chain_offline` 中的断言从 `data:image/png;base64` 改为新结构：

```python
        assert 'id="chart-data"' in html
        assert "echarts" in html.lower()
        assert "data:font/woff2;base64," in html
        assert 'src="http' not in html
        assert 'href="http' not in html
        assert facts["modules"]["expression"]["status"] == "ok"
        assert facts["modules"]["mutation"]["status"] == "ok"
        assert facts["modules"]["dependency"]["status"] == "ok"
        assert facts["modules"]["basic"]["status"] == "ok"
        assert facts["modules"]["pathway"]["status"] == "ok"
        assert facts["modules"]["ptm"]["status"] == "ok"
        assert facts["modules"]["disease"]["status"] == "ok"
        assert facts["modules"]["tractability"]["status"] == "ok"
        assert facts["modules"]["safety"]["status"] == "ok"
        assert facts["modules"]["cancer"]["status"] == "ok"
        assert facts["modules"]["comparative"]["status"] == "ok"
        assert facts["modules"]["summary"]["status"] == "ok"
```

- [ ] **Step 6: 运行相关测试**

Run: `uv run pytest tests/test_cli_run.py tests/integration/test_vertical_slice.py tests/test_pdf.py`
Expected: 全部通过（默认 html 不产 PDF；`--format pdf` 未在测试中请求）

---

### Task 15: 移除 matplotlib 与 figure_paths

**Files:**
- Modify: `src/target_profile/models.py`
- Modify: `pyproject.toml`
- Delete: `src/target_profile/figures/charts.py`
- Delete: `src/target_profile/figures/theme.py`
- Delete: `tests/test_figures.py`

- [ ] **Step 1: 删除 matplotlib 资产**

Run:

```bash
rm src/target_profile/figures/charts.py \
   src/target_profile/figures/theme.py \
   tests/test_figures.py
```

- [ ] **Step 2: 从模型移除 figure_paths**

```python
# src/target_profile/models.py —— ModuleResult 最终形态
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

    def degrade(self, reason: str) -> "ModuleResult":
        self.status = "no_data"
        self.caveats.append(reason)
        return self
```

同时删除文件顶部的 `from pathlib import Path`（若不再使用）。

- [ ] **Step 3: 从依赖中移除 matplotlib**

```toml
# pyproject.toml —— dependencies 改为
dependencies = [
  "duckdb>=1.1",
  "pandas>=2.2",
  "pyarrow>=17.0",
  "jinja2>=3.1",
  "typer>=0.12",
  "pydantic>=2.8",
  "pyyaml>=6.0",
  "httpx[socks]>=0.27",
  "playwright>=1.47",
]
```

- [ ] **Step 4: 全量测试**

Run: `uv run pytest`
Expected: 全部通过（若 `.venv` 中 matplotlib 仍安装不影响；`uv lock` 下次 sync 时会移除）

- [ ] **Step 5: 同步锁文件**

Run: `uv lock`
Expected: 成功，`uv.lock` 中不再包含 matplotlib 直接依赖。

---

### Task 16: 全链路自包含验收测试

**Files:**
- Modify: `tests/integration/test_vertical_slice.py`

- [ ] **Step 1: 追加自包含与图表 JSON 断言**

```python
# 追加到 tests/integration/test_vertical_slice.py
import re


def test_report_is_self_contained(tmp_path, monkeypatch):
    home = _build_home(tmp_path)
    monkeypatch.setenv("TARGET_PROFILE_HOME", str(home))
    result = CliRunner().invoke(app, ["run", "KRAS", "--offline", "--no-llm"])
    assert result.exit_code == 0, result.output
    out_dir = next((home / "out").glob("KRAS_*"))
    html = (out_dir / "report.html").read_text(encoding="utf-8")

    assert "echarts" in html.lower()
    assert "data:font/woff2;base64," in html
    assert not re.search(r'(src|href)\s*=\s*["\']https?://', html)
    assert "url(http" not in html
    assert "@import url(http" not in html

    payload = json.loads(
        html.split('<script id="chart-data" type="application/json">')[1].split("</script>")[0]
    )
    assert "expression-gtex" in payload
    assert "mutation-cancers" in payload
    assert "dependency-dist" in payload
    assert "cancer-hallmarks" in payload
    assert "comparative-identity" in payload
    for entry in payload.values():
        assert "option" in entry

    for number in range(1, 13):
        assert f'id="ch-{number}"' in html
```

- [ ] **Step 2: 运行集成测试**

Run: `uv run pytest tests/integration/test_vertical_slice.py`
Expected: 2 passed

- [ ] **Step 3: 全量测试**

Run: `uv run pytest`
Expected: 全部通过

---

### Task 17: 真实数据手工验收（KRAS / TP53）

**Files:** 无代码改动（仅验收与截图）

- [ ] **Step 1: 离线生成 KRAS 报告**

Run:

```bash
cd /root/target_profiling
uv run target-profile run KRAS --offline --no-llm --force
```

Expected: 退出码 0；`out/KRAS_*/report.html` 存在，无 `report.pdf`；`run.log` 无 ERROR。

- [ ] **Step 2: 用 Playwright 截图并检查视觉**

Run:

```bash
uv run python - <<'PY'
from pathlib import Path
from playwright.sync_api import sync_playwright

html = sorted(Path("out").glob("KRAS_*/report.html"))[-1].resolve()

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto(html.as_uri(), wait_until="load")
    page.wait_for_function("window.__chartsReady === true", timeout=20000)
    page.screenshot(path="/tmp/kras_top.png")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.35)")
    page.wait_for_timeout(400)
    page.screenshot(path="/tmp/kras_mid.png")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(400)
    page.screenshot(path="/tmp/kras_bottom.png")
    browser.close()
print(html)
PY
```

Expected: 三张截图生成。

- [ ] **Step 3: 查看截图**

Use the Read tool on `/tmp/kras_top.png`、`/tmp/kras_mid.png`、`/tmp/kras_bottom.png`。
检查：
- Hero 深色渐变、基因符号大标题、ID 徽章
- 左侧目录高亮、章节编号
- 图表无空白/破图、中文不乱码
- 事实卡与表格可读、caveat 琥珀色
- 附录与页脚完整

- [ ] **Step 4: 验证交互与自包含**

Run:

```bash
uv run python - <<'PY'
import re
from pathlib import Path

html = sorted(Path("out").glob("KRAS_*/report.html"))[-1].read_text(encoding="utf-8")
print("size_kb", len(html) // 1024)
print("external_src", bool(re.search(r'(src|href)\s*=\s*["\']https?://', html)))
print("has_echarts", "echarts" in html.lower())
print("has_font", "data:font/woff2;base64," in html)
print("chart_ids", len(re.findall(r'data-chart-id="', html)))
PY
```

Expected: `size_kb` 约 1200–1500；`external_src False`；`has_echarts True`；`has_font True`；`chart_ids` 约 17

- [ ] **Step 5: 生成 TP53 并与基线核对**

Run:

```bash
uv run target-profile run TP53 --offline --no-llm --force
uv run python - <<'PY'
import json
from pathlib import Path

facts = json.loads(sorted(Path("out").glob("TP53_*/facts.json"))[-1].read_text())
m = facts["modules"]
print("overall_freq_pct", m["mutation"]["facts"]["overall_freq_pct"])
print("driver", m["cancer"]["facts"]["driver_status"])
print("homologues", m["comparative"]["facts"].get("n_homologues"))
print("cards", [c["label"] for c in m["summary"]["label_cards"]])
PY
```

Expected（基线）: `overall_freq_pct 35.01`；`driver 驱动证据阳性`；`n_homologues` 为整数；`cards` 至少包含 组织表达模式/泛癌突变率/依赖性/泛癌必需/可成药性/癌症驱动。

- [ ] **Step 6: 可选 PDF 验证**

Run: `uv run target-profile run KRAS --offline --no-llm --format pdf --force`
Expected: 退出码 0，`out/KRAS_*/report.pdf` 存在且大于 100KB；若失败则退出码 4 且 HTML 保留（best-effort，不阻塞验收）。

---

## 自检（Spec 覆盖）

| Spec 条目 | 对应任务 |
|---|---|
| `ChartSpec` / `ModuleResult` 扩展 | Task 1 |
| ECharts 5.5.1 + 字体内联 | Task 2、5、6 |
| 8 个现有维度图重写 | Task 3、4 |
| `cancer`（hallmarks + 驱动状态 + isEssential） | Task 10、11 |
| `comparative`（homologues） | Task 12 |
| `summary` 标签卡 + 阈值公开 | Task 13、6 附录 |
| LLM（client/prompts/guard/cache/回退） | Task 7、8、9 |
| 12 章固定顺序 + 空状态 + 第 12 章占位 + 附录 | Task 6 |
| 自包含断言 | Task 6、16 |
| PDF 默认关闭、快照后打印、失败退出码 4 | Task 14 |
| 移除 matplotlib | Task 15 |
| 真实数据验收 | Task 17 |

已知与 spec 的偏差（按实际 API 修正）：
- Open Targets v4 的 hallmarks 查询为 `hallmarks { attributes { name description } cancerHallmarks { label impact description pmid } }`，不是 `hallmarks { label impact }`。
- Open Targets `Target` 类型无 `isCancerDriverGene` 字段，驱动状态按「泛癌突变率阈值或 hallmark 命中」推导并在 caveat 注明。
- `comparative` 复用 `opentargets_safety` 缓存中的 `homologues`，不新增 API。
