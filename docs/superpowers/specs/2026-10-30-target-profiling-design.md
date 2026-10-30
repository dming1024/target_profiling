# 靶点全方位画像报告工具 — 设计文档

- 日期：2026-10-30
- 状态：已确认（第 1–3 节 + 维度扩充，用户逐节批准）
- 用途：对外交付/展示的单基因靶点画像报告

## 1. 背景与目标

输入一个基因（HGNC 符号、别名、Ensembl 或 UniProt ID），生成一份中文正文、英文图表标签的"全方位基因画像"报告，覆盖表达、突变、依赖性、通路/网络、蛋白修饰，以及对齐 Open Targets 的疾病关联、可成药性、安全性、癌症特征、比较基因组等维度。

目标：

- 自包含 HTML（图片 base64 内嵌）+ 可导出 PDF，适合对外交付
- 数据本地预下载、预聚合；**报告生成运行时零联网**（LLM 润色除外，可关闭）
- 所有数字单一来源，带数据源与版本，可追溯
- 只用开放许可数据源，满足商用合规
- CLI 单基因入口；架构预留后续批量与网页

## 2. 范围

### v1 包含

- 12 章报告，25–30 张静态图
- 维度：基因/蛋白基础、疾病关联与遗传证据、表达、突变与变异、依赖性与癌症特征、通路与相互作用、蛋白修饰、可成药性与药物、安全性与风险、比较基因组学
- CLI：`run` / `data` / `doctor` / `version`
- 规则模板文字 + 可选 LLM 润色（失败回退模板）

### v1 不包含（Tier3，后续）

- 药物基因组学、文献计量
- GWAS credible sets / L2G fine-mapping
- 单细胞表达
- AlphaFold 结构渲染（仅报告可用性）
- 批量基因输入与网页界面（架构预留）

## 3. 总体架构

5 层，单向依赖：

```
data_prep/  →  parquet/ + manifest  →  analysis/  →  figures/  →  report/
 (下载+聚合)      (DuckDB 查询)        (每维度结构化结果)   (300dpi 图)   (HTML→PDF)
                                    ↘  llm/（可选润色，失败回退模板）
```

- `data_prep` 流式下载并聚合原始大表，聚合后删除临时文件
- `analysis` 每个模块输入 `GeneContext`，输出结构化结果 dataclass
- `figures` 只消费 analysis 的结构化结果，统一主题
- `report` 用 Jinja2 渲染单文件 HTML，Playwright/Chromium 打印 PDF

## 4. 数据层

### 4.1 数据源与本地保留

| 维度 | 开放数据源 | 本地保留 |
|---|---|---|
| 表达 | GTEx v10、TCGA、DepMap/CCLE、HPA | 组织中位数/IQR、τ；癌种级分位数；细胞系×基因矩阵；HPA nTPM 与定位 |
| 突变 | TCGA MC3 MAF、gnomAD constraint | 基因×癌种频率与类型谱、蛋白位点聚合、pLI/LOEUF/mis_z |
| 依赖 | DepMap CRISPRGeneEffect (Chronos) + Model | 基因×细胞系效应矩阵、谱系统计 |
| 通路/网络 | Reactome、GO、STRING 人类 links (score≥700) | 通路归属/层级、PPI 高置信邻域 |
| PTM | UniProt curated PTM | 位点表、类型统计、结构域/区域叠加 |
| 疾病 | Open Targets associatedDiseases、ClinVar、gnomAD | 关联总数/Top/来源分解/时间趋势、致病变异、约束 |
| 可成药性 | Open Targets tractability/chemicalProbes/drugs | 分级矩阵、探针、已知药物与临床候选 |
| 安全性 | Open Targets safetyLiabilities、IMPC | 安全事件、小鼠 KO 表型、泛癌必需、表达广度 |
| 癌症特征 | Open Targets hallmarks、DepMap | hallmarks、驱动基因状态、体细胞突变证据 |
| 比较基因组 | Open Targets homologues | 直系/旁系同源、序列一致性 |
| 索引 | HGNC、Ensembl、UniProt | 别名/ID 映射、版本清单 |

### 4.2 落地规则

1. 原始大表流式聚合后立即删除（TCGA 逐癌种下载→算分位数→删；OT parquet 子集化后删原始）
2. 所有数据源版本、下载日期、校验和、许可写入 `data/manifest.json`，自动渲染到报告附录
3. `config/licenses.yaml` 维护许可登记表，随报告输出
4. 报告生成运行时零联网（LLM 除外且可关）
5. **常驻数据 ≤ 2.5GB；下载临时峰值 ≤ 10GB**。若 OT 数据导致超限，互作表继续只用 STRING，OT 互作不落地（M1 实测确认）

### 4.3 关键取舍

- TCGA 表达只存癌种级分位数，不存样本矩阵
- PPI 只存 STRING combined_score ≥ 700 的高置信邻域
- 突变热点仅由 TCGA 计数定义，不用 COSMIC

### 4.4 许可红线

- 可用：STRING 单物种 links（CC BY 4.0）、HPA（CC BY 4.0，需署名）、Open Targets Platform（CC0，上游 ChEMBL 等逐项标注）、ClinVar（公共领域）、gnomAD（开放）、IMPC（开放）、AlphaFold DB（CC BY 4.0）、GO/GTEx/Reactome/UniProt（CC BY 4.0）
- 禁用：KEGG、COSMIC/CGC、PhosphoSitePlus、dbPTM、iPTMnet
- STRING 的 detailed/full 下载（需另签）禁用，只用单物种 links

## 5. 基因解析与上下文

`gene_resolve.py` 自动识别 HGNC symbol、旧符号/别名、Ensembl ID（ENSG…）、UniProt ID；报告统一使用 HGNC 标准符号，并展示解析结果。无法解析时报错并提示相近符号。

`GeneContext`：HGNC ID、标准符号、别名、Ensembl/UniProt、坐标、转录本、蛋白长度。

## 6. 分析模块

### 通用约定

- 每模块返回：`status(ok/no_data)` + `facts(dict)` + `tables` + `figure_specs` + `caveats`
- `facts` 同时驱动模板文字与 LLM 输入，数字单一来源；所有数字带来源与版本
- 无数据维度显示"暂无可用数据"，不留空
- 明确区分"该基因无该数据"与"数据源缺失/分析失败"（后者见错误处理）

### 6.1 basic（基因与蛋白基础）

OT functionDescriptions、targetClass、biotype、subcellularLocations、proteinIds、genomicLocation、canonicalTranscript、AlphaFold 可用性；UniProt 序列与蛋白长度。

### 6.2 expression（表达）

GTEx 组织中位数 + IQR、τ 特异性；TCGA 癌种中位数/百分位；CCLE 谱系表达；HPA 共识 nTPM 与 IHC 证据（不用图片）。
图：GTEx 条形（IQR）、TCGA 点图、CCLE 点图、综合面板。

### 6.3 mutation（突变）

TCGA MC3 基因×癌种突变率、类型谱、HGVSp 位点聚合；gnomAD pLI/LOEUF/mis_z；UniProt/Pfam 结构域叠加。
图：泛癌频率条形、癌种×类型堆叠、蛋白 lollipop + 结构域、Top 热点表。
不预测致病性；热点仅由 TCGA 计数定义。

### 6.4 dependency（依赖）

DepMap Chronos 效应分布；谱系差异（Mann-Whitney + 效应量）；强依赖细胞系列表；common essential 标记；选择性评分；共依赖 Top 基因（本地矩阵即时计算）。
图：效应分布直方图、谱系箱线/点图、强依赖 Top15、共依赖散点（可选）。
明确区分泛癌必需 vs 谱系选择性依赖。

### 6.5 pathway（通路与相互作用）

Reactome 归属 + 层级；GO BP/MF/CC + 证据码；STRING ≥ 700 邻域、Top 伙伴、网络度、Reactome 复合物。
图：Reactome 顶层树图、GO 点图、PPI 网络 Top30、伙伴评分条形。

### 6.6 ptm（蛋白修饰）

UniProt curated PTM 类型统计、位点表、结构域/区域叠加、文献描述。
图：类型计数、位点 lollipop + 结构域、区域注释图。
v1 不做激酶-底物推断（无商用安全可靠源），报告注明局限。

### 6.7 disease（疾病关联与人类遗传证据）

OT associatedDiseases 总数/Top 疾病/按数据源分解/时间趋势；ClinVar 致病变异；gnomAD 约束。
图：Top 疾病关联条形、来源分解、时间趋势。

### 6.8 tractability（可成药性）

OT tractability（SM/AB/PROTAC/other × Approved Drug → Literature 分级）、口袋/配体、化学探针、known drugs 与临床候选、靶点类别、亚细胞定位、AlphaFold 可用性。
图：可成药性分级热图、药物/临床阶段条形。

### 6.9 safety（安全性与风险）

OT safetyLiabilities、IMPC 小鼠 KO 表型、common essential、LOEUF、关键组织表达广度、旁系同源补偿。
图：安全事件表、表达广度条图。
**报告明确"无记录 ≠ 安全"**（该维度天然稀疏，如 KRAS 的 safetyLiabilities 为空）。

### 6.10 cancer（癌症特征）

OT hallmarks（label + impact）、驱动基因状态、OT 体细胞突变证据（与 TCGA 互补）、isEssential/depMapEssentiality。
图：hallmarks 条形、驱动状态标签卡、体细胞证据对比。

### 6.11 comparative（比较基因组学）

OT homologues：直系/旁系同源、序列一致性、最近旁系、高置信标记。
图：同源一致性条形（含最近旁系）。

### 6.12 summary（执行摘要）

汇总各模块 facts 生成**事实标签卡**（阈值公开，见 `config/settings.toml` 的 `thresholds`）。不做主观加权评分/雷达图。

默认阈值（写入配置，报告脚注公开）：

| 标签 | 默认阈值 |
|---|---|
| 组织特异（τ） | ≥ 0.9 特异；0.6–0.9 偏特异；< 0.6 广泛表达 |
| 泛癌高频突变 | 泛癌突变率 > 5% |
| 强依赖 | 平均 Chronos 效应 ≤ -0.5 |
| 泛癌必需 | DepMap common essential 标记为真 |
| 强约束 | LOEUF < 0.6 |
| 可成药性 | OT tractability 中 SM/AB 达到 Approved/Advanced Clinical 任一为真 |
| 癌症驱动 | OT isCancerDriverGene 为真 |
| 安全警示 | 存在 safetyLiabilities 记录或 IMPC 严重表型 |

## 7. 图表规范

- 25–30 张，A4 宽 16–17cm，300dpi，统一配色字体
- 图表标签英文；标题/图注/来源脚注中文
- 默认静态 PNG；PPI 网络保留一个交互插槽（HTML 内嵌 Plotly，PDF 用静态回退）
- `figures/theme.py` 统一主题，各维度图模块只接收结构化结果

## 8. LLM 润色

- OpenAI 兼容接口，可插拔；`--no-llm` 跳过
- 输入 facts JSON + 模板草稿 + 写作规范，只允许改写措辞
- `guard.py`：输出数字必须命中 facts 白名单，基因符号不得替换；失败重试一次，仍失败回退模板
- 按（基因, facts 哈希, 模型, prompt 版本）缓存
- 报告脚注记录是否使用 LLM、模型与版本

## 9. 报告结构

1. 执行摘要（事实标签卡：靶点类别、可成药性分级、Top 疾病、安全警示、驱动状态）
2. 基因与蛋白基础
3. 疾病关联与遗传证据
4. 表达
5. 突变与变异
6. 依赖性与癌症特征
7. 通路与相互作用
8. 蛋白修饰
9. 可成药性与药物
10. 安全性与风险
11. 比较基因组学
12. 药物基因组学/文献（Tier3，v1 显示"暂未包含"占位）
- 附录：数据源版本/下载日期/校验和/许可、缺失维度清单、LLM 使用情况、方法学局限

## 10. CLI 设计

统一入口 `target-profile`（Python 包名 `target-profile`，源码 `src/target_profile/`）：

```
target-profile run GENE [--out DIR] [--format html|pdf|both] [--no-llm] [--force]
target-profile data [all|<source>] [--force]     # 下载+聚合，写 manifest
target-profile doctor                            # 检查环境、数据完整性、校验和
target-profile version
```

- `GENE` 自动识别 symbol / 别名 / Ensembl / UniProt，报告统一 HGNC 符号
- `run` 除可选 LLM 润色外全程离线（`--no-llm` 时完全离线）；默认产物 `out/<SYMBOL>_<YYYYMMDD>/`：
  - `report.html`（自包含，图片 base64 内嵌）
  - `report.pdf`
  - `facts.json`（所有结构化事实 + 来源）
  - `run.log`
- `--force` 覆盖已存在产物目录

## 11. 错误处理（分层严格）

| 情况 | 行为 | 退出码 |
|---|---|---|
| 基因无法解析 | 报错 + 相近符号提示 | 2 |
| 数据文件缺失/校验和不符 | 报错 + 提示 `target-profile data <source>` | 3 |
| 单维度确实无数据 | 渲染"暂无可用数据"，附录记缺失 | 0 |
| 单维度计算异常 | 该维度降级 + 警告，继续，写入 run.log 与附录 | 0 |
| PDF 渲染失败 | 保留 HTML，报错 | 4 |
| LLM 失败 | 回退模板，脚注标注未使用 LLM | 0 |

## 12. 测试策略

- **单元测试**：fixture parquet（手工 3–5 行）；覆盖分位数/τ/效应量、HGVSp 解析、别名解析、guard 数字白名单
- **集成测试**：fake 数据目录 + 2–3 个基因跑完整链路；断言章节、facts、图存在；monkeypatch socket 验证零联网
- **LLM**：fake client 测 guard 与回退路径
- **快照**：只对 `facts.json` 关键字段做快照，不做 HTML 全文/视觉回归
- 数据层下载逻辑用 dry-run/小样本测试，CI 不联网

## 13. 目录结构

```
target_profiling/
├── pyproject.toml            # uv 管理：duckdb, pandas, pyarrow, matplotlib,
│                             #   jinja2, playwright, typer, pydantic, pyyaml, httpx
├── config/
│   ├── settings.toml         # 数据根路径、LLM 配置、事实标签阈值
│   └── licenses.yaml         # 许可登记表
├── src/target_profile/
│   ├── cli.py  config.py  db.py  gene_resolve.py  context.py
│   ├── data_prep/
│   │   ├── registry.py  aggregate.py  manifest.py
│   │   └── sources/  gtex tcga depmap hpa uniprot reactome_go
│   │                 string_ppi opentargets clinvar gnomad impc
│   ├── analysis/    expression mutation dependency pathway ptm
│   │               disease tractability safety cancer comparative
│   │               basic summary
│   ├── figures/     theme.py + 各维度图模块
│   ├── report/      render.py  templates/report.html.j2  print.css  pdf.py
│   └── llm/         client.py  prompts.py  guard.py  cache.py
├── data/                     # 运行时数据根：parquet/ + manifest.json
├── out/
└── tests/  fixtures/ fakes/ unit/ integration/
```

模块边界：`data_prep` 只写 parquet/manifest；`analysis` 只读 parquet、输出结构化结果；`figures` 只读分析结果；`report` 只读分析结果与图；`llm` 只接收 facts 与草稿。各层不反向依赖。

## 14. 里程碑与验收

垂直切片优先：先用 2–3 个代表性基因（KRAS、TP53、一个罕见病基因）打通全链路，再补齐模块。

| 里程碑 | 内容 | 验收标准 |
|---|---|---|
| M0 | 仓库骨架：pyproject、包布局、CLI 骨架、config、manifest schema、测试脚手架 | `target-profile --help/version/doctor` 可运行；pytest 空套件通过 |
| M1 | 垂直切片数据：GTEx 表达 + TCGA 突变 + DepMap 依赖 → parquet + manifest | `target-profile data gtex tcga depmap` 产出带版本/校验和的 parquet；doctor 通过；常驻数据实测 |
| M2 | 垂直切片全链路：三模块分析 → 图表 → 自包含 HTML → PDF | `target-profile run KRAS --no-llm` 产出 out 目录四件套；KRAS/TP53 人工验收；零联网测试通过 |
| M3 | 补齐基础报告：通路/网络、PTM、基因蛋白基础 | 章节 2/4/5/6/7/8 渲染完整 |
| M4 | Tier1 维度：疾病关联、可成药性、安全性 | 章节 3/9/10 渲染；KRAS 安全性"无记录 ≠ 安全"正确呈现 |
| M5 | Tier2 + 收尾：癌症特征、比较基因组、执行摘要标签卡、LLM 润色、12 章结构完整、批量接口预留 | 12 章结构齐全（第 12 章为 Tier3 占位说明）；`--no-llm`/`--format`/LLM 回退验证；全测试绿；README 与环境说明 |

## 15. 运行环境与依赖

- Python 3.13（uv 管理）；项目使用 `uv venv` 独立环境
- 运行时依赖：duckdb、pandas、pyarrow、matplotlib、jinja2、playwright、typer、pydantic、pyyaml、httpx
- Playwright 需 Chromium；`doctor` 检查并给出安装指引；PDF 失败时保留 HTML
- 机器约束：2 核 / 7GB 内存 / 磁盘 ≥ 13GB（下载峰值 ≤ 10GB）

## 16. 风险与缓解

| 风险 | 缓解 |
|---|---|
| OT 数据体积超限（下载峰值 8–10GB） | 子集化/流式处理；M1 实测；超限则 OT 互作不落地，仅用 STRING |
| TCGA MC3 源文件不稳 | 固定带校验和的镜像文件，manifest 记录 |
| Chromium 不可用 | HTML 始终产出；doctor 预检；PDF 失败退出码 4 |
| LLM guard 误杀 | 重试一次后回退模板，脚注标注 |
| 安全性维度稀疏被误读 | 显式"无记录 ≠ 安全"声明 |
| 许可变化 | licenses.yaml 版本化管理，报告附录展示 |
