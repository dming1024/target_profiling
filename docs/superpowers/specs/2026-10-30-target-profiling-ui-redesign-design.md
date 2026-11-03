# 靶点画像报告 — UI 改版与 M5 收尾 设计文档

- 日期：2026-10-30
- 状态：草案（待用户审阅）
- 关联：`docs/superpowers/specs/2026-10-30-target-profiling-design.md`（下称"主 spec"）
- 项目约束：**不使用 git**（不做 commit/分支/PR；本文与后续计划均不含 git 步骤）

## 1. 背景与目标

现有报告（M0–M4）已覆盖 9 个分析维度，但页面为浅色、单列、静态 PNG 图、无导航，观感与"对外交付"定位不符。本次改版与 M5 收尾**合并为一个最终里程碑**，目标：

- 深色科幻仪表盘风格，信息层级清晰、可导航、有科技感
- 图表全部改为**内联 ECharts 交互图**，仍满足**自包含单文件 HTML + 运行时零联网**
- 一次性完成 12 章结构与 M5 功能（癌症特征、比较基因组、执行摘要、LLM 润色）
- PDF 降为可选 best-effort，不再作为默认交付物

## 2. 关键决策

1. **单文件内联**：ECharts、CSS、JS、图表配置全部内联进 `report.html`，不产生 `assets/` 目录，不引用任何外部 URL。
2. **图表引擎**：弃用 matplotlib 报告图，统一 ECharts 5.5.1（Apache-2.0，随包 vendor 并内联）。Python 只构建 ECharts `option` 数据，不负责绘制。
3. **主题**：深色科幻仪表盘（参考 `test_kras_reprot.html` 的视觉语言）。
4. **字体**：不引 Google Fonts。内嵌一枚拉丁显示字体（Space Grotesk，OFL，woff2 子集，约 30KB）；中文走系统 CJK 字体栈；等宽标签用系统等宽栈。
5. **路线图**：M5 功能 + UI 改版合并交付。
6. **交付物默认**：`target-profile run` 默认只产 `report.html` + `facts.json` + `run.log`；`--format pdf|both` 保留为 best-effort。

## 3. 范围

### 本里程碑包含

- 12 章 + 附录的固定信息架构，左侧粘性目录与滚动高亮
- 深色视觉系统（配色、字体、网格背景、卡片、面板、提示条）
- 8 个现有维度的 ECharts 交互图重写
- M5 功能：`cancer`（癌症特征）、`comparative`（比较基因组）、`summary`（执行摘要标签卡）、LLM 润色、第 12 章占位、附录
- 数据模型扩展：`ChartSpec`、`ModuleResult.charts`、`ModuleResult.narrative`、`ModuleResult.label_cards`
- 渲染管线重写与自包含保证
- 测试重写（ECharts builder 单测、渲染单测、离线集成）

### 非目标

- 不引入前端框架（React/Vue）、不引入构建步骤
- 不做网页服务端、不做批量输入（架构预留即可）
- 不做图表导出按钮、暗/亮主题切换
- 不做 Tier3（药物基因组学/文献）内容，仅占位

## 4. 信息架构（12 章 + 附录）

章节顺序固定，**不依赖模块注册顺序**：

| # | 章节标题 | 数据模块 |
|---|---|---|
| 1 | 执行摘要 | `summary`（新） |
| 2 | 基因与蛋白基础 | `basic` |
| 3 | 疾病关联与遗传证据 | `disease` |
| 4 | 表达 | `expression` |
| 5 | 突变与变异 | `mutation` |
| 6 | 依赖性与癌症特征 | `dependency` + `cancer`（新） |
| 7 | 通路与相互作用 | `pathway` |
| 8 | 蛋白修饰 | `ptm` |
| 9 | 可成药性与药物 | `tractability` |
| 10 | 安全性与风险 | `safety` |
| 11 | 比较基因组学 | `comparative`（新） |
| 12 | 药物基因组学/文献 | 静态占位（"暂未包含"） |
| 附录 | 来源/版本/许可、缺失维度、LLM 使用、方法学局限 | 汇总 |

每章结构：中文解读段（可选）→ 图表 → 事实卡 → 数据表 → caveat 提示条。无数据时整章显示空状态面板。

## 5. 数据模型与模块契约

### 5.1 `ChartSpec`（定义于 `models.py`）

`ChartSpec` 与 `ModuleResult` 同处 `models.py`，避免 `figures` 与 `models` 的循环依赖；`figures/chart_specs.py` 只导入并使用它。

```python
@dataclass(frozen=True)
class ChartSpec:
    id: str                 # 全局唯一，如 "expression-gtex"
    title: str              # 英文标题
    subtitle: str = ""      # 英文副标题/来源
    option: dict[str, Any] = field(default_factory=dict)  # ECharts option
```

- `option` 为纯 JSON 可序列化字典，不包含函数；主题由 JS 统一注入。
- 空数据时 builder 返回带 `graphic` 文本"暂无可用数据"的最小 option，`id` 不变。

### 5.2 `ModuleResult` 扩展

```python
@dataclass
class ModuleResult:
    name: str
    status: Literal["ok", "no_data"] = "ok"
    facts: dict[str, Any] = field(default_factory=dict)
    tables: dict[str, Any] = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)
    charts: list[ChartSpec] = field(default_factory=list)   # 新增，替代 figure_paths
    narrative: str | None = None                            # 新增，中文解读段
    label_cards: list[dict] = field(default_factory=list)   # 新增，仅 summary 使用
    def degrade(self, reason: str) -> "ModuleResult": ...
```

- `figure_paths` 移除；所有图改由 `charts` 承载。
- `label_cards` 元素：`{"label": str, "value": str, "level": "ok"|"warn"|"info"}`。

### 5.3 M5 新模块契约

- `analysis/cancer.py`：输入 OT `hallmarks`；产出 `facts`（`n_cancer_hallmarks`、`top_hallmark`、`essential`、`pan_cancer_freq_pct`、`driver_status`）与 `charts=[build_cancer(...)]`。`driver_status` 取值："驱动证据阳性 / 证据不足 / 未知"：优先读 OT `isCancerDriverGene`（若 API 返回该字段），否则由"泛癌突变率 ≥ 阈值（`pan_cancer_hotspot_pct`）或 hallmarks 命中"推导，并在 caveat 注明推导依据。
- `analysis/comparative.py`：复用 `opentargets_safety` 缓存中的 `homologues`；产出 `facts`（`n_homologues`、`top_homologue`、`top_homologue_identity`、`top_paralogue_identity`）与一致性条形图。
- `analysis/summary.py`：读取全部模块 facts，按主 spec §6.12 阈值生成 `label_cards`（组织特异/泛癌高频突变/强依赖/泛癌必需/强约束/可成药性/癌症驱动/安全警示），不改写数字。
- LLM：新增 `llm/` 包（client/prompts/guard/cache），为各模块生成 `narrative`；失败或 `--no-llm` 时回退规则模板。guard 数字必须命中 facts 白名单。

### 5.4 API 增量

- `api/opentargets.py` 新增 `target_cancer(ensembl, fetcher, refresh=False)`，缓存名 `opentargets_cancer`，GraphQL 取 `hallmarks { label impact }`（必要时含驱动相关字段）。
- `fetch` 增加 "Open Targets cancer" 步骤。
- `comparative` 不新增 API；读取 `opentargets_safety` 载荷中的 `homologues`。

## 6. 视觉设计系统

### 6.1 颜色（CSS 变量）

```
--bg:#080b10; --bg-2:#0c1118; --panel:#111822; --panel-2:#0f1620;
--line:rgba(120,160,200,.14); --text:#e7eef7; --muted:#8b9bb0;
--cyan:#55d6be; --amber:#f0b053; --blue:#6ea8fe;
--rose:#f27d9a; --green:#75d88a; --violet:#a78bfa;
--accent-grad: linear-gradient(120deg,#55d6be,#6ea8fe);
```

- 蓝色/青色为主强调，琥珀用于 caveat 与警示，玫红用于异常/高分风险，绿色为正向。
- 图表色板顺序：`["#55d6be","#6ea8fe","#f0b053","#f27d9a","#75d88a","#a78bfa"]`。

### 6.2 字体

```
--font-sans: "Space Grotesk", system-ui, -apple-system, "PingFang SC",
             "Noto Sans SC", "Microsoft YaHei", sans-serif;
--font-mono: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
```

- Space Grotesk 以 woff2 子集内嵌（`@font-face` base64），仅含拉丁与常用符号；中文自动回退系统字体。
- mono 用于 eyebrow、ID 徽章、图注、表格数字。

### 6.3 布局

- `.shell` 两列：`240px` 粘性目录 + 主内容（`max-width:1080px`，居中，左右留白）。
- 背景：`--bg` 上叠加 40px 蓝图网格（`linear-gradient` 细线）+ 顶部径向青色光晕。
- Hero：eyebrow `TARGET PROFILE` + 超大基因符号 + 中文副标题 + ID 徽章行（Ensembl / UniProt / chr / 生成时间）。
- 目录项：两位编号 + 标题；当前章高亮（左侧青色竖条 + 文字提亮）。
- 响应式：`<1000px` 时目录折叠为顶部横向条；图表宽度自适应。

### 6.4 组件

- `panel`：`--panel` 底、1px `--line` 边、圆角 14px、内边距 18–24px。
- 事实卡网格：`.cards.g2/.g3/.g4`，卡内 `label`（muted、mono）+ `value`（大号、强调色）。
- 表格：无外边框、行悬浮高亮、表头 mono 小字、数值右对齐。
- caveat：琥珀左边框提示条，前缀"注："。
- 空状态：面板内居中 `--muted` 文案 + 图标字符。
- 页脚：数据源署名、许可、免责声明、ECharts/字体许可。

### 6.5 动效

- 章节进入视口淡入上移（IntersectionObserver，`prefers-reduced-motion` 时禁用）。
- 目录滚动高亮（IntersectionObserver 或 scroll 节流）。
- ECharts 入场动画使用内置 `animationDuration`；tooltip 跟随。

## 7. 图表规范（逐模块）

| 模块 | chart id | ECharts 类型 | 数据 / 备注 |
|---|---|---|---|
| expression | `expression-gtex` | 横向 bar | `tables["gtex"]` top20，x=median TPM |
| expression | `expression-depmap` | 横向 bar | `tables["depmap_lineage"]` top12 |
| mutation | `mutation-cancers` | 横向 bar | `tables["cancers"]` top15，% |
| mutation | `mutation-proteins` | 横向 bar | `tables["protein_changes"]` top10 |
| dependency | `dependency-dist` | bar（分箱直方图） | `tables["distribution"]` 的 effect 分 30 箱 |
| dependency | `dependency-lineage` | 横向 bar | `tables["by_lineage"]` top12 |
| cancer | `cancer-hallmarks` | 横向 bar | hallmarks label×impact |
| pathway | `pathway-levels` | 横向 bar | `tables["top_levels"]` top10 |
| pathway | `pathway-network` | graph（签名图） | 中心基因 + `tables["partners"]` top30，边宽∝score |
| ptm | `ptm-types` | 横向 bar | `tables["ptm_types"]` |
| ptm | `ptm-sites` | scatter（lollipop） | x=位置，y=类型，叠加 `domains` 色带（`markArea`） |
| disease | `disease-top` | 横向 bar | `tables["diseases"]` top12 |
| disease | `disease-sources` | 横向 bar | `tables["datasources"]` top12 |
| tractability | `tractability-heat` | heatmap | modality × bucket |
| tractability | `tractability-stages` | 横向 bar | `tables["drug_stages"]` |
| safety | `safety-mouse` | 横向 bar | `tables["mouse_phenotypes"]` top12 |
| safety | `safety-breadth` | 横向 bar | `tables["expression_breadth"]` top15 |
| comparative | `comparative-identity` | 横向 bar | homologues 一致性 top12 |

统一约定：

- 英文标题/轴标签/图例；来源写入 `subtitle` 或图注（中文）。
- 数值 tooltip；长标签截断并 `tooltip` 显示全称。
- 所有图表容器高度响应式（`min(46vh, 420px)`），`resize` 时调用 `chart.resize()`。
- 无数据：`option` 仅含居中 `graphic` 文本 + 空 `xAxis/yAxis`，或渲染 `.empty` 面板。

## 8. 渲染管线与资源内联

```
cli.run
  → analysis 模块 → ModuleResult（facts/tables/caveats/charts/narrative/label_cards）
  → figures/chart_specs.build_<module>(result) 填充 charts
  → report.render.render_report(...)
       · 按固定章节顺序组装 sections（含 summary、第 12 章占位、附录）
       · 收集 chart_payload = {id: {title, option}}（JSON 可序列化）
       · 读取并内联 dashboard.css、dashboard.js、vendor/echarts.min.js、字体 base64
       · Jinja 渲染 report.html
  → 写 report.html / facts.json
  → （可选）pdf
```

### 8.1 章节组装

`render.py` 内定义固定章节表，一个章节可聚合一个或多个 `ModuleResult`：

```python
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
```

- 章节缺失对应模块结果时整章降级为空状态，并在附录记为缺失。
- 附录由 `render_report` 生成，数据来自 `licenses.yaml`、各模块 `status`、LLM 使用信息。
- 渲染函数签名扩展：

```python
def render_report(
    gene: GeneContext,
    modules: list[ModuleResult],
    out_dir: Path,
    *,
    llm_info: dict | None = None,
) -> tuple[Path, Path]:
```

模板要点：

- `<script id="chart-data" type="application/json">{{ chart_payload | tojson }}</script>`（`tojson` 对 `<`/`>`/`&` 转义，避免截断脚本）。
- 每个图位：`<div class="chart" data-chart-id="{{ spec.id }}"></div>`。
- 章节锚点 `id="ch-<n>"`；目录由 sections 生成。
- CSS/JS 以内联 `<style>`/`<script>` 嵌入，**不得**出现外链 `src`/`href`/`@import url(http`/`url(http`。

`dashboard.js` 职责：

1. 读取 `chart-data` → `JSON.parse`
2. `echarts.registerTheme("target", {...})`（配色、字体、轴、tooltip）
3. 遍历 `.chart[data-chart-id]` → `init` + `setOption`
4. 响应式 `resize`
5. 目录滚动高亮 + 章节淡入
6. `window.__snapshotCharts()`：用 `chart.getDataURL({type:"png",pixelRatio:2,backgroundColor:"#0b1118"})` 将每个图替换为 `<img>`，供 PDF 打印

## 9. 降级与错误处理

- 维度 `status=="no_data"`：章节渲染空状态面板 + caveats，不渲染图表。
- 单个 builder 异常：跳过该图，记 `run.log` 警告，其余继续。
- chart 配置缺失/无法序列化：跳过该图并警告。
- 所有分析层原有降级语义不变（`degrade`，不抛错）。
- 退出码保持：基因无法解析 2、数据缺失 3、PDF 失败 4（仅在请求 PDF 时）。

## 10. PDF 策略

- `--format` 默认改为 `html`。
- `--format pdf|both`：Playwright 打印前执行 `window.__snapshotCharts()`，把交互图转为静态 PNG；`print.css` 将深色面板转为浅色可打印样式（或在深色下保持可读的浅色文字反向处理）。
- PDF 失败：保留 HTML，退出码 4（沿用）。
- PDF 为 best-effort，不保证交互能力与屏幕一致。

## 11. 自包含保证

- 渲染完成后做结构断言（测试与运行时可选）：HTML 中不存在 `src="http`、`href="http`、`url(http`、`@import url(http`。
- ECharts、字体、CSS、JS、图表 JSON 均在文件内。
- 运行时零联网：图表初始化不发起网络请求。

## 12. M5 功能范围（合并项）

以下沿用主 spec 定义，本里程碑实现：

- `cancer`：OT hallmarks + `isEssential`（复用安全缓存）+ 驱动状态；图：hallmarks 条形。
- `comparative`：OT homologues；图：一致性条形。
- `summary`：事实标签卡，阈值取自 `config/settings.toml`，脚注公开。
- `llm/`：OpenAI 兼容接口、可插拔、`--no-llm` 跳过；`guard.py` 数字白名单与基因符号保护；缓存键（基因, facts 哈希, 模型, prompt 版本）；失败回退模板；脚注标注。
- 第 12 章占位：静态说明（Tier3 未包含）。
- 附录：数据源版本/下载日期/校验和/许可（读 `config/licenses.yaml`）、缺失维度清单、LLM 使用情况、方法学局限。

## 13. 测试策略

- `tests/unit/test_echarts.py`
  - 每个 builder 对 fixture 表产出预期 series/xAxis 结构与长度
  - 空表 → 空状态 option（含 graphic 文本）
  - option 可 `json.dumps` 序列化
- `tests/unit/test_render.py`
  - HTML 含内联 echarts 标记与 `chart-data`，JSON 可解析
  - 12 章目录锚点齐全、顺序正确
  - 事实值/表格/caveat 仍存在
  - 无外链断言
- `tests/unit/test_summary.py`：阈值标签卡正确（KRAS/TP53 fixture）
- `tests/unit/test_llm_guard.py`：数字白名单命中/拒绝、回退路径（fake client）
- `tests/integration/test_vertical_slice.py`：离线全链路 → HTML 自包含、图表 JSON 有效、9+3 模块状态 ok
- 移除 matplotlib 图相关测试；保留 analysis/facts 断言
- 不做 HTML 视觉回归；手工用 Playwright 截图验收

## 14. 文件结构变更

新增：
```
src/target_profile/figures/chart_specs.py    # 各模块 ECharts option builder
src/target_profile/analysis/cancer.py
src/target_profile/analysis/comparative.py
src/target_profile/analysis/summary.py
src/target_profile/llm/{__init__,client,prompts,guard,cache}.py
src/target_profile/report/static/dashboard.css
src/target_profile/report/static/dashboard.js
src/target_profile/report/vendor/echarts.min.js
src/target_profile/report/vendor/fonts/space-grotesk.woff2
tests/unit/test_echarts.py
tests/unit/test_summary.py
tests/unit/test_llm_guard.py
```

修改：
```
src/target_profile/models.py        # 扩展 ModuleResult；新增 ChartSpec
src/target_profile/cli.py           # chart builders；默认 html；fetch cancer
src/target_profile/report/render.py # 12 章组装、内联资源、附录、标签卡
src/target_profile/report/templates/report.html.j2
src/target_profile/report/print.css # 打印覆盖
src/target_profile/api/opentargets.py  # target_cancer
config/licenses.yaml                # ECharts Apache-2.0、Space Grotesk OFL
```

移除：
```
src/target_profile/figures/charts.py
src/target_profile/figures/theme.py
tests/unit/test_figures.py（替换为 test_echarts.py）
```

## 15. 验收标准

自动化：

- 全量 `uv run pytest` 通过（新增/改写后的用例）
- `uv run target-profile run KRAS --offline --no-llm` 产出 `report.html`，其中：
  - 含内联 ECharts、`chart-data` 可解析、12 章目录齐全
  - 无任何外部 URL 引用
  - `facts.json` 模块状态符合预期
- `--format pdf`（可选）能产出可读 PDF

手工（真实数据 KRAS/TP53）：

- 深色仪表盘视觉完整：hero、粘性目录高亮、卡片、面板、caveat
- 所有图表可交互（tooltip、hover），无破图/溢出
- 空数据章节正确显示空状态
- 附录与页脚署名/许可完整

## 16. 参考

- 视觉参考：`/root/test_kras_reprot.html`（深色仪表盘）、`/root/Biomni/Biomni/KRAS_profiling/report/KRAS_multimics_report.html`（浅色信息卡）
- 主设计：`docs/superpowers/specs/2026-10-30-target-profiling-design.md`
