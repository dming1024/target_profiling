# 靶点画像 HTML 报告重设计

- 日期：2026-11-03
- 状态：已与用户确认（视觉方向 A、表格收敛策略、PDF 精简版范围）
- 影响范围：报告渲染层（模板 / CSS / 渲染代码 / PDF 流程）
- 不改动：分析模块、facts/tables 数据结构、CLI 参数、数据采集与缓存

## 1. 背景与问题

当前报告每个模块无条件渲染全部内容：

- 所有 facts 变成卡片（安全章节 13 张、表达章节 11 张），长文本字段撑满卡片；
- 所有表格最多 20 行全部铺开，EGFR 报告共 22 张表、约 400+ 数据行；
- 所有图表整宽排列（18 张，每张高 280–420px）；
- 同一组数字同时出现在正文、fact 卡片、图表和表格中；
- 表头保留 DataFrame 原始英文列名，表标题是下划线转换后的英文；
- 页面极长，对交付对象不友好，也降低了关键结论的可见性。

目标不是删信息，而是**结论先行、主次分层、明细可展开**。

## 2. 目标与非目标

### 目标

1. 每章统一为「KPI → 结论 → 图表 → Top 主表 → 折叠明细」的固定节奏。
2. 默认页面只展示每章 3–4 个关键数字、1 张主表（5–8 行）和全部图表；其余明细折叠。
3. 表头、表标题全部中文化，数值格式统一。
4. 保留现有暗色视觉基因并细化（方向 A「深色实验室」）。
5. 新增独立的 3–5 页浅色 PDF 精简版，适合打印和快速汇报。
6. 保持自包含单文件、离线运行、现有测试全通过。

### 非目标

- 不修改任何 analysis 模块、facts/tables 键、图表 option。
- 不实现 Tier 3（PGx/文献/GWAS）内容。
- 不增加新数据源、不改变 LLM 提示词与守卫。
- 不提供浅色 HTML 主题（浅色仅用于 PDF 精简版）。
- 不做表格排序/筛选等前端交互。

## 3. 信息架构

### 3.1 单章模板

每个模块块（`ModuleResult`）按以下顺序渲染：

1. **章节头**：编号章 + 标题；右侧 1 个状态标签（`status`）。
2. **KPI 条**：3–4 个关键指标，单面板四列，竖线分隔。
3. **结论**：沿用 `module.narrative`；缺失时回退到规则句；超过 200 字截断并进折叠区。
4. **图表**：全部图表，双列网格；窄屏单列。
5. **主表**：仅 1 张，最多 8 行，中文表头。
6. **折叠明细** `<details>`：
   - 其余表格（每张仍最多 20 行）；
   - 剩余指标键值清单（两列）；
   - 超长字段全文；
   - caveats。

第 6 章包含 `dependency` 与 `cancer` 两个块，各自独立重复上述结构（共享章节头，块内带小标题）。

### 3.2 执行摘要（第 1 章）

替代现有 10 张卡片，改为：

- **结论横幅**：基因符号 + 蛋白全名/定位 + 一句功能概述（截断 120 字）+ 5 个状态 chip（可成药性、驱动状态、组织表达模式、LoF 约束、泛癌必需）。
- **三个主题分组**（每组分 4–5 个「指标 / 值」行）：
  1. 靶点定位：靶点类别、蛋白长度、最高表达组织、亚细胞定位（截断）。
  2. 疾病与变异：Top 关联疾病 + 评分、疾病关联总数、泛癌突变率、最高癌种 + 频率、ClinVar 记录数。
  3. 依赖 · 成药 · 风险：强依赖细胞系/总数、可成药性 + 已批准药物数、安全事件数、小鼠表型数、癌症驱动状态、LoF 约束。
- 数据直接从各模块 `facts` 读取；`summary.label_cards` 继续保留在 facts.json 中，供兼容与测试使用。

### 3.3 附录

保持现有内容，重排为：

- 数据源与许可（表）
- 标签阈值（表）
- 缺失维度
- 方法学局限
- LLM 使用情况

第 12 章占位改为单行紧凑提示，不再占整块空白。

## 4. 章节配置（`chapter_specs.py`）

新增模块级配置，键为 `ModuleResult.name`。字段：

```python
@dataclass(frozen=True)
class ModuleSpec:
    kpi: tuple[str, ...]          # 3-4 个 facts 键
    status: str | None            # 状态规则 id；None 表示不显示
    primary_table: str | None
    secondary_tables: tuple[str, ...]
    primary_charts: tuple[str, ...]   # 供 PDF 精简版使用
    table_rows: int = 8               # 主表行数上限
```

### 4.1 各模块配置

| module | KPI facts | 状态规则 | 主表 | 次表 | 图表 |
|---|---|---|---|---|---|
| basic | protein_length, target_class, subcellular_locations, alphafold_mean_plddt | 靶点大类 | — | — | — |
| disease | disease_count, top_disease, top_disease_score, clinvar_total | 约束状态 | diseases | datasources, constraint, clinvar | disease-top |
| expression | gtex_tissue_count, gtex_top_median_tpm, tau, depmap_n_lines | τ 分类 | gtex | gtex_percentile, depmap_lineage, depmap_lines | expression-gtex |
| mutation | overall_freq_pct, top_cancer_freq_pct, n_mutated_samples, top_protein_change | 频率高低 | cancers | types, protein_changes | mutation-cancers |
| dependency | strong_dependency_count, strong_dependency_fraction, median_effect, top_lineage | 依赖强度 | by_lineage | distribution, strong_lines | dependency-dist |
| cancer | n_cancer_hallmarks, top_hallmark, driver_status, essential | 驱动状态 | hallmarks | — | cancer-hallmarks |
| pathway | n_pathways, top_level_term, n_go_terms, n_partners_high_conf | 主要通路类别 | pathways | top_levels, go_terms, partners | pathway-network |
| ptm | n_ptm_sites, top_ptm_type, n_domains, sequence_length | 主要 PTM 类型 | ptm_sites | ptm_types, domains | ptm-sites |
| tractability | tractable, max_clinical_stage, n_drugs, approved_drug_count | 可成药性 | drugs | tractability, probes, drug_stages | tractability-heat |
| safety | n_safety_liabilities, top_safety_event, n_mouse_phenotypes, constrained | 安全记录 | liabilities | mouse_phenotypes, expression_breadth | safety-mouse |
| comparative | n_homologues, top_homologue_identity, n_paralogues, top_paralogue_identity | 同源数量 | homologues | — | comparative-identity |

KPI 值支持复合展示：`top_disease` 拼接评分显示为「NSCLC · 0.85」；`top_protein_change` 拼接计数显示为「A289V · 23 次」。

### 4.2 状态规则

| 规则 id | 依据 | 输出 |
|---|---|---|
| target_class | `target_class` 第一段 | 如 `Kinase` |
| constraint | `constrained` / `loeuf` | 强约束 / 无强约束 |
| tau | `tau` 与 settings 阈值 | 组织特异 / 偏特异表达 / 广泛表达 |
| mutation_freq | `overall_freq_pct` 与阈值 | 高频突变 / 低频突变 |
| dependency | `mean_effect` 与阈值 | 强依赖 / 非强依赖 |
| driver | `driver_status` | 原值 |
| pathway | `top_level_term` | 原值 |
| ptm | `top_ptm_type` | 原值 |
| tractable | `tractable` | 可成药 / 未证实 |
| safety | `n_safety_liabilities` | `N 条安全事件` / `无安全记录（不代表安全）` |
| homologue | `n_homologues` | `N 个同源基因` |

### 4.3 主表选择理由

- disease：疾病关联是核心结论，主表用 Top 疾病；约束、ClinVar、证据源进折叠。
- expression：主表用 GTEx 组织表（最常被引用）；百分位、DepMap 谱系/细胞系进折叠。
- mutation：主表用癌种频率；突变类型与蛋白改变进折叠（蛋白改变已由图表呈现）。
- dependency：主表用谱系中位效应；分布与最强依赖细胞系进折叠。
- pathway：主表用 Reactome 通路清单；类别计数、GO、互作伙伴进折叠。
- ptm：主表用位点表；类型计数与结构域进折叠。
- tractability：主表用药物/临床候选；可成药桶、探针、阶段计数进折叠。
- safety：主表用安全事件；小鼠表型与表达广度进折叠。
- comparative：只有一张表，直接作为主表。

## 5. 表格策略

### 5.1 行数与截断

- 主表最多 8 行（`table_rows` 默认 8）；若数据不足则全部显示。
- 折叠区表格最多 20 行（与现状一致）。
- 单元格文本超过 60 字截断加 `…`；长字段（function_summary、subcellular_locations、domain_summary、mouse_phenotype_examples）超过 120 字截断，全文进折叠明细。
- 折叠标题必须说明内容规模，例如「展开全部 54 个组织 · 2 张明细表 · 8 项指标」。

### 5.2 中文表头映射（全量）

| 表 | 列 → 中文 |
|---|---|
| diseases | disease_id 疾病 ID · disease 疾病 · score 关联评分 · datasources 证据源数 |
| datasources | datasource 证据来源 · diseases 涉及疾病数 |
| constraint | type 变异类型 · score 约束评分 · oe 观察/预期 · oe_upper OE 上限 |
| clinvar | variant 变异 · classification 临床分类 · review 审阅状态 |
| gtex | Tissue 组织 · median 中位 TPM · mean 平均 TPM · max 最大 TPM · count 样本数 |
| gtex_percentile | Tissue 组织 · percentile 组织内百分位 |
| depmap_lineage | OncotreeLineage 谱系 · median 中位 log2(TPM+1) · mean 平均 · count 细胞系数 |
| depmap_lines | ModelID 模型 ID · value log2(TPM+1) · CellLineName 细胞系 · OncotreeLineage 谱系 · OncotreePrimaryDisease 原发疾病 |
| cancers | studyId 研究 ID · cancer 癌种 · n_samples 样本数 · n_mutated_samples 突变样本数 · n_mutations 突变数 · freq_pct 突变率 (%) |
| types | mutationType 突变类型 · count 计数 |
| protein_changes | proteinChange 蛋白改变 · count 计数 |
| distribution / strong_lines | ModelID 模型 ID · effect Chronos 效应 · CellLineName 细胞系 · OncotreeLineage 谱系 · OncotreePrimaryDisease 原发疾病 |
| by_lineage | OncotreeLineage 谱系 · median 中位 Chronos 效应 · mean 平均效应 · count 细胞系数 |
| hallmarks | impact 影响 · label Hallmark · promotes 促进 · suppresses 抑制 · total 合计 |
| pathways | pathwayId 通路 ID · pathway 通路 · topLevelTerm 顶层类别 |
| top_levels | topLevelTerm 顶层类别 · count 通路数 |
| go_terms | aspect GO 方面 · term GO 条目 · evidence_count 证据数 |
| partners | preferredName_B 互作伙伴 · score 互作分数 |
| ptm_sites | type 修饰类型 · position 位置 · end 结束位置 · description 描述 |
| ptm_types | type 修饰类型 · count 位点数 |
| domains | type 类型 · name 名称 · start 起点 · end 终点 |
| tractability | modality 模态 · bucket 可成药桶 · available 可用 |
| probes | probe 探针 · drug_id 药物 ID · mechanism 机制 · high_quality 高质量 |
| drugs | drug 药物 · drug_id 药物 ID · stage 阶段 · diseases 适应症 |
| drug_stages | stage 阶段 · count 药物数 |
| liabilities | event 安全事件 · datasource 数据源 · effect 影响 · studies 研究数 |
| mouse_phenotypes | phenotype_class 表型类别 · models 模型数 |
| expression_breadth | tissue 组织 · median 中位 TPM |
| homologues | species 物种 · type 同源类型 · identity 一致性 (%) · target_gene_id 目标基因 ID |

表标题也中文化：`gtex_percentile` → 「组织内表达百分位」，`top_levels` → 「Reactome 顶层类别」，`go_terms` → 「GO 条目」，`partners` → 「高置信互作伙伴」，以此类推。

### 5.3 数值格式

- 列名或以 `_pct` 结尾：保留 2 位小数并加 `%`。
- `score`、`median`、`mean`、`effect`、`oe`、`oe_upper`、`percentile`、`tau`、`pli`、`loeuf`、`lof_oe`：3 位小数。
- `identity`：1 位小数加 `%`。
- 计数类（`count`、`n_*`、`models`、`studies`、`diseases`、`samples` 等）：整数 + 千分位。
- 布尔列 `available`、`high_quality`：`Yes` / `No`。
- 空值统一显示 `—`。
- 表格数值列右对齐并使用等宽数字。

### 5.4 值的中文化（可选映射）

- `stage`：`APPROVAL` → 已批准，`PHASE_3` → III 期，`PHASE_2` → II 期，`PHASE_1` → I 期，其余保留原值。
- `type`（同源）：`ortholog` → 直系同源，`within_species_paralog` → 种内旁系同源。
- `impact`（hallmark）：`promotes` → 促进，`suppresses` → 抑制。

## 6. 视觉系统（方向 A）

### 6.1 设计令牌

| 令牌 | 值 |
|---|---|
| `--bg` | `#0b1017` |
| `--panel` | `#121a25` |
| `--panel-2` | `#0f1620` |
| `--line` | `rgba(130,160,190,.18)` |
| `--text` | `#e8eff8` |
| `--body` | `#c3d0e0` |
| `--muted` | `#8294a9` |
| `--cyan` | `#4fd1c5` |
| `--blue` | `#6ea8fe` |
| `--amber` | `#f0b053` |
| `--rose` | `#f27d9a` |
| `--green` | `#75d88a` |
| `--violet` | `#a78bfa` |

字体：Space Grotesk 500/700（拉丁与数字），中文回退 `PingFang SC` / `Noto Sans SC` / `Microsoft YaHei`；数值使用 `font-variant-numeric: tabular-nums`。

### 6.2 排版尺度

- Hero 基因名：`clamp(44px, 6vw, 72px)`（现为 56–104px）。
- 章节标题：20px / 700；章节编号 chip：11px 等宽。
- KPI 数值：26px / 650；KPI 标签：10px 等宽大写；单位：11px muted。
- 正文与结论：12.5–13.5px，行高 1.7。
- 表格：11.5–13px，行高 32–34px；表头 10px 等宽大写。
- 章节间距 48px；面板内边距 12–18px；面板圆角 8–10px。

### 6.3 组件

- **KPI 条**：单面板四列，列间 1px 分隔线；无独立卡片阴影。
- **状态 chip**：圆角胶囊，按语义着色（ok 绿、warn 琥珀、info 蓝、中性灰）。
- **图表面板**：双列网格，单图高度 280–320px；标题 11px 等宽；副标题 10.5px muted。
- **主表面板**：无斑马纹，仅 1px 行分隔；数值列右对齐；首列可换行。
- **折叠控件**：`<details>` + 自定义 summary，右侧 chevron 旋转；summary 文案包含数量说明。
- **空状态**：紧凑面板，图标 + 一行说明 + caveat。
- **动效**：保留现有 reveal 淡入与 TOC 高亮，尊重 `prefers-reduced-motion`。
- **响应式**：>1000px 左 TOC + 主内容；≤1000px TOC 变顶部横滑；≤620px 全部单列。

### 6.4 删除项

- 删除全量 facts 卡片墙（`.cards.g3` 在正文中的使用）。
- 删除 `table.dt` 直接铺表的默认行为。
- 页面不再出现原始英文表标题和英文列名。

## 7. 图表策略

- 保留全部 18 张图，双列并排；每图高度 280–320px。
- 图表 option、标题、副标题、数据不变。
- 图表顺序沿用模块内顺序。
- 图表面板与 KPI、表格之间保持 12–16px 间距。
- PDF 精简版只选择每模块 `primary_charts` 中的 1 张（见第 8 节）。

## 8. PDF 精简版（3–5 页）

### 8.1 生成方式

- 新增独立模板 `report/templates/print.html.j2` 与浅色样式 `report/static/print-speedread.css`。
- 使用与网页相同的数据上下文，但只渲染：封面/摘要、12 维速览、8 张主图、数据源与局限。
- 模板同样内联 `echarts_js` 与 `dashboard_js`，以复用 `registerTheme` 与 `__snapshotCharts()`；TOC/reveal 选择器在打印页不存在，不会产生副作用。
- CLI 在 `--format pdf|both` 时：
  1. 渲染临时文件 `out/<SYMBOL>_<date>/_print.html`；
  2. 用 Playwright 载入、`__snapshotCharts()`、打印 PDF；
  3. 无论成功失败，在 `finally` 中删除 `_print.html`。
- `report.html` 与 `facts.json` 的产出逻辑不变；PDF 失败仍返回 exit 4。

### 8.2 页面结构

| 页 | 内容 |
|---|---|
| P1 | 封面 + 执行摘要：基因名、蛋白名、一句概述、5 个 chip、4 个核心数字、三组主题结论（紧凑版） |
| P2 | 12 维速览表：每行「维度 / 核心指标 / 数值 / 状态」，一行一个维度 |
| P3 | 核心图表 I：表达、突变、依赖、疾病（2×2） |
| P4 | 核心图表 II：可成药性、安全、通路网络、癌症 hallmark（2×2） |
| P5 | 数据源与许可、标签阈值、方法学局限、LLM 使用情况 |

- 固定 A4，页边距 12mm，浅色背景 `#fffdf8` / 白面板 / 深青 `#0f6b5c` 强调色。
- 页码显示在页脚；`break-after: page` 控制分页。
- 若某主图缺失，图表位置自动收缩；页面数可为 3–4 页，但不使用空白占位撑页。
- 字体：拉丁与数字 Space Grotesk，中文系统回退；不嵌入额外字体文件（现有字体已内嵌）。

## 9. 实现设计

### 9.1 文件改动

| 文件 | 改动 |
|---|---|
| `report/chapter_specs.py` | 新增：`ModuleSpec`、模块配置、表标题、列中文映射、值映射、格式化与状态规则 |
| `report/render.py` | 重构：抽出共享上下文构建；`_block` 改为生成 KPI/主表/折叠明细；新增 `render_print_report` |
| `report/templates/report.html.j2` | 重写 section 与附录渲染；新增 KPI、状态 chip、details 结构 |
| `report/templates/print.html.j2` | 新增 5 页精简模板 |
| `report/static/dashboard.css` | 更新设计令牌与组件样式；删除卡片墙样式 |
| `report/static/print-speedread.css` | 新增 PDF 精简版样式 |
| `report/print.css` | 保留，作为浏览器手动打印 `report.html` 的降级样式 |
| `cli.py` | PDF 分支改为渲染 `_print.html` 后打印并清理 |

### 9.2 渲染数据结构

`_block(module)` 输出：

```python
{
  "id": module.name,
  "title": ...,
  "status": {"text": "偏特异表达", "level": "info"},
  "kpis": [{"label": ..., "value": ..., "unit": ..., "hint": ...}],
  "narrative": ...,
  "charts": [...],
  "primary_table": {"title": "Top 8 组织表达", "html": ...} | None,
  "details": {
      "summary": "展开全部 54 个组织 · 2 张明细表 · 8 项指标",
      "tables": [...],
      "metrics": [{"label": ..., "value": ...}],
      "caveats": [...],
      "long_text": [{"label": ..., "text": ...}],
  },
}
```

`summary` 段（第 1 章）输出独立的 `verdict` 与 `groups` 结构。

### 9.3 共享上下文

抽出 `build_report_context(gene, modules, llm_info)`，返回模板块、chart_payload、appendix、hero 数据等。`render_report` 与 `render_print_report` 共用该函数，避免两份逻辑漂移。`render_report` 签名与返回值保持不变。

### 9.4 自包含约束

- 仍不引入任何外链；字体与 ECharts 继续内联。
- print.html 使用同一 `chart_payload` 子集与内联 CSS，不写外部资源。
- 临时 print 文件不留在交付目录。

## 10. 降级与边界情况

- 模块 `no_data`：紧凑空状态 + caveats；章节保留，TOC 不隐藏。
- 主表缺失：跳过主表，折叠区仍展示可用指标与表格。
- 图表不可序列化：沿用现有跳过逻辑并追加 caveat。
- 长文本：截断到 120 字；全文进折叠区。
- 缺省阈值（settings 不可用）：状态规则回退到中性 chip 或省略。
- 模块 facts 键缺失：KPI 自动跳过该卡，不显示空值。
- 第 12 章：单行提示「药物基因组学 / 文献 / GWAS 证据将在后续版本提供」。

## 11. 测试计划

### 11.1 单元测试

- `chapter_specs`：`CHAPTERS` 中出现的每个模块都有配置；KPI 键与主表键在真实模块中存在（fixture 下可选）；每个表都有列映射；所有映射列在真实 DataFrame 中存在（以 EGFR fixture 为准）。
- 格式化：百分比、比例、千分位、空值 `—`、布尔 Yes/No。
- 表头中文化：渲染后的主表不含原始英文列名（`Tissue`、`median`、`score` 等）。
- 行数：主表 ≤ 8 行；折叠表 ≤ 20 行。
- 折叠：`<details>` 存在，summary 含数量说明；完整表行数大于主表。
- 长文本：截断标记 `…` 与全文同时存在。
- 执行摘要：三个主题分组、5 个 chip 均出现。
- 打印模板：5 个 page 容器、8 个 chart 占位、包含数据源与局限；无外链。
- 现有 `tests/unit/test_render.py`、`test_summary.py` 等保持通过；如断言旧标记则更新为新结构。

### 11.2 集成 / 验收

- `uv run pytest` 全部通过（当前 86 个）。
- 对 EGFR / KRAS / TP53 / TOP1 运行 `--offline --format both`：
  - `report.html`、`facts.json`、`report.pdf` 存在；
  - PDF 页数 3–5（`pdfinfo` 或 Playwright 验证）；
  - HTML 自包含、无外链；
  - 主表与折叠明细符合行数规则。
- 视觉检查：Playwright 截取整章与 PDF 页面，确认层级、对比度、无溢出。
- 页面长度：EGFR 报告滚动高度相对当前版本下降 ≥ 40%（Playwright 测量）。

## 12. 验收标准

1. 每章默认最多 1 张主表（≤ 8 行）与 1 个折叠明细区。
2. 用户可见表头与表标题均为中文；数值格式统一。
3. 每章有 3–4 个 KPI 与状态 chip，结论句为首屏可见内容。
4. 全部图表保留并双列展示。
5. 执行摘要使用三个主题分组，不再出现 10 张卡片墙。
6. PDF 为 3–5 页浅色精简版，包含封面摘要、12 维速览、8 张主图、数据源与局限。
7. HTML 仍为单文件自包含，离线可用。
8. `uv run pytest` 全部通过，CLI 退出码语义不变。

## 13. 风险

- **章节配置遗漏**：用单元测试覆盖所有模块键，并在渲染时对未知键回退到默认（无 KPI、无主表、全部进折叠）。
- **PDF 页数不稳定**：使用固定页面容器与分页样式；图表缺失时收缩而不是留白。
- **打印字体**：仅使用已内嵌的 Space Grotesk 与系统中文字体，避免新增网络请求。
- **旧测试断言**：渲染结构变化可能触发少量断言更新，需在实施时逐条确认，不降低覆盖。
