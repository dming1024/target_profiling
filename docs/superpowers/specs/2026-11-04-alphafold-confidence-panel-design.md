# AlphaFold 结构置信度面板设计

日期：2026-11-04
状态：已批准设计，待实施

## 1. 背景与问题

AlphaFold 数据已经在 `fetch` 阶段下载并缓存（`data/cache/_global/alphafold_<ACC>.json`），
`analyze_basic` 也已读取，但报告只暴露两个字段：

- 第 2 章 KPI「平均 pLDDT」
- 折叠明细中的「AlphaFold 结构：Yes」

缓存中另有 4 档 pLDDT 占比、模型版本、entry ID、PDB/CIF 链接；
AlphaFold DB 还提供约 5 KB 的逐残基 confidence JSON。
用户希望在 HTML 报告中看到可见、可解释的结构置信度信息。

## 2. 目标与非目标

### 目标

1. 第 2 章新增结构置信度面板：逐残基 pLDDT 曲线 + 四档占比环形图。
2. 第 2 章 KPI 增加「高置信残基占比 (≥90)」。
3. 执行摘要「靶点定位」增加 AlphaFold pLDDT 一项。
4. 面板提供 AlphaFold DB / PDB / CIF 外链。
5. 明确科学口径：pLDDT 是单模型逐残基置信度，不是实验精度或功能重要性。
6. 离线可复现：报告生成阶段零联网；旧缓存可降级。

### 非目标

- 不做交互式 3D 结构（3Dmol/NGL）或结构渲染，属于 3b。
- 不做 PAE 矩阵可视化。
- 不改动其他章节的图表与 PDF 图表页。
- 不引入新的 Python/JS 依赖。

## 3. 数据来源与许可

| 数据 | 来源 | 许可 | 用途 |
|---|---|---|---|
| 模型元数据 | AlphaFold DB `/api/prediction/<ACC>` | CC BY 4.0 | 平均 pLDDT、四档占比、版本、覆盖度、链接 |
| 逐残基置信度 | `plddtDocUrl`（confidence JSON） | CC BY 4.0 | 逐残基曲线与分级计数 |

AlphaFold DB 已在 `config/licenses.yaml` 与 `render.FALLBACK_SOURCES` 中登记，无需新增许可条目。

逐残基 JSON 结构（已验证 P04637）：

```json
{
  "residueNumber": [1, 2, ...],
  "confidenceScore": [42.72, 43.59, ...],
  "confidenceCategory": ["D", "D", ...]
}
```

`confidenceCategory`：A = very high (≥90)，B = confident (70–90)，C = low (50–70)，D = very low (<50)。

## 4. 数据流与缓存

```
fetch GENE
  ├─ alphafold_prediction(ACC)          -> _global/alphafold_<ACC>.json（已有）
  └─ alphafold_confidence(ACC, pred)    -> _global/alphafold_plddt_<ACC>.json（新增）

run GENE --offline
  └─ analyze_basic 读取上述两个缓存；缺失逐残基缓存时降级
```

### 4.1 `api/alphafold.py` 新增

```python
def alphafold_confidence(
    acc: str | None,
    prediction: dict[str, Any] | None,
    fetcher: CachedFetcher,
    refresh: bool = False,
) -> dict[str, Any] | None:
    """Download/cache the per-residue pLDDT document referenced by prediction."""
```

- 无 `acc`、无 `prediction`、无 `plddtDocUrl` 时返回 `None`。
- 缓存名：`alphafold_plddt_{acc}`，目录 `_global`。
- 离线且无缓存时由 `CachedFetcher` 抛 `OfflineCacheMiss`；调用方捕获并降级。

### 4.2 `cli.fetch` 新增步骤

在现有 AlphaFold prediction 步骤之后追加：

```python
def _fetch_af_confidence():
    prediction = alphafold_prediction(ctx.uniprot_id, fetcher, refresh=refresh)
    return alphafold_confidence(ctx.uniprot_id, prediction, fetcher, refresh=refresh)

steps.append(("AlphaFold confidence", _fetch_af_confidence))
```

失败只打印 warning，不中断 `fetch`（沿用现有行为）。

## 5. 分析层（`analysis/basic.py`）

### 5.1 新增 facts

| fact | 类型 | 说明 |
|---|---|---|
| `alphafold_mean_plddt` | float | 已有，保留 |
| `alphafold_very_high_pct` | float | `fractionPlddtVeryHigh * 100` |
| `alphafold_confident_pct` | float | `fractionPlddtConfident * 100` |
| `alphafold_low_pct` | float | `fractionPlddtLow * 100` |
| `alphafold_very_low_pct` | float | `fractionPlddtVeryLow * 100` |
| `alphafold_entry_id` | str | 如 `AF-P04637-F1` |
| `alphafold_model_version` | str | 如 `v6` |
| `alphafold_coverage` | str | 如 `1–393 aa (100%)` |

缺失字段不写入 facts。所有百分比保留一位小数。

### 5.2 覆盖度

- 起点/终点优先取 `uniprotStart` / `uniprotEnd`，回退 `sequenceStart` / `sequenceEnd`。
- 全长取 UniProt `protein_length`；覆盖率 = (end - start + 1) / protein_length × 100。
- 无长度时只显示区间，如 `1–393 aa`。
- 覆盖率 < 95% 时追加 caveat，说明未覆盖区域无置信度。

### 5.3 表格

`alphafold_categories`（用于明细展示与环形图）：

| category | residues | pct |
|---|---|---|
| Very high (≥90) | 207 | 52.7 |
| Confident (70–90) | 28 | 7.1 |
| Low (50–70) | 41 | 10.4 |
| Very low (<50) | 117 | 29.8 |

- 有逐残基文档时 `residues` 用 A/B/C/D 计数；否则留空（显示“—”），`pct` 仍来自元数据。
- 顺序固定为 Very high → Confident → Low → Very low。

`alphafold_plddt`（隐藏，仅绘图）：列 `residue`、`plddt`、`category`。

### 5.4 链接

`ModuleResult` 新增字段：

```python
links: list[dict[str, str]] = field(default_factory=list)
```

`basic` 在存在时追加：

```python
[
    {"label": "AlphaFold DB", "url": f"https://alphafold.ebi.ac.uk/entry/{acc}"},
    {"label": "PDB", "url": prediction["pdbUrl"]},
    {"label": "CIF", "url": prediction["cifUrl"]},
]
```

### 5.5 caveats

- 有预测时：
  `AlphaFold pLDDT 是单模型逐残基置信度，不代表实验结构精度或残基功能重要性；低 pLDDT 不等于无序。`
- 覆盖度 < 95% 时追加覆盖范围说明。
- 缺失逐残基缓存时：
  `未找到逐残基置信度缓存，本面板仅展示分段占比；运行 fetch 可补齐。`

## 6. 展示层

### 6.1 第 2 章 KPI

`MODULE_SPECS["basic"].kpi` 追加 `alphafold_very_high_pct`，顺序放在 `alphafold_mean_plddt` 之后。

### 6.2 图表 builder

`figures/chart_specs.py` 新增 `build_basic(result)`，`cli.BUILDERS["basic"] = build_basic`。
图表均为纯 JSON 可序列化（无 JS 函数）。

#### `alphafold-residue`

- title：`AlphaFold per-residue pLDDT`
- subtitle：`Source: AlphaFold DB · <entry_id> · <version>`
- 数据：`alphafold_plddt` 的 `[residue, plddt]`
- 折线：无 symbol，线色 `#55d6be`，面积渐变低透明度
- y 轴 0–100，x 轴从 1 开始
- 背景 `markArea` 四档：
  - ≥90 `Very high`，`rgba(85,214,190,.08)`
  - 70–90 `Confident`，`rgba(110,168,254,.07)`
  - 50–70 `Low`，`rgba(240,176,83,.07)`
  - <50 `Very low`，`rgba(242,125,154,.06)`
- tooltip：残基号与 pLDDT；四档背景色带承担等级提示（保持纯 JSON，无 JS formatter）
- 若 `alphafold_plddt` 不存在，不生成该图（不生成空图占位）

#### `alphafold-confidence`

- title：`AlphaFold confidence distribution`
- subtitle：`Source: AlphaFold DB`
- 环形图：`radius ["52%","76%"]`，颜色
  - Very high `#55d6be`
  - Confident `#6ea8fe`
  - Low `#f0b053`
  - Very low `#f27d9a`
- 标签：`{b}\n{c}%`
- 中心文字：平均 pLDDT（如 `75.1`）与 `mean pLDDT`
- 数据来自 `alphafold_categories`

### 6.3 章节装配

- `basic` 的图表由 `module.charts` 直接渲染；无需改 `CHAPTERS`。
- `ModuleSpec` 新增 `hidden_tables: tuple[str, ...] = ()`；`_block` 自动补充明细表时跳过隐藏表。
- `basic.hidden_tables = ("alphafold_plddt",)`。
- `alphafold_categories` 作为 secondary table 进入折叠明细。

### 6.4 模板

`report.html.j2` 在 `block.charts` 之后增加：

```jinja
{% if block.links %}
<div class="block-links">
  {% for link in block.links %}
  <a href="{{ link.url }}" target="_blank" rel="noopener">{{ link.label }}</a>
  {% endfor %}
</div>
{% endif %}
```

`dashboard.css` 增加 `.block-links` 样式：小号字体、等宽圆角、hover 青色描边。
打印时隐藏 `.block-links`（`print.css`）。

自包含约束说明：外链是 `<a href>` 引用，不加载任何资源；仍禁止 `<script src>`、
`<link href>` 与 CSS `url(http...)`。现有测试中“任何 http href 均不允许”的断言
需收窄为“资源类 http 引用不允许”，锚点外链放行。

### 6.5 执行摘要

`_summary_view` 的「靶点定位」组追加：

```python
{"label": "AlphaFold pLDDT", "value": f"{mean:.1f} · 高置信 {very_high:.1f}%"}
```

仅当 `alphafold_mean_plddt` 存在时添加。

### 6.6 PDF 速览

- 保持现有 5 页与图表页不变。
- `_speed_rows` 在第 2 章行后插入：

```python
{"title": "结构置信度", "metric": "AlphaFold 平均 pLDDT",
 "value": "75.1 (高置信 52.7%)", "status": "覆盖 100%"}
```

- 行数上限从 12 调整为 13。

### 6.7 附录

`LIMITATIONS` 追加：

`AlphaFold 结构为计算预测（monomer），pLDDT 仅反映局部置信度；不得据此推断实验构象、功能位点或临床意义。`

## 7. 科学口径

- pLDDT 是 AlphaFold 对每个残基局部距离误差的预测置信度，范围 0–100。
- 平均 pLDDT 是残基加权均值，不能代表整体结构精度或特定区域可靠性。
- pLDDT 低不等于无序：可能表示柔性、构象集合或缺乏同源信息。
- 模型为 monomer 预测，不含配体、PTM、复合物环境。
- 报告必须同时展示平均 pLDDT、四档占比与序列覆盖度，避免单一数字误导。
- 面板及附录不得出现“结构准确”“高精度结构”等未经支持的表述。

## 8. 降级与兼容

| 情况 | 行为 |
|---|---|
| 无 AlphaFold 预测 | 不生成面板；`alphafold_available = No` |
| 有预测、无逐残基缓存 | 生成环形图与 KPI；不生成曲线；追加 caveat |
| 旧缓存缺 fraction 字段 | 只显示可用字段；环形图缺数据则不生成 |
| 离线且缓存缺失 | 捕获异常，basic 模块不失败 |
| 逐残基文档格式异常 | 捕获异常，按无逐残基处理 |

## 9. 测试计划

1. `tests/test_api_sources.py`
   - `alphafold_confidence` 读取缓存。
   - 无 URL / 无 accession 返回 `None`。
   - 离线缺缓存抛 `OfflineCacheMiss`（由调用方处理）。
2. `tests/test_basic.py`
   - 扩展 fixture：fractions、entryId、latestVersion、uniprotStart/End、逐残基文档。
   - 断言新 facts、`alphafold_categories`、`alphafold_plddt`、links、coverage。
   - 无逐残基文档时降级且 caveat 存在。
3. `tests/unit/test_chapter_specs.py`
   - 新 FACT_LABELS、`pct` 格式化、KPI 卡片。
4. `tests/integration/test_vertical_slice.py`
   - fixture 增加逐残基缓存。
   - 报告 HTML 含 `alphafold-residue`、`alphafold-confidence` 与图题。
5. 打印/CLI 测试
   - `_print.html` 含「结构置信度」速览行。
6. 全量 `uv run pytest` 通过。

## 10. 文件影响

| 文件 | 变更 |
|---|---|
| `src/target_profile/api/alphafold.py` | 新增 `alphafold_confidence` |
| `src/target_profile/cli.py` | fetch 步骤；`BUILDERS["basic"]` |
| `src/target_profile/models.py` | `ModuleResult.links` |
| `src/target_profile/analysis/basic.py` | facts、表格、链接、caveats |
| `src/target_profile/figures/chart_specs.py` | `build_basic` |
| `src/target_profile/report/chapter_specs.py` | KPI、标签、hidden_tables |
| `src/target_profile/report/render.py` | links、summary、print 行、limitations |
| `src/target_profile/report/templates/report.html.j2` | 链接行 |
| `src/target_profile/report/static/dashboard.css` | `.block-links` |
| `src/target_profile/report/print.css` | 打印隐藏链接 |
| 测试与 fixture | 见第 9 节 |

## 11. 验收标准

1. `uv run pytest` 全绿。
2. 对 KRAS / TP53（已有缓存）执行 `fetch --refresh` 后，`run --offline --format both`：
   - 第 2 章出现两张 AlphaFold 图。
   - KPI 含平均 pLDDT 与高置信占比。
   - 摘要含 AlphaFold pLDDT 项。
   - 明细含置信度分级表与版本/覆盖度。
   - 外链为 AlphaFold DB / PDB / CIF。
3. 旧缓存（无逐残基 JSON）生成成功，只缺曲线图并有 caveat。
4. 报告仍为单文件、无外链资源（锚点外链除外）、PDF 5 页。
5. 报告中无“结构准确/高精度”等越界表述。

## 12. 未包含

- 3D 结构查看器（3Dmol/NGL）。
- PAE 矩阵图。
- 突变位点在结构上的映射。
- 复合物或配体结合构象。
