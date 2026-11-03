# 靶点画像 — Tier3-3a 扩展证据（PGx / GWAS / 文献）设计文档

- 日期：2026-10-30
- 状态：草案（待用户审阅）
- 关联：`docs/superpowers/specs/2026-10-30-target-profiling-design.md`（主 spec）、`2026-10-30-target-profiling-ui-redesign-design.md`（12 章信息架构）
- 项目约束：**不使用 git**（不做 commit/分支/PR；本文与后续计划均不含 git 步骤）

## 1. 背景与目标

v1（M0–M5）已完成，报告固定 12 章，第 12 章「药物基因组学/文献」为静态占位。Tier3 原规划 5 个维度：PGx、文献、GWAS credible sets、单细胞表达、AlphaFold 3D 结构。经用户确认：

- 本批（**3a**）只做 **Open Targets 可覆盖** 的三个维度：PGx、GWAS credible sets、文献
- 单细胞表达与 3D 结构留待 **3b**，另行设计

目标：

- 第 12 章从占位变为可交付的「扩展证据」，含三个小节
- 全部走 OT Platform API + Europe PMC REST API，**零新增本地大表**
- 维持自包含单文件 HTML、运行时零联网、`--offline` 可重现
- 商用合规：Europe PMC 只存书目元数据，不存摘要正文

## 2. 关键决策

1. **范围**：仅 PGx / GWAS / 文献；单细胞与 3D 结构不在本批。
2. **架构**：3 个独立分析模块（`pgx`、`gwas`、`literature`），各自返回 `ModuleResult`，独立降级。
3. **报告位置**：扩充第 12 章为「扩展证据」，不新增章节；报告仍为 12 章，锚点仍为 `ch-12`。
4. **文献口径**：OT 提供总量/最早年份；Europe PMC 按「标题命中基因符号」+ 被引降序取 Top 20，只存元数据。
5. **GWAS 呈现**：汇总统计 + 按 p 值排序 Top 10 表 + 1 张条形图。
6. **PGx 呈现**：按药物分组表 + 类别分布图。
7. **执行摘要不变**：`summary` 模块不纳入新维度，保持卡片稳定。
8. **LLM 版本**：`PROMPT_VERSION` 由 `v1` 升为 `v2`，避免旧缓存被错误复用。

## 3. 范围

### 包含

- `api/opentargets.py` 新增 PGx 与 credible sets 查询函数
- 新增 `api/europepmc.py`
- 新增 `analysis/pgx.py`、`analysis/gwas.py`、`analysis/literature.py`
- `figures/chart_specs.py` 新增 2 个 builder
- 第 12 章渲染、`SECTION_TITLES` / `FACT_LABELS` 扩展
- LLM 模板 3 个分支、`PROMPT_VERSION` 升级
- `fetch GENE` 预热新缓存
- 单测 + 集成测试 + 真实数据验收

### 非目标

- 不做单细胞表达（3b）
- 不做 AlphaFold 3D 结构渲染（3b）
- 不改动其他 11 章内容与图表
- 不新增本地 Parquet 派生表
- 不引入前端框架、不做交互筛选控件
- 不抓取文献全文或摘要
- 不做 git 操作

## 4. 数据源与许可

| 维度 | 来源 | 许可/合规要点 |
|---|---|---|
| PGx | Open Targets Platform（`target.pharmacogenomics`，上游 ClinPGx） | 平台数据 CC0；上游数据源逐项标注，报告附录保留 OT 署名与检索日期 |
| GWAS credible sets | Open Targets Platform（`target.credibleSets`，上游 GWAS Catalog / eQTL Catalogue / GTEx 等） | 同上；图表注明「L2G/credible set 推断」 |
| 文献 | Open Targets（计数/最早年份）+ Europe PMC REST | 只存书目元数据（标题/期刊/年份/首作者/被引/PMID/DOI）；**不存摘要**；报告标注来源与访问日期 |

缓存优先：所有请求经 `CachedFetcher`；`--offline` 只读缓存，缺失即降级。

## 5. 数据层

### 5.1 OT 药物基因组学

`api/opentargets.py` 新增常量 `PGX_QUERY` 与函数：

```python
def target_pharmacogenomics(ensembl_id, fetcher, refresh=False):
    return _target_query(ensembl_id, PGX_QUERY, "opentargets_pharmacogenomics", fetcher, refresh)
```

GraphQL（已在 KRAS 实测，11 条记录）：

```graphql
query($ensemblId: String!) {
  target(ensemblId: $ensemblId) {
    approvedSymbol
    pharmacogenomics {
      evidenceLevel
      pgxCategory
      phenotypeText
      genotype
      variantRsId
      datasourceId
      literature
      isDirectTarget
      drugs { drugFromSource drugId drug { id name } }
      variantFunctionalConsequence { id label }
    }
  }
}
```

- 返回 `data.target.pharmacogenomics`（list，可能为空）
- 缓存键：`<ENSG>/opentargets_pharmacogenomics.json`
- `pharmacogenomics` 在 schema 中为 NON_NULL list，空列表属正常无数据

### 5.2 OT GWAS credible sets

`api/opentargets.py` 新增 `CREDIBLE_SETS_QUERY` 与函数：

```python
def target_credible_sets(ensembl_id, fetcher, refresh=False):
    return _target_query(ensembl_id, CREDIBLE_SETS_QUERY, "opentargets_credible_sets", fetcher, refresh)
```

分页上限固定在查询串内（`size: 200`），不暴露参数，避免缓存键与查询不一致。

GraphQL（已在 KRAS 实测，`count=71`）：

```graphql
query($ensemblId: String!) {
  target(ensemblId: $ensemblId) {
    credibleSets(page: {index: 0, size: 200}) {
      count
      rows {
        studyId
        studyType
        variant { id rsIds chromosome position }
        chromosome
        position
        pValueMantissa
        pValueExponent
        beta
        zScore
        confidence
        finemappingMethod
        l2GPredictions { rows { score target { approvedSymbol } } }
        colocalisation { rows { h4 colocalisationMethod } }
        study { studyType traitFromSource }
      }
    }
  }
}
```

要点：

- `l2GPredictions` 与 `colocalisation` 是**分页包装类型**，必须写 `{ rows { ... } }`；直接写 `score` / `h4` 会报 schema 错误
- `count` 为真实总数；`rows` 最多 200 条（首屏）；当 `count > len(rows)` 时 facts 记录 `truncated=True` 并在 caveat 说明
- `-log10(p) = -(pValueExponent + log10(pValueMantissa))`；`pValueMantissa <= 0` 或任一字段缺失的行跳过并计数
- 缓存键：`<ENSG>/opentargets_credible_sets.json`

### 5.3 Europe PMC 高被引文献

新增 `api/europepmc.py`：

```python
def top_cited(symbol, fetcher, refresh=False, limit=20):
    ...
```

请求（已验证 `TITLE:"KRAS" AND SRC:MED` 命中 8,190，按被引排序结果相关）：

- URL：`https://www.ebi.ac.uk/europepmc/webservices/rest/search`
- 参数：`query=f'TITLE:"{symbol}" AND SRC:MED'`、`format=json`、`pageSize=limit`、`sort="CITED desc"`、`resultType=core`
- 符号先做白名单清洗（仅 `[A-Za-z0-9._-]`），不可能含引号
- 缓存键：`<SYMBOL>/europepmc_top_cited.json`（保存原始响应，便于追溯）

归一化后返回：

```python
{
  "hit_count": int,          # response["hitCount"]
  "rows": [
    {
      "pmid": str,
      "title": str,
      "journal": str,        # journalInfo.journal.title，缺省 ""
      "year": int | None,    # pubYear
      "first_author": str,   # authorString 首个逗号前；多于一人追加 " et al."
      "cited_by": int,       # citedByCount，缺省 0
      "doi": str,            # 缺省 ""
    }
  ]
}
```

- 跳过缺 `pmid` 或 `title` 的记录
- 网络/JSON 异常向上抛，由模块降级处理

## 6. 分析模块契约

所有模块签名为 `analyze_xxx(ctx, settings, offline=True, fetcher=None)`（与现有模块一致），内部自行构造 `CachedFetcher`（若未传入）。`facts` 是叙事与 LLM 数字校验的唯一来源。

### 6.1 `analysis/pgx.py`

facts：

| key | 含义 |
|---|---|
| `n_records` | PGx 记录数 |
| `n_drugs` | 去重药物数 |
| `n_direct_target` | `isDirectTarget=True` 记录数 |
| `pgx_categories` | 类别计数，字符串 `"efficacy: 8; toxicity: 3"` |
| `evidence_levels` | 等级计数，字符串 `"3: 8; 1: 3"` |
| `top_category` | 记录最多的类别（tie 按字母序） |

> facts 只放标量/字符串（与现有模块一致，便于事实卡与 LLM 数字守卫）；分布原始结构保留在模块内部供图表使用。

表格 `tables["pgx_drugs"]`（pandas DataFrame，按药物合并）：

| 列 | 说明 |
|---|---|
| Drug | `drug.name` 优先，否则 `drugFromSource` |
| rsID | 去重 rsID，逗号连接 |
| Genotype | 去重基因型，逗号连接 |
| Phenotype | 去重 `phenotypeText`，`; ` 连接 |
| Category | 去重 `pgxCategory` |
| Evidence | 去重 `evidenceLevel` |
| N PMIDs | 去重 PMID 数（整数，非列表） |

排序：记录数降序、药物名升序。无药物字段的记录归入 `(unspecified)`。

图表 `pgx-categories`：按 `pgx_categories` 的条形图，英文标签，纯 JSON。

caveats：

- `PGx 记录为 Open Targets 对 ClinPGx 的汇总，证据等级含义以源数据库为准`
- `仅供研究参考，不构成用药或临床决策依据`

无记录 → `ModuleResult(name="pgx").degrade("pgx: no Open Targets pharmacogenomics records")`。

### 6.2 `analysis/gwas.py`

facts：

| key | 含义 |
|---|---|
| `n_credible_sets` | OT `count` |
| `n_rows` | 本地实际拿到的原始条数 |
| `truncated` | `count > n_rows` |
| `study_types` | 研究类型计数，字符串 `"eqtl: 60; gwas: 11"` |
| `min_p` | 最小 p 值（float） |
| `min_p_log10` | 对应 `-log10(p)`（保留 2 位） |
| `top_variant` | 最强信号的 `rsIds[0]` 优先，否则 `variant.id` |
| `top_locus` | 字符串 `"chr:pos (studyType, -log10p=15.31)"` |
| `n_colocalised` | 任一 colocalisation 的 `h4 >= 0.8` 的 credible set 数 |

> facts 只放标量/字符串；Top 10 明细只进表格与图表。

表格 `tables["gwas_top_loci"]`（Top 10，按 `-log10(p)` 降序、p 升序、研究 ID 升序稳定排序）：

| 列 | 说明 |
|---|---|
| Variant | `rsIds[0]` 优先，否则 `variant.id` |
| Locus | `chromosome:position` |
| Study type | `studyType` |
| Trait | `study.traitFromSource`（eQTL 常为 Ensembl 样式，原样展示） |
| -log10(p) | 保留 2 位小数 |
| Beta | `beta`（可空） |
| Max H4 | colocalisation 行中 `h4` 最大值（无则空） |
| Study | `studyId` |

图表 `gwas-loci`：Top 10 的 `-log10(p)` 条形图；x 轴为 Variant，按 `studyType` 着色；英文标签。

caveats：

- `GWAS 关联来自 credible set 与 L2G 推断，不表示因果关系`
- `eQTL/pQTL 研究与疾病 GWAS 研究混合统计`
- 若 `truncated`：`仅展示前 200 条 credible sets（共 {count} 条）`

无记录 → `degrade("gwas: no Open Targets credible sets")`。

### 6.3 `analysis/literature.py`

facts：

| key | 含义 |
|---|---|
| `ot_total` | OT `literatureOcurrences.count`（若可获得） |
| `ot_earliest_year` | OT `earliestPubYear` |
| `europepmc_hits` | Europe PMC 标题命中总数 |
| `n_top_cited` | 实际保留条数 |
| `top_pmid` | 被引最高文献 PMID |
| `top_cited_count` | 被引最高文献被引数 |

OT 文献计数：`api/opentargets.py` 新增 `LITERATURE_COUNT_QUERY` 与 `target_literature(ensembl_id, fetcher, refresh=False)`，缓存键 `<ENSG>/opentargets_literature.json`：

```graphql
query($ensemblId: String!) {
  target(ensemblId: $ensemblId) {
    literatureOcurrences {
      count
      earliestPubYear
    }
  }
}
```

> 注：字段名 `literatureOcurrences` 为 OT 官方拼写（缺 `c`），不得改写。

表格 `tables["literature_top_cited"]`（≤20 行，按被引降序）：

| 列 | 说明 |
|---|---|
| Title | 标题 |
| Journal | 期刊 |
| Year | 年份 |
| First author | 首作者（多作者附 et al.） |
| Cited by | 被引数 |
| PMID | `pmid`（纯文本，不生成外链，保持自包含/零外链约束） |
| DOI | `doi`（纯文本） |

不生成图表。

caveats：

- `文献按标题命中基因符号挑选并按被引排序，不代表临床重要性或证据等级`
- `仅展示 Europe PMC 书目元数据，不含摘要正文`
- OT 计数失败但 Europe PMC 成功时，保留 Europe PMC 结果并标注 `OT 文献统计不可用`

降级规则：

- OT 与 Europe PMC **都**失败/为空 → `degrade("literature: no literature data")`
- 仅一方成功 → 保留成功部分，`status="ok"`，facts 中缺失键省略，附 caveat

## 7. 报告与渲染

`report/render.py`：

- `CHAPTERS` 第 12 项改为 `(12, "扩展证据", ["pgx", "gwas", "literature"], "default")`
- `SECTION_TITLES` 增加：
  - `"pgx": "药物基因组学（PGx）"`
  - `"gwas": "GWAS 与共定位证据"`
  - `"literature": "高被引文献"`
- 模板已支持同一章多 block：`section.blocks | length > 1` 时自动渲染 `<h3>` 小节标题，无需改模板
- `FACT_LABELS` 增加三个模块 facts 的中文标签：

| key | 标签 |
|---|---|
| `n_records` | PGx 记录数 |
| `n_drugs` | 涉及药物数 |
| `n_direct_target` | 直接靶点记录数 |
| `pgx_categories` | PGx 类别分布 |
| `evidence_levels` | 证据等级分布 |
| `top_category` | 主要 PGx 类别 |
| `n_credible_sets` | credible set 总数 |
| `n_rows` | 已获取条数 |
| `truncated` | 是否截断 |
| `study_types` | 研究类型分布 |
| `min_p` | 最小 p 值 |
| `min_p_log10` | 最强信号 -log10(p) |
| `top_variant` | 最强信号变异 |
| `top_locus` | 最强信号位点 |
| `n_colocalised` | 共定位证据数 |
| `ot_total` | OT 文献总数 |
| `ot_earliest_year` | OT 最早文献年份 |
| `europepmc_hits` | Europe PMC 命中数 |
| `n_top_cited` | 高被引文献数 |
| `top_pmid` | 最高被引 PMID |
| `top_cited_count` | 最高被引次数 |

未登记键保持原样显示。

- 空状态：三个模块均注册且有返回，章级 `missing=False`；全部 `no_data` 时显示三个空状态小节；仅当模块未注册时章级 `missing` 才为真（正常流程不会发生）

图表 id 仍全局唯一：`pgx-categories`、`gwas-loci`。自包含约束不变（无外链、图表数据进 `<script id="chart-data">`）。

## 8. LLM 叙事

`llm/prompts.py`：

- `PROMPT_VERSION = "v2"`
- `template_narrative` 增加 `pgx` / `gwas` / `literature` 分支，中文模板，所有数字来自 facts
- `build_user_prompt` 沿用现有结构（gene + facts JSON）
- 数字校验、重试一次、失败回退模板的既有逻辑不变
- 缓存键包含 `prompt_version`，升版后旧缓存自然失效

## 9. CLI 与 `fetch`

`cli.py`：

- 导入并注册 3 个分析函数；执行顺序：9 个基础模块 → `cancer`、`comparative`（带 `prior`）→ `pgx`、`gwas`、`literature` → `summary`
- `BUILDERS` 增加 `"pgx": build_pgx`、`"gwas": build_gwas`（`literature` 无图）
- `fetch GENE` 增加步骤：
  - `Open Targets pharmacogenomics`
  - `Open Targets credible sets`
  - `Open Targets literature count`
  - `Europe PMC top cited`
- 单步失败仅 warning，不中断（沿用现有循环）
- `--offline` 下 `run` 只读缓存；缺任一缓存 → 对应模块降级，不 exit

## 10. 错误处理与降级

| 情形 | 行为 |
|---|---|
| PGx 缓存缺失且 offline | `no_data` + caveat |
| PGx 记录为空 | `no_data` |
| credible sets 为空 | `no_data` |
| credible sets > 200 | 展示前 200，`truncated=True` + caveat |
| Europe PMC 网络失败 | literature 保留 OT 统计，`ok` + caveat |
| OT 文献计数失败 | literature 保留 Europe PMC 列表，`ok` + caveat |
| 两者皆失败 | `no_data` |
| 单模块内部异常 | CLI 捕获 → 该模块 `no_data`，其他章节不受影响 |
| 图表构建失败 | 记录 warning，模块保留表格/叙事 |

不新增退出码；顶层 `DataMissing` / `GeneNotFound` 语义不变。

## 11. 测试策略（TDD）

全部离线，沿用现有 fixture 方式（tmp_path 写 JSON + monkeypatch `socket.socket.connect`）。

新增/修改：

- `tests/test_opentargets.py`：PGx / credible sets / 文献计数的查询与缓存键
- `tests/test_europepmc.py`：查询参数、归一化、首作者截断、缺字段跳过、异常抛出
- `tests/unit/test_pgx.py`：分组、facts、caveat、空数据降级
- `tests/unit/test_gwas.py`：-log10(p) 计算、Top10 排序、truncated、colocalisation 计数、空数据
- `tests/unit/test_literature.py`：OT+EPMC 合并、单方失败、双失败
- `tests/unit/test_chart_specs.py`（或现有图表测试文件）：`build_pgx`、`build_gwas` 的 option 可 JSON 序列化
- `tests/unit/test_llm_pipeline.py`：新模板分支、`PROMPT_VERSION` 变化
- `tests/test_cli_run.py`：模块集合扩为 15（12 + 3）
- `tests/integration/test_vertical_slice.py`：fixture 增加
  - `<ENSG>/opentargets_pharmacogenomics.json`
  - `<ENSG>/opentargets_credible_sets.json`
  - `<ENSG>/opentargets_literature.json`
  - `<SYMBOL>/europepmc_top_cited.json`
  - 断言 `facts["modules"]` 含 `pgx`/`gwas`/`literature` 且 `status == "ok"`
  - 断言 HTML 含 `id="ch-12"`、三个小节标题、`pgx-categories`、`gwas-loci`
  - 沿用外链/自包含断言

预期测试总数：86 → 约 105（以实际为准，全绿为验收）。

## 12. 验收标准

1. `uv run pytest -q` 全绿。
2. 真实数据（需先 `fetch KRAS` / `fetch TP53` 预热）`--offline --no-llm` 生成成功：
   - 第 12 章含三个小节与 2 张图
   - `facts.json` 的 `modules` 含 `pgx`、`gwas`、`literature`
   - HTML 无外部 `src`/`href`，字体与 ECharts 内联
3. KRAS 手工核对（预期量级，以实际缓存为准）：
   - PGx：11 条记录左右，含 panitumumab/cetuximab
   - GWAS：`n_credible_sets=71`，`study_types` 以 `eqtl` 为主
   - 文献：EPMC 命中约 8,190，Top 20 有标题/期刊/年份/被引
4. `fetch GENE` 能写入 4 类新缓存；断网后 `--offline` 可复现。
5. 无 git 操作。

## 13. 后续（3b，不在本 spec）

- 单细胞表达（数据源选型、体积约束、谱系/细胞类型聚合）
- AlphaFold 3D 结构渲染（PDB 下载、自包含体积预算、降级策略）
- 两者各自独立 spec → plan → 实施
