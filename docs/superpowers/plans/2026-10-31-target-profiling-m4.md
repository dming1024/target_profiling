# Target Profiling M4（Tier1 维度：疾病 / 可成药性 / 安全性）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 M3 的 6 模块基础上补齐 Tier1 三个维度（disease / tractability / safety），使报告第 3/9/10 章完整，并落实"无安全记录 ≠ 安全"的呈现。

**Architecture:** 新增 4 个 Open Targets GraphQL 查询（disease/constraint、tractability/probes/drugs、safety/mouse/homologues）与 1 个 ClinVar eutils 适配器，全部经 `CachedFetcher` 按基因缓存；新增 3 个 analysis 模块与 3 组双联图；CLI 扩展到 9 模块并预热新缓存。

**Tech Stack:** Python 3.13、uv、pandas、matplotlib、Jinja2、Typer、httpx、pytest。

**约束：** 用户要求暂不使用 git，本计划不含 commit 步骤。项目根 `/root/target_profiling`，命令一律用 `uv run`。

**已验证的外部接口（2026-10-30 实测）：**
- OT `target(ensemblId:)` 字段（introspection 确认）：`associatedDiseases(page:{index,size}){count rows{disease{id name} score datatypeScores{id score}}}`、`geneticConstraint{constraintType score oe oeLower oeUpper upperRank}`、`tractability{modality label value}`、`chemicalProbes{id drugId mechanismOfAction isHighQuality}`、`drugAndClinicalCandidates{count rows{id maxClinicalStage drug{id name} diseases{disease{id name}}}}`、`safetyLiabilities{event eventId datasource effects{direction dosing} studies{name type}}`、`mousePhenotypes{modelPhenotypeLabel modelPhenotypeClasses{id label}}`、`isEssential`、`homologues{speciesName homologyType targetGeneId queryPercentageIdentity targetPercentageIdentity}`
- 实测值：KRAS 疾病 2262（top Noonan syndrome 0.834）、pLI 0.9998、LOEUF 0.2264、isEssential true、SM Approved Drug true、探针 7、药物 3（SOTORASIB 已批准）、safetyLiabilities 0、小鼠表型 91（class top: cardiovascular 22）；TP53 疾病 5198（top Li-Fraumeni 0.876）、LOEUF 0.4184、isEssential false、探针 0、药物 9、safetyLiabilities 4、小鼠表型 250
- ClinVar eutils：`esearch.fcgi?db=clinvar&term=SYMBOL[gene]&retmode=json`（KRAS 628 / TP53 4059）；致病过滤 `SYMBOL[gene] AND ("pathogenic"[germline_classification] OR "likely pathogenic"[germline_classification])`（KRAS 216 / TP53 1767）；`esummary.fcgi` 的 `germline_classification.description/review_status` 为聚合分类，抽样中可能为 VUS/冲突 → 报告需措辞谨慎
- `drugAndClinicalCandidates.rows[].diseases[].disease` 可能为 `null`；`safetyLiabilities.studies[].name` 可能为 `null`
- 临床阶段枚举实测：`APPROVAL`、`PHASE_3`、`PHASE_2`；模态：`SM`/`AB`/`PR`/`OC`

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `src/target_profile/api/opentargets.py`（改） | 新增 `target_disease()`、`target_tractability()`、`target_safety()` |
| `src/target_profile/api/clinvar.py`（新） | `fetch_clinvar()`：总数 / 含致病提交数 / Top 记录 |
| `src/target_profile/analysis/disease.py`（新） | OT 疾病关联 + 遗传约束 + ClinVar |
| `src/target_profile/analysis/tractability.py`（新） | 可成药性分级 + 探针 + 药物/临床阶段 |
| `src/target_profile/analysis/safety.py`（新） | 安全事件 + 小鼠表型 + 约束 + 表达广度 + 旁系同源 |
| `src/target_profile/figures/charts.py`（改） | 新增 `plot_disease()`、`plot_tractability()`、`plot_safety()` |
| `src/target_profile/report/render.py`（改） | 新增章节标题与 fact 标签 |
| `src/target_profile/report/templates/report.html.j2`（改） | 页脚数据来源更新 |
| `src/target_profile/cli.py`（改） | 9 个模块接线；`fetch` 预热新缓存 |
| `src/target_profile/config.py` + `config/settings.toml`（改） | 新增 `expression_breadth_tpm = 1.0` |
| `tests/test_opentargets.py`、`tests/test_clinvar.py`（新/改） | 适配器层 |
| `tests/test_disease.py`、`tests/test_tractability.py`、`tests/test_safety.py`（新） | 分析模块 |
| `tests/test_figures.py`、`tests/test_render.py`、`tests/test_cli_run.py`、`tests/integration/test_vertical_slice.py`（改） | 图表/报告/CLI/集成 |

缓存布局（沿用 M2/M3）：OT 查询按 Ensembl 存 `data/cache/<ENSG>/opentargets_<name>.json`；ClinVar 按符号存 `data/cache/<SYMBOL>/clinvar_*.json`。

---

### Task 1: OT 疾病 / 可成药性 / 安全性查询 + 广度阈值

**Files:**
- Modify: `src/target_profile/api/opentargets.py`
- Modify: `src/target_profile/config.py`
- Modify: `config/settings.toml`
- Modify: `tests/test_opentargets.py`

- [x] **Step 1: 写失败测试（追加到 `tests/test_opentargets.py`）**

```python
from target_profile.api.opentargets import target_disease, target_safety, target_tractability


def test_target_disease_reads_cache(tmp_path):
    cache = tmp_path / "ENSG00000133703"
    cache.mkdir(parents=True)
    (cache / "opentargets_disease.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "associatedDiseases": {
                            "count": 2,
                            "rows": [
                                {"disease": {"id": "MONDO_0018997", "name": "Noonan syndrome"}, "score": 0.83, "datatypeScores": [{"id": "genetic_association", "score": 0.9}]}
                            ],
                        },
                        "geneticConstraint": [{"constraintType": "lof", "score": 0.99, "oe": 0.05, "oeUpper": 0.22}],
                    }
                }
            }
        )
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    details = target_disease("ENSG00000133703", fetcher)
    assert details["associatedDiseases"]["count"] == 2
    assert details["geneticConstraint"][0]["constraintType"] == "lof"


def test_target_tractability_reads_cache(tmp_path):
    cache = tmp_path / "ENSG00000133703"
    cache.mkdir(parents=True)
    (cache / "opentargets_tractability.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "tractability": [{"modality": "SM", "label": "Approved Drug", "value": True}],
                        "chemicalProbes": [{"id": "ARS-1620", "drugId": "CHEMBL4214264", "mechanismOfAction": ["inhibitor"], "isHighQuality": False}],
                        "drugAndClinicalCandidates": {"count": 1, "rows": []},
                    }
                }
            }
        )
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    details = target_tractability("ENSG00000133703", fetcher)
    assert details["tractability"][0]["modality"] == "SM"
    assert details["chemicalProbes"][0]["id"] == "ARS-1620"


def test_target_safety_reads_cache(tmp_path):
    cache = tmp_path / "ENSG00000133703"
    cache.mkdir(parents=True)
    (cache / "opentargets_safety.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "safetyLiabilities": [],
                        "mousePhenotypes": [{"modelPhenotypeLabel": "small liver", "modelPhenotypeClasses": [{"id": "MP:0005370", "label": "liver/biliary system phenotype"}]}],
                        "geneticConstraint": [{"constraintType": "lof", "score": 0.99, "oeUpper": 0.22}],
                        "isEssential": True,
                        "homologues": [],
                    }
                }
            }
        )
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    details = target_safety("ENSG00000133703", fetcher)
    assert details["isEssential"] is True
    assert details["mousePhenotypes"][0]["modelPhenotypeLabel"] == "small liver"
```

- [x] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_opentargets.py -v`
Expected: FAIL（`target_disease` / `target_tractability` / `target_safety` 不存在）

- [x] **Step 3: 扩展 OT 适配器与配置**

在 `src/target_profile/api/opentargets.py` 末尾追加：

```python
DISEASE_QUERY = """
query Disease($id: String!) {
  target(ensemblId: $id) {
    id
    associatedDiseases(page: {index: 0, size: 20}) {
      count
      rows { disease { id name } score datatypeScores { id score } }
    }
    geneticConstraint { constraintType score oe oeLower oeUpper upperRank }
  }
}
"""

TRACTABILITY_QUERY = """
query Tractability($id: String!) {
  target(ensemblId: $id) {
    id
    tractability { modality label value }
    chemicalProbes { id drugId mechanismOfAction isHighQuality }
    drugAndClinicalCandidates {
      count
      rows { id maxClinicalStage drug { id name } diseases { disease { id name } } }
    }
  }
}
"""

SAFETY_QUERY = """
query Safety($id: String!) {
  target(ensemblId: $id) {
    id
    safetyLiabilities { event eventId datasource effects { direction dosing } studies { name type } }
    mousePhenotypes { modelPhenotypeLabel modelPhenotypeClasses { id label } }
    geneticConstraint { constraintType score oeUpper }
    isEssential
    homologues { speciesName homologyType targetGeneId queryPercentageIdentity targetPercentageIdentity }
  }
}
"""


def target_disease(
    ensembl_id: str, fetcher: CachedFetcher, refresh: bool = False
) -> dict[str, Any] | None:
    return _target_query(ensembl_id, DISEASE_QUERY, "opentargets_disease", fetcher, refresh)


def target_tractability(
    ensembl_id: str, fetcher: CachedFetcher, refresh: bool = False
) -> dict[str, Any] | None:
    return _target_query(
        ensembl_id, TRACTABILITY_QUERY, "opentargets_tractability", fetcher, refresh
    )


def target_safety(
    ensembl_id: str, fetcher: CachedFetcher, refresh: bool = False
) -> dict[str, Any] | None:
    return _target_query(ensembl_id, SAFETY_QUERY, "opentargets_safety", fetcher, refresh)
```

`src/target_profile/config.py` 的 `Thresholds` 增加一行（放在 `string_min_score` 之后）：

```python
    expression_breadth_tpm: float = 1.0
```

`config/settings.toml` 的 `[thresholds]` 下增加：

```toml
expression_breadth_tpm = 1.0
```

- [x] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_opentargets.py -v`
Expected: 5 passed

---

### Task 2: ClinVar 适配器

**Files:**
- Create: `src/target_profile/api/clinvar.py`
- Create: `tests/test_clinvar.py`

- [x] **Step 1: 写失败测试**

```python
# tests/test_clinvar.py
import json

from target_profile.api.cache import CachedFetcher
from target_profile.api.clinvar import fetch_clinvar


def test_fetch_clinvar_reads_cache(tmp_path):
    gene_dir = tmp_path / "KRAS"
    gene_dir.mkdir(parents=True)
    (gene_dir / "clinvar_search.json").write_text(
        json.dumps({"esearchresult": {"count": "628", "idlist": []}})
    )
    (gene_dir / "clinvar_search_pathogenic.json").write_text(
        json.dumps({"esearchresult": {"count": "216", "idlist": ["1", "2"]}})
    )
    (gene_dir / "clinvar_summary_pathogenic.json").write_text(
        json.dumps(
            {
                "result": {
                    "uids": ["1", "2"],
                    "1": {
                        "title": "NM_004985.5(KRAS):c.34G>T (p.Gly12Cys)",
                        "germline_classification": {
                            "description": "Pathogenic",
                            "review_status": "reviewed by expert panel",
                        },
                    },
                    "2": {
                        "title": "NM_004985.5(KRAS):c.173C>T (p.Thr58Ile)",
                        "germline_classification": {
                            "description": "Uncertain significance",
                            "review_status": "criteria provided, single submitter",
                        },
                    },
                }
            }
        )
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    data = fetch_clinvar("KRAS", fetcher)
    assert data["total"] == 628
    assert data["pathogenic_submissions"] == 216
    assert data["records"][0]["classification"] == "Pathogenic"
    assert data["records"][1]["uid"] == "2"


def test_fetch_clinvar_without_pathogenic_ids_skips_summary(tmp_path):
    gene_dir = tmp_path / "ZZZ"
    gene_dir.mkdir(parents=True)
    (gene_dir / "clinvar_search.json").write_text(
        json.dumps({"esearchresult": {"count": "0"}})
    )
    (gene_dir / "clinvar_search_pathogenic.json").write_text(
        json.dumps({"esearchresult": {"count": "0", "idlist": []}})
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    data = fetch_clinvar("ZZZ", fetcher)
    assert data == {"total": 0, "pathogenic_submissions": 0, "records": []}
```

- [x] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_clinvar.py -v`
Expected: FAIL（模块不存在）

- [x] **Step 3: 实现 ClinVar 适配器**

```python
# src/target_profile/api/clinvar.py
from typing import Any

from target_profile.api.cache import CachedFetcher

CLINVAR_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PATHOGENIC_TERM = (
    '{symbol}[gene] AND ("pathogenic"[germline_classification] '
    'OR "likely pathogenic"[germline_classification])'
)


def _count(payload: dict) -> int:
    return int(payload.get("esearchresult", {}).get("count") or 0)


def fetch_clinvar(
    symbol: str,
    fetcher: CachedFetcher,
    retmax: int = 100,
    refresh: bool = False,
) -> dict[str, Any]:
    total_payload = fetcher.request_json(
        "clinvar_search",
        "GET",
        f"{CLINVAR_BASE}/esearch.fcgi",
        gene=symbol,
        params={
            "db": "clinvar",
            "term": f"{symbol}[gene]",
            "retmode": "json",
            "retmax": 0,
            "tool": "target_profile",
        },
        refresh=refresh,
    )
    pathogenic_payload = fetcher.request_json(
        "clinvar_search_pathogenic",
        "GET",
        f"{CLINVAR_BASE}/esearch.fcgi",
        gene=symbol,
        params={
            "db": "clinvar",
            "term": PATHOGENIC_TERM.format(symbol=symbol),
            "retmode": "json",
            "retmax": retmax,
            "tool": "target_profile",
        },
        refresh=refresh,
    )
    ids = [
        uid
        for uid in pathogenic_payload.get("esearchresult", {}).get("idlist", [])
        if uid
    ]
    records: list[dict[str, str]] = []
    if ids:
        summary = fetcher.request_json(
            "clinvar_summary_pathogenic",
            "GET",
            f"{CLINVAR_BASE}/esummary.fcgi",
            gene=symbol,
            params={
                "db": "clinvar",
                "id": ",".join(ids),
                "retmode": "json",
                "tool": "target_profile",
            },
            refresh=refresh,
        )
        result = summary.get("result", {})
        for uid in ids:
            record = result.get(uid) or {}
            classification = record.get("germline_classification") or {}
            records.append(
                {
                    "uid": uid,
                    "title": str(record.get("title") or ""),
                    "classification": str(classification.get("description") or ""),
                    "review_status": str(classification.get("review_status") or ""),
                }
            )
    return {
        "total": _count(total_payload),
        "pathogenic_submissions": _count(pathogenic_payload),
        "records": records,
    }
```

- [x] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_clinvar.py -v`
Expected: 2 passed

---

### Task 3: disease 分析模块

**Files:**
- Create: `src/target_profile/analysis/disease.py`
- Create: `tests/test_disease.py`

- [x] **Step 1: 写失败测试**

```python
# tests/test_disease.py
import json

from target_profile.analysis.disease import analyze_disease
from target_profile.config import Settings
from target_profile.models import GeneContext


def _settings(tmp_path):
    ensg = tmp_path / "data" / "cache" / "ENSG00000133703"
    ensg.mkdir(parents=True)
    (ensg / "opentargets_disease.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "associatedDiseases": {
                            "count": 2262,
                            "rows": [
                                {
                                    "disease": {"id": "MONDO_0018997", "name": "Noonan syndrome"},
                                    "score": 0.8336,
                                    "datatypeScores": [
                                        {"id": "genetic_association", "score": 0.86},
                                        {"id": "literature", "score": 0.19},
                                    ],
                                },
                                {
                                    "disease": {"id": "MONDO_0005233", "name": "non-small cell lung carcinoma"},
                                    "score": 0.8035,
                                    "datatypeScores": [
                                        {"id": "somatic_mutation", "score": 0.84},
                                        {"id": "genetic_association", "score": 0.40},
                                    ],
                                },
                            ],
                        },
                        "geneticConstraint": [
                            {"constraintType": "lof", "score": 0.9998, "oe": 0.0477, "oeUpper": 0.2264},
                            {"constraintType": "syn", "score": 0.3861, "oe": 0.924, "oeUpper": 0.95},
                        ],
                    }
                }
            }
        )
    )
    gene_dir = tmp_path / "data" / "cache" / "KRAS"
    gene_dir.mkdir(parents=True)
    (gene_dir / "clinvar_search.json").write_text(
        json.dumps({"esearchresult": {"count": "628"}})
    )
    (gene_dir / "clinvar_search_pathogenic.json").write_text(
        json.dumps({"esearchresult": {"count": "216", "idlist": ["1", "2"]}})
    )
    (gene_dir / "clinvar_summary_pathogenic.json").write_text(
        json.dumps(
            {
                "result": {
                    "uids": ["1", "2"],
                    "1": {
                        "title": "NM_004985.5(KRAS):c.34G>T (p.Gly12Cys)",
                        "germline_classification": {"description": "Pathogenic", "review_status": "reviewed by expert panel"},
                    },
                    "2": {
                        "title": "NM_004985.5(KRAS):c.173C>T (p.Thr58Ile)",
                        "germline_classification": {"description": "Uncertain significance", "review_status": "criteria provided, single submitter"},
                    },
                }
            }
        )
    )
    return Settings(lake_root=tmp_path / "lake", data_root=tmp_path / "data", out_root=tmp_path / "out")


def test_disease_facts(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703")
    result = analyze_disease(ctx, _settings(tmp_path), offline=True)
    assert result.status == "ok"
    assert result.facts["disease_count"] == 2262
    assert result.facts["top_disease"] == "Noonan syndrome"
    assert result.facts["top_disease_score"] == 0.834
    assert result.facts["pli"] == 0.9998
    assert result.facts["loeuf"] == 0.2264
    assert result.facts["constrained"] == "Yes"
    assert result.facts["clinvar_total"] == 628
    assert result.facts["clinvar_pathogenic_submissions"] == 216
    assert result.facts["clinvar_top_variant"].startswith("NM_004985.5(KRAS):c.34G")
    # 只有聚合分类为 Pathogenic 的记录进入表格
    assert len(result.tables["clinvar"]) == 1
    assert set(result.tables["datasources"]["datasource"]) == {
        "Genetic association",
        "Literature",
        "Somatic mutation",
    }
```

- [x] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_disease.py -v`
Expected: FAIL（模块不存在）

- [x] **Step 3: 实现 disease 分析**

```python
# src/target_profile/analysis/disease.py
from collections import Counter

import pandas as pd

from target_profile.api.cache import CachedFetcher
from target_profile.api.clinvar import fetch_clinvar
from target_profile.api.opentargets import target_disease
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult

CONSTRAINT_LABELS = {"lof": "LoF", "mis": "Missense", "syn": "Synonymous"}
DATASOURCE_LABELS = {
    "genetic_association": "Genetic association",
    "genetic_literature": "Genetic literature",
    "somatic_mutation": "Somatic mutation",
    "affected_pathway": "Affected pathway",
    "animal_model": "Animal model",
    "literature": "Literature",
    "clinical": "Clinical",
    "rna_expression": "RNA expression",
    "expression_atlas": "Expression atlas",
    "known_drug": "Known drug",
    "uniprot_variants": "UniProt variants",
    "europepmc": "Europe PMC",
    "phenotype": "Phenotype",
}


def _is_pathogenic(classification: str) -> bool:
    text = classification.lower()
    return (
        "pathogenic" in text
        and "conflict" not in text
        and "benign" not in text
    )


def analyze_disease(
    ctx: GeneContext,
    settings: Settings,
    offline: bool = True,
    fetcher: CachedFetcher | None = None,
) -> ModuleResult:
    result = ModuleResult(name="disease")
    fetcher = fetcher or CachedFetcher(settings.data_root / "cache", offline=offline)

    details = None
    try:
        details = target_disease(ctx.ensembl_id, fetcher)
    except Exception as exc:
        result.caveats.append(f"disease: Open Targets unavailable ({exc})")

    if details:
        associated = details.get("associatedDiseases") or {}
        rows = associated.get("rows") or []
        if rows:
            frame = pd.DataFrame(
                [
                    {
                        "disease_id": row["disease"]["id"],
                        "disease": row["disease"]["name"],
                        "score": round(float(row["score"]), 3),
                        "datasources": len(row.get("datatypeScores") or []),
                    }
                    for row in rows
                    if row.get("disease")
                ]
            ).sort_values("score", ascending=False)
            result.tables["diseases"] = frame.reset_index(drop=True)
            result.facts.update(
                {
                    "disease_count": int(associated.get("count") or 0),
                    "top_disease": str(frame.iloc[0]["disease"]),
                    "top_disease_score": float(frame.iloc[0]["score"]),
                    "top_diseases": ", ".join(frame.head(3)["disease"].astype(str)),
                }
            )

            counts: Counter[str] = Counter()
            for row in rows:
                for component in row.get("datatypeScores") or []:
                    if float(component.get("score") or 0) > 0:
                        counts[component["id"]] += 1
            if counts:
                datasources = pd.DataFrame(
                    sorted(counts.items(), key=lambda item: (-item[1], item[0])),
                    columns=["datasource", "diseases"],
                )
                datasources["datasource"] = datasources["datasource"].map(
                    lambda value: DATASOURCE_LABELS.get(value, value)
                )
                result.tables["datasources"] = datasources

        constraint = details.get("geneticConstraint") or []
        lof = next(
            (item for item in constraint if item.get("constraintType") == "lof"), None
        )
        if lof:
            loeuf = float(lof.get("oeUpper") or 0)
            result.facts.update(
                {
                    "pli": round(float(lof.get("score") or 0), 4),
                    "loeuf": round(loeuf, 4),
                    "lof_oe": round(float(lof.get("oe") or 0), 4),
                    "constrained": (
                        "Yes"
                        if loeuf < settings.thresholds.loeuf_constrained
                        else "No"
                    ),
                }
            )
            result.tables["constraint"] = pd.DataFrame(
                [
                    {
                        "type": CONSTRAINT_LABELS.get(
                            item.get("constraintType"), item.get("constraintType")
                        ),
                        "score": item.get("score"),
                        "oe": item.get("oe"),
                        "oe_upper": item.get("oeUpper"),
                    }
                    for item in constraint
                ]
            )

    clinvar = None
    try:
        clinvar = fetch_clinvar(ctx.symbol, fetcher)
    except Exception as exc:
        result.caveats.append(f"disease: ClinVar unavailable ({exc})")

    if clinvar:
        result.facts["clinvar_total"] = clinvar["total"]
        result.facts["clinvar_pathogenic_submissions"] = clinvar[
            "pathogenic_submissions"
        ]
        records = clinvar.get("records") or []
        strong = [record for record in records if _is_pathogenic(record["classification"])]
        chosen = strong or records
        if chosen:
            result.tables["clinvar"] = pd.DataFrame(
                [
                    {
                        "variant": record["title"],
                        "classification": record["classification"],
                        "review": record["review_status"],
                    }
                    for record in chosen[:10]
                ]
            )
            result.facts["clinvar_top_variant"] = chosen[0]["title"]
        if clinvar["pathogenic_submissions"] > len(strong):
            result.caveats.append(
                "disease: ClinVar 计数含存在致病提交的记录，聚合分类可能为 VUS 或冲突"
            )

    if not result.tables:
        return result.degrade("disease: no disease association data")
    return result
```

- [x] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_disease.py -v`
Expected: PASS

---

### Task 4: tractability 分析模块

**Files:**
- Create: `src/target_profile/analysis/tractability.py`
- Create: `tests/test_tractability.py`

- [x] **Step 1: 写失败测试**

```python
# tests/test_tractability.py
import json

from target_profile.analysis.tractability import analyze_tractability
from target_profile.config import Settings
from target_profile.models import GeneContext


def _settings(tmp_path):
    ensg = tmp_path / "data" / "cache" / "ENSG00000133703"
    ensg.mkdir(parents=True)
    (ensg / "opentargets_tractability.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "tractability": [
                            {"modality": "SM", "label": "Approved Drug", "value": True},
                            {"modality": "SM", "label": "Structure with Ligand", "value": True},
                            {"modality": "SM", "label": "High-Quality Pocket", "value": False},
                            {"modality": "AB", "label": "Approved Drug", "value": False},
                            {"modality": "AB", "label": "Advanced Clinical", "value": True},
                        ],
                        "chemicalProbes": [
                            {"id": "ACBI3", "drugId": "CHEMBL6195033", "mechanismOfAction": ["degrader"], "isHighQuality": True},
                            {"id": "ARS-1620", "drugId": "CHEMBL4214264", "mechanismOfAction": ["inhibitor"], "isHighQuality": False},
                        ],
                        "drugAndClinicalCandidates": {
                            "count": 2,
                            "rows": [
                                {"id": "a", "maxClinicalStage": "APPROVAL", "drug": {"id": "CHEMBL4535757", "name": "SOTORASIB"}, "diseases": [{"disease": {"id": "MONDO_0005233", "name": "non-small cell lung carcinoma"}}]},
                                {"id": "b", "maxClinicalStage": "PHASE_2", "drug": {"id": "CHEMBL23293", "name": "SALIRASIB"}, "diseases": [{"disease": None}, {"disease": {"id": "MONDO_0008903", "name": "lung cancer"}}]},
                            ],
                        },
                    }
                }
            }
        )
    )
    return Settings(lake_root=tmp_path / "lake", data_root=tmp_path / "data", out_root=tmp_path / "out")


def test_tractability_facts(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703")
    result = analyze_tractability(ctx, _settings(tmp_path), offline=True)
    assert result.status == "ok"
    assert result.facts["tractable"] == "Yes"
    assert result.facts["approved_modalities"] == "Small molecule"
    assert result.facts["advanced_clinical_modalities"] == "Antibody"
    assert result.facts["n_probes"] == 2
    assert result.facts["n_high_quality_probes"] == 1
    assert result.facts["top_probe"] == "ACBI3"
    assert result.facts["n_drugs"] == 2
    assert result.facts["max_clinical_stage"] == "Approved"
    assert result.facts["approved_drug_count"] == 1
    assert len(result.tables["drugs"]) == 2
    assert result.tables["drugs"].iloc[0]["drug"] == "SOTORASIB"
```

- [x] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_tractability.py -v`
Expected: FAIL（模块不存在）

- [x] **Step 3: 实现 tractability 分析**

```python
# src/target_profile/analysis/tractability.py
import pandas as pd

from target_profile.api.cache import CachedFetcher
from target_profile.api.opentargets import target_tractability
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult

MODALITY_LABELS = {
    "SM": "Small molecule",
    "AB": "Antibody",
    "PR": "PROTAC",
    "OC": "Other modality",
}
STAGE_LABELS = {
    "APPROVAL": "Approved",
    "PHASE_4": "Phase 4",
    "PHASE_3": "Phase 3",
    "PHASE_2": "Phase 2",
    "PHASE_1": "Phase 1",
    "PRECLINICAL": "Preclinical",
    "UNKNOWN": "Unknown",
}
STAGE_ORDER = {label: index for index, label in enumerate(STAGE_LABELS.values())}


def analyze_tractability(
    ctx: GeneContext,
    settings: Settings,
    offline: bool = True,
    fetcher: CachedFetcher | None = None,
) -> ModuleResult:
    result = ModuleResult(name="tractability")
    fetcher = fetcher or CachedFetcher(settings.data_root / "cache", offline=offline)

    details = None
    try:
        details = target_tractability(ctx.ensembl_id, fetcher)
    except Exception as exc:
        result.caveats.append(f"tractability: Open Targets unavailable ({exc})")

    if details:
        rows = details.get("tractability") or []
        if rows:
            frame = pd.DataFrame(
                [
                    {
                        "modality": MODALITY_LABELS.get(row["modality"], row["modality"]),
                        "bucket": row["label"],
                        "available": bool(row["value"]),
                    }
                    for row in rows
                ]
            )
            result.tables["tractability"] = frame
            available = frame[frame["available"]]
            approved = sorted(
                set(available.loc[available["bucket"] == "Approved Drug", "modality"])
            )
            advanced = sorted(
                set(
                    available.loc[
                        available["bucket"] == "Advanced Clinical", "modality"
                    ]
                )
            )
            result.facts.update(
                {
                    "tractable": "Yes" if approved or advanced else "No",
                    "approved_modalities": ", ".join(approved) or "None",
                    "advanced_clinical_modalities": ", ".join(advanced) or "None",
                }
            )

        probes = details.get("chemicalProbes") or []
        if probes:
            probe_frame = pd.DataFrame(
                [
                    {
                        "probe": probe.get("id"),
                        "drug_id": probe.get("drugId"),
                        "mechanism": ", ".join(probe.get("mechanismOfAction") or []),
                        "high_quality": bool(probe.get("isHighQuality")),
                    }
                    for probe in probes
                ]
            ).sort_values(
                ["high_quality", "probe"], ascending=[False, True]
            ).reset_index(drop=True)
            result.tables["probes"] = probe_frame
            result.facts.update(
                {
                    "n_probes": int(len(probe_frame)),
                    "n_high_quality_probes": int(probe_frame["high_quality"].sum()),
                    "top_probe": str(probe_frame.iloc[0]["probe"]),
                }
            )

        candidates = details.get("drugAndClinicalCandidates") or {}
        drug_rows = candidates.get("rows") or []
        if drug_rows:
            records = []
            for row in drug_rows:
                drug = row.get("drug") or {}
                diseases = sorted(
                    {
                        (item.get("disease") or {}).get("name")
                        for item in row.get("diseases") or []
                        if (item.get("disease") or {}).get("name")
                    }
                )
                records.append(
                    {
                        "drug": drug.get("name") or row.get("id"),
                        "drug_id": drug.get("id"),
                        "stage": STAGE_LABELS.get(
                            row.get("maxClinicalStage"), row.get("maxClinicalStage")
                        ),
                        "diseases": ", ".join(diseases[:3]),
                    }
                )
            drug_frame = pd.DataFrame(records)
            drug_frame["stage_order"] = drug_frame["stage"].map(STAGE_ORDER).fillna(99)
            drug_frame = drug_frame.sort_values(
                ["stage_order", "drug"]
            ).drop(columns="stage_order").reset_index(drop=True)
            result.tables["drugs"] = drug_frame
            result.tables["drug_stages"] = (
                drug_frame["stage"]
                .value_counts()
                .rename_axis("stage")
                .reset_index(name="count")
            )
            result.facts.update(
                {
                    "n_drugs": int(len(drug_frame)),
                    "max_clinical_stage": str(drug_frame.iloc[0]["stage"]),
                    "approved_drug_count": int(
                        (drug_frame["stage"] == "Approved").sum()
                    ),
                }
            )

    if not result.tables:
        return result.degrade("tractability: no tractability data")
    return result
```

- [x] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_tractability.py -v`
Expected: PASS

---

### Task 5: safety 分析模块

**Files:**
- Create: `src/target_profile/analysis/safety.py`
- Create: `tests/test_safety.py`

- [x] **Step 1: 写失败测试**

```python
# tests/test_safety.py
import json

import pandas as pd

from target_profile.analysis.safety import analyze_safety
from target_profile.config import Settings
from target_profile.models import GeneContext


def _settings(tmp_path, liabilities):
    ensg = tmp_path / "data" / "cache" / "ENSG00000133703"
    ensg.mkdir(parents=True)
    (ensg / "opentargets_safety.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "safetyLiabilities": liabilities,
                        "mousePhenotypes": [
                            {
                                "modelPhenotypeLabel": "small liver",
                                "modelPhenotypeClasses": [{"id": "MP:0005370", "label": "liver/biliary system phenotype"}],
                            },
                            {
                                "modelPhenotypeLabel": "increased heart weight",
                                "modelPhenotypeClasses": [{"id": "MP:0005385", "label": "cardiovascular system phenotype"}],
                            },
                            {
                                "modelPhenotypeLabel": "enlarged heart",
                                "modelPhenotypeClasses": [{"id": "MP:0005385", "label": "cardiovascular system phenotype"}],
                            },
                        ],
                        "geneticConstraint": [{"constraintType": "lof", "score": 0.9998, "oeUpper": 0.2264}],
                        "isEssential": True,
                        "homologues": [
                            {"speciesName": "Human", "homologyType": "within_species_paralog", "targetGeneId": "ENSG00000126458", "queryPercentageIdentity": 53.7234, "targetPercentageIdentity": 46.3303}
                        ],
                    }
                }
            }
        )
    )
    parquet = tmp_path / "data" / "parquet"
    parquet.mkdir(parents=True)
    pd.DataFrame(
        {
            "Gene": ["KRAS", "KRAS", "KRAS"],
            "Tissue": ["Lung", "Liver", "Brain"],
            "Expression": [12.0, 2.0, 0.2],
        }
    ).to_parquet(parquet / "gtex.parquet", index=False)
    return Settings(lake_root=tmp_path / "lake", data_root=tmp_path / "data", out_root=tmp_path / "out")


def test_safety_facts_and_caveat(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703")
    result = analyze_safety(ctx, _settings(tmp_path, []), offline=True)
    assert result.status == "ok"
    assert result.facts["n_safety_liabilities"] == 0
    assert any("无安全记录不代表安全" in caveat for caveat in result.caveats)
    assert result.facts["n_mouse_phenotypes"] == 3
    assert result.facts["top_mouse_phenotype_class"] == "cardiovascular system phenotype"
    assert result.facts["common_essential"] == "Yes"
    assert result.facts["loeuf"] == 0.2264
    assert result.facts["n_paralogues"] == 1
    assert result.facts["top_paralogue_identity"] == 53.7
    assert result.facts["n_tissues_expressed"] == 2
    assert result.facts["tissue_count"] == 3
    assert len(result.tables["expression_breadth"]) == 3


def test_safety_with_liabilities(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703")
    liabilities = [
        {
            "event": "drug toxicity",
            "datasource": "ClinPGx",
            "effects": [{"direction": "Activation/Increase/Upregulation"}],
            "studies": [{"name": "antineoplastic agents induced effect", "type": "clinical"}],
        }
    ]
    result = analyze_safety(ctx, _settings(tmp_path, liabilities), offline=True)
    assert result.facts["n_safety_liabilities"] == 1
    assert result.facts["top_safety_event"] == "drug toxicity"
    assert result.facts["safety_datasources"] == "ClinPGx"
    assert len(result.tables["liabilities"]) == 1
```

- [x] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_safety.py -v`
Expected: FAIL（模块不存在）

- [x] **Step 3: 实现 safety 分析**

```python
# src/target_profile/analysis/safety.py
from collections import Counter

import pandas as pd

from target_profile.analysis.expression import _read, _tau
from target_profile.api.cache import CachedFetcher
from target_profile.api.opentargets import target_safety
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult


def analyze_safety(
    ctx: GeneContext,
    settings: Settings,
    offline: bool = True,
    fetcher: CachedFetcher | None = None,
) -> ModuleResult:
    result = ModuleResult(name="safety")
    fetcher = fetcher or CachedFetcher(settings.data_root / "cache", offline=offline)

    details = None
    try:
        details = target_safety(ctx.ensembl_id, fetcher)
    except Exception as exc:
        result.caveats.append(f"safety: Open Targets unavailable ({exc})")

    if details:
        liabilities = details.get("safetyLiabilities") or []
        result.facts["n_safety_liabilities"] = int(len(liabilities))
        if liabilities:
            rows = [
                {
                    "event": item.get("event") or item.get("eventId"),
                    "datasource": item.get("datasource"),
                    "effect": ", ".join(
                        sorted(
                            {
                                effect.get("direction")
                                for effect in item.get("effects") or []
                                if effect.get("direction")
                            }
                        )
                    ),
                    "studies": ", ".join(
                        sorted(
                            {
                                study.get("name")
                                for study in item.get("studies") or []
                                if study.get("name")
                            }
                        )[:3]
                    ),
                }
                for item in liabilities
            ]
            result.tables["liabilities"] = pd.DataFrame(rows)
            result.facts["safety_datasources"] = ", ".join(
                sorted(
                    {
                        item.get("datasource")
                        for item in liabilities
                        if item.get("datasource")
                    }
                )
            )
            result.facts["top_safety_event"] = str(rows[0]["event"])

        mouse = details.get("mousePhenotypes") or []
        if mouse:
            labels: set[str] = set()
            class_counts: Counter[str] = Counter()
            for item in mouse:
                if item.get("modelPhenotypeLabel"):
                    labels.add(item["modelPhenotypeLabel"])
                for phenotype_class in item.get("modelPhenotypeClasses") or []:
                    if phenotype_class.get("label"):
                        class_counts[phenotype_class["label"]] += 1
            if class_counts:
                class_frame = pd.DataFrame(
                    sorted(class_counts.items(), key=lambda item: (-item[1], item[0])),
                    columns=["phenotype_class", "models"],
                )
                result.tables["mouse_phenotypes"] = class_frame
                result.facts["n_mouse_phenotypes"] = int(len(labels))
                result.facts["top_mouse_phenotype_class"] = str(
                    class_frame.iloc[0]["phenotype_class"]
                )
                result.facts["mouse_phenotype_examples"] = "; ".join(
                    sorted(labels)[:3]
                )

        constraint = details.get("geneticConstraint") or []
        lof = next(
            (item for item in constraint if item.get("constraintType") == "lof"), None
        )
        if lof:
            loeuf = float(lof.get("oeUpper") or 0)
            result.facts["loeuf"] = round(loeuf, 4)
            result.facts["constrained"] = (
                "Yes" if loeuf < settings.thresholds.loeuf_constrained else "No"
            )

        if details.get("isEssential") is not None:
            result.facts["common_essential"] = (
                "Yes" if details["isEssential"] else "No"
            )

        paralogues = [
            item
            for item in details.get("homologues") or []
            if "paralog" in (item.get("homologyType") or "")
            and item.get("targetGeneId") != ctx.ensembl_id
        ]
        if paralogues:
            result.facts["n_paralogues"] = int(len(paralogues))
            best = max(
                paralogues,
                key=lambda item: float(item.get("queryPercentageIdentity") or 0),
            )
            result.facts["top_paralogue_identity"] = round(
                float(best.get("queryPercentageIdentity") or 0), 1
            )

    gtex = _read(settings.data_root / "parquet" / "gtex.parquet")
    sub = gtex[gtex["Gene"] == ctx.symbol]
    if not sub.empty:
        tissue = sub.groupby("Tissue")["Expression"].median()
        result.tables["expression_breadth"] = (
            tissue.sort_values(ascending=False)
            .rename_axis("tissue")
            .reset_index(name="median")
        )
        result.facts["n_tissues_expressed"] = int(
            (tissue >= settings.thresholds.expression_breadth_tpm).sum()
        )
        result.facts["tissue_count"] = int(len(tissue))
        result.facts["expression_tau"] = round(_tau(tissue), 3)

    result.caveats.append("safety: 无安全记录不代表安全；安全性维度数据天然稀疏")

    if not result.tables:
        return result.degrade("safety: no safety data")
    return result
```

- [x] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_safety.py -v`
Expected: 2 passed

---

### Task 6: 疾病 / 可成药性 / 安全性图表

**Files:**
- Modify: `src/target_profile/figures/charts.py`
- Modify: `tests/test_figures.py`

- [x] **Step 1: 写失败测试（追加到 `tests/test_figures.py`）**

```python
from target_profile.figures.charts import plot_disease, plot_safety, plot_tractability


def test_disease_figure(tmp_path):
    r = _result(
        "disease",
        {
            "diseases": pd.DataFrame(
                {"disease_id": ["MONDO_1", "MONDO_2"], "disease": ["Noonan syndrome", "NSCLC"], "score": [0.83, 0.80], "datasources": [5, 4]}
            ),
            "datasources": pd.DataFrame({"datasource": ["Genetic association", "Literature"], "diseases": [2, 2]}),
        },
    )
    paths = plot_disease(r, tmp_path)
    assert len(paths) == 1
    assert paths[0].exists() and paths[0].stat().st_size > 0


def test_tractability_figure(tmp_path):
    r = _result(
        "tractability",
        {
            "tractability": pd.DataFrame(
                {
                    "modality": ["Small molecule", "Small molecule", "Antibody", "Antibody"],
                    "bucket": ["Approved Drug", "Structure with Ligand", "Approved Drug", "Advanced Clinical"],
                    "available": [True, True, False, True],
                }
            ),
            "drug_stages": pd.DataFrame({"stage": ["Approved", "Phase 2"], "count": [1, 1]}),
        },
    )
    paths = plot_tractability(r, tmp_path)
    assert len(paths) == 1
    assert paths[0].exists() and paths[0].stat().st_size > 0


def test_safety_figure(tmp_path):
    r = _result(
        "safety",
        {
            "mouse_phenotypes": pd.DataFrame(
                {"phenotype_class": ["cardiovascular system phenotype", "liver/biliary system phenotype"], "models": [22, 9]}
            ),
            "expression_breadth": pd.DataFrame({"tissue": ["Lung", "Liver", "Brain"], "median": [12.0, 2.0, 0.2]}),
        },
    )
    paths = plot_safety(r, tmp_path)
    assert len(paths) == 1
    assert paths[0].exists() and paths[0].stat().st_size > 0
```

同时把 `tests/test_figures.py` 顶部的 import 改为包含三个新函数：

```python
from target_profile.figures.charts import (
    plot_dependency,
    plot_disease,
    plot_expression,
    plot_mutation,
    plot_pathway,
    plot_ptm,
    plot_safety,
    plot_tractability,
)
```

- [x] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_figures.py -v`
Expected: FAIL（`plot_disease` / `plot_tractability` / `plot_safety` 未定义）

- [x] **Step 3: 实现三组图（追加到 `figures/charts.py`）**

```python
def plot_disease(result: ModuleResult, out_dir: Path) -> list[Path]:
    apply_theme()
    fig, axes = plt.subplots(1, 2, figsize=(16.5 / 2.54, 6 / 2.54 * 1.6))
    diseases = result.tables.get("diseases")
    if diseases is not None and not diseases.empty:
        top = diseases.head(12).iloc[::-1]
        axes[0].barh(top["disease"], top["score"], color=PALETTE[0])
        axes[0].set_title("Top associated diseases")
        axes[0].set_xlabel("Open Targets association score")
        axes[0].tick_params(labelsize=5)
    else:
        axes[0].text(0.5, 0.5, "No disease data", ha="center", va="center")
        axes[0].set_axis_off()

    datasources = result.tables.get("datasources")
    if datasources is not None and not datasources.empty:
        top = datasources.head(12).iloc[::-1]
        axes[1].barh(top["datasource"], top["diseases"], color=PALETTE[4])
        axes[1].set_title("Evidence by data source")
        axes[1].set_xlabel("Top-ranked diseases with evidence")
        axes[1].tick_params(labelsize=6)
    else:
        axes[1].text(0.5, 0.5, "No source breakdown", ha="center", va="center")
        axes[1].set_axis_off()

    fig.tight_layout()
    return [save(fig, out_dir, "disease")]


def plot_tractability(result: ModuleResult, out_dir: Path) -> list[Path]:
    apply_theme()
    fig, axes = plt.subplots(1, 2, figsize=(16.5 / 2.54, 6 / 2.54 * 1.6))
    tractability = result.tables.get("tractability")
    if tractability is not None and not tractability.empty:
        pivot = (
            tractability.pivot_table(
                index="modality", columns="bucket", values="available", aggfunc="max"
            )
            .fillna(False)
        )
        axes[0].imshow(pivot.values.astype(float), cmap="Blues", aspect="auto")
        axes[0].set_xticks(
            range(len(pivot.columns)),
            pivot.columns,
            rotation=45,
            ha="right",
            fontsize=4,
        )
        axes[0].set_yticks(range(len(pivot.index)), pivot.index, fontsize=6)
        axes[0].set_title("Tractability buckets")
    else:
        axes[0].text(0.5, 0.5, "No tractability data", ha="center", va="center")
        axes[0].set_axis_off()

    stages = result.tables.get("drug_stages")
    if stages is not None and not stages.empty:
        axes[1].barh(stages["stage"].iloc[::-1], stages["count"].iloc[::-1], color=PALETTE[2])
        axes[1].set_title("Drugs and clinical candidates")
        axes[1].set_xlabel("Count")
        axes[1].tick_params(labelsize=6)
    else:
        axes[1].text(0.5, 0.5, "No drug data", ha="center", va="center")
        axes[1].set_axis_off()

    fig.tight_layout()
    return [save(fig, out_dir, "tractability")]


def plot_safety(result: ModuleResult, out_dir: Path) -> list[Path]:
    apply_theme()
    fig, axes = plt.subplots(1, 2, figsize=(16.5 / 2.54, 6 / 2.54 * 1.6))
    phenotypes = result.tables.get("mouse_phenotypes")
    if phenotypes is not None and not phenotypes.empty:
        top = phenotypes.head(12).iloc[::-1]
        axes[0].barh(top["phenotype_class"], top["models"], color=PALETTE[3])
        axes[0].set_title("IMPC mouse phenotypes")
        axes[0].set_xlabel("Models affected")
        axes[0].tick_params(labelsize=5)
    else:
        axes[0].text(0.5, 0.5, "No mouse phenotype data", ha="center", va="center")
        axes[0].set_axis_off()

    breadth = result.tables.get("expression_breadth")
    if breadth is not None and not breadth.empty:
        top = breadth.head(15).iloc[::-1]
        axes[1].barh(top["tissue"], top["median"], color=PALETTE[1])
        axes[1].set_title("GTEx expression breadth")
        axes[1].set_xlabel("Median TPM")
        axes[1].tick_params(labelsize=6)
    else:
        axes[1].text(0.5, 0.5, "No expression data", ha="center", va="center")
        axes[1].set_axis_off()

    fig.tight_layout()
    return [save(fig, out_dir, "safety")]
```

- [x] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_figures.py -v`
Expected: 8 passed

---

### Task 7: 报告标签、章节标题与页脚

**Files:**
- Modify: `src/target_profile/report/render.py`
- Modify: `src/target_profile/report/templates/report.html.j2`
- Modify: `tests/test_render.py`

- [x] **Step 1: 写失败测试（追加到 `tests/test_render.py`）**

```python
def test_render_tier1_section_titles(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703")
    r = ModuleResult(
        name="disease",
        facts={"disease_count": 2262, "pli": 0.9998, "clinvar_total": 628},
    )
    html_path, _ = render_report(ctx, [r], tmp_path / "out")
    html = html_path.read_text(encoding="utf-8")
    assert "疾病关联与遗传证据" in html
    assert "疾病关联数" in html
    assert "pLI" in html
    assert "ClinVar 记录数" in html


def test_render_safety_no_record_warning(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703")
    r = ModuleResult(name="safety", facts={"n_safety_liabilities": 0})
    r.caveats.append("safety: 无安全记录不代表安全；安全性维度数据天然稀疏")
    html_path, _ = render_report(ctx, [r], tmp_path / "out")
    html = html_path.read_text(encoding="utf-8")
    assert "安全性与风险" in html
    assert "无安全记录不代表安全" in html
```

- [x] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_render.py -v`
Expected: FAIL（标题显示为 `disease`/`safety`，标签显示原始 key）

- [x] **Step 3: 扩充映射与页脚**

`src/target_profile/report/render.py` 的 `FACT_LABELS` 增加：

```python
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
```

`SECTION_TITLES` 增加：

```python
    "disease": "疾病关联与遗传证据",
    "tractability": "可成药性与药物",
    "safety": "安全性与风险",
```

`report.html.j2` 页脚整段替换为：

```html
<footer>
  <p>数据来源：GTEx v8、DepMap、HPA、cBioPortal TCGA PanCancer Atlas、Open Targets（Reactome/GO、疾病关联、可成药性、安全性）、STRING、UniProt、AlphaFold DB、ClinVar。仅供科研参考，不构成临床诊疗建议。</p>
</footer>
```

- [x] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_render.py -v`
Expected: 4 passed

---

### Task 8: CLI 接线与 fetch 预热

**Files:**
- Modify: `src/target_profile/cli.py`
- Modify: `tests/test_cli_run.py`

- [x] **Step 1: 写失败测试（把 `test_cli_run.py` 中既有的 `test_run_offline_declares_new_sections` 替换为下面版本）**

```python
def test_run_offline_declares_new_sections(tmp_path, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setenv("TARGET_PROFILE_HOME", str(home))
    result = CliRunner().invoke(
        app, ["run", "KRAS", "--offline", "--no-llm", "--format", "html"]
    )
    assert result.exit_code == 0, result.output
    out_dir = next((home / "out").glob("KRAS_*"))
    facts = json.loads((out_dir / "facts.json").read_text())
    assert set(facts["modules"]) == {
        "basic",
        "disease",
        "expression",
        "mutation",
        "dependency",
        "pathway",
        "ptm",
        "tractability",
        "safety",
    }
```

- [x] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_cli_run.py::test_run_offline_declares_new_sections -v`
Expected: FAIL（modules 只有 6 个）

- [x] **Step 3: 接线 CLI**

导入区增加：

```python
from target_profile.analysis.disease import analyze_disease
from target_profile.analysis.safety import analyze_safety
from target_profile.analysis.tractability import analyze_tractability
from target_profile.api.clinvar import fetch_clinvar
from target_profile.api.opentargets import (
    target_basic,
    target_details,
    target_disease,
    target_pathways,
    target_safety,
    target_tractability,
)
from target_profile.figures.charts import (
    plot_dependency,
    plot_disease,
    plot_expression,
    plot_mutation,
    plot_pathway,
    plot_ptm,
    plot_safety,
    plot_tractability,
)
```

模块与绘图注册改为：

```python
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
PLOTTERS = {
    "expression": plot_expression,
    "mutation": plot_mutation,
    "dependency": plot_dependency,
    "pathway": plot_pathway,
    "ptm": plot_ptm,
    "disease": plot_disease,
    "tractability": plot_tractability,
    "safety": plot_safety,
}
```

`fetch` 的 `steps` 列表在现有 4 条 OT/STRING 之后、UniProt 之前插入 3 条，并在 cBioPortal 之后追加 ClinVar：

```python
    steps = [
        ("Open Targets target", lambda: target_details(ctx.ensembl_id, fetcher, refresh=refresh)),
        ("Open Targets basic", lambda: target_basic(ctx.ensembl_id, fetcher, refresh=refresh)),
        ("Open Targets pathways", lambda: target_pathways(ctx.ensembl_id, fetcher, refresh=refresh)),
        ("Open Targets disease", lambda: target_disease(ctx.ensembl_id, fetcher, refresh=refresh)),
        ("Open Targets tractability", lambda: target_tractability(ctx.ensembl_id, fetcher, refresh=refresh)),
        ("Open Targets safety", lambda: target_safety(ctx.ensembl_id, fetcher, refresh=refresh)),
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
```

- [x] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_cli_run.py -v`
Expected: 3 passed

---

### Task 9: 集成测试扩展

**Files:**
- Modify: `tests/integration/test_vertical_slice.py`

- [x] **Step 1: 扩展 fixture 并添加断言**

在 `_build_home` 的循环里（`global_dir` 写入 AlphaFold 之后、循环结束前）追加以下缓存。注意：`opentargets_*` 在 Ensembl 目录，`clinvar_*` 在基因符号目录。

```python
        (ensg_dir / "opentargets_disease.json").write_text(
            json.dumps(
                {
                    "data": {
                        "target": {
                            "associatedDiseases": {
                                "count": 1,
                                "rows": [
                                    {
                                        "disease": {"id": "MONDO_1", "name": "Noonan syndrome"},
                                        "score": 0.8,
                                        "datatypeScores": [{"id": "genetic_association", "score": 0.9}],
                                    }
                                ],
                            },
                            "geneticConstraint": [
                                {"constraintType": "lof", "score": 0.99, "oe": 0.05, "oeUpper": 0.22}
                            ],
                        }
                    }
                }
            )
        )
        (ensg_dir / "opentargets_tractability.json").write_text(
            json.dumps(
                {
                    "data": {
                        "target": {
                            "tractability": [
                                {"modality": "SM", "label": "Approved Drug", "value": True}
                            ],
                            "chemicalProbes": [],
                            "drugAndClinicalCandidates": {
                                "count": 1,
                                "rows": [
                                    {
                                        "id": "d1",
                                        "maxClinicalStage": "APPROVAL",
                                        "drug": {"id": "CHEMBL1", "name": "SOTORASIB"},
                                        "diseases": [{"disease": {"id": "MONDO_1", "name": "NSCLC"}}],
                                    }
                                ],
                            },
                        }
                    }
                }
            )
        )
        (ensg_dir / "opentargets_safety.json").write_text(
            json.dumps(
                {
                    "data": {
                        "target": {
                            "safetyLiabilities": [],
                            "mousePhenotypes": [
                                {
                                    "modelPhenotypeLabel": "small liver",
                                    "modelPhenotypeClasses": [{"id": "MP:1", "label": "liver/biliary system phenotype"}],
                                }
                            ],
                            "geneticConstraint": [{"constraintType": "lof", "score": 0.99, "oeUpper": 0.22}],
                            "isEssential": False,
                            "homologues": [],
                        }
                    }
                }
            )
        )
        (home / "data" / "cache" / gene / "clinvar_search.json").write_text(
            json.dumps({"esearchresult": {"count": "10"}})
        )
        (home / "data" / "cache" / gene / "clinvar_search_pathogenic.json").write_text(
            json.dumps({"esearchresult": {"count": "2", "idlist": ["1", "2"]}})
        )
        (home / "data" / "cache" / gene / "clinvar_summary_pathogenic.json").write_text(
            json.dumps(
                {
                    "result": {
                        "uids": ["1", "2"],
                        "1": {
                            "title": f"{gene} variant 1",
                            "germline_classification": {"description": "Pathogenic", "review_status": "reviewed by expert panel"},
                        },
                        "2": {
                            "title": f"{gene} variant 2",
                            "germline_classification": {"description": "Uncertain significance", "review_status": "criteria provided, single submitter"},
                        },
                    }
                }
            )
        )
```

断言追加：

```python
        assert facts["modules"]["disease"]["status"] == "ok"
        assert facts["modules"]["tractability"]["status"] == "ok"
        assert facts["modules"]["safety"]["status"] == "ok"
```

- [x] **Step 2: 运行确认通过**

Run: `uv run pytest tests/integration/test_vertical_slice.py -v`
Expected: PASS

- [x] **Step 3: 全量测试**

Run: `uv run pytest -q`
Expected: 全部通过（约 57 个用例）

---

### Task 10: 真实数据验收（KRAS / TP53）

**Files:** 无（仅运行命令与检查）

- [x] **Step 1: 预热新缓存**

Run:
```bash
uv run target-profile fetch KRAS
uv run target-profile fetch TP53
```
Expected：输出含 `cached: Open Targets disease`、`cached: Open Targets tractability`、`cached: Open Targets safety`、`cached: ClinVar records`（其余步骤同 M3）。

- [x] **Step 2: 离线生成 KRAS 报告**

Run:
```bash
uv run target-profile run KRAS --offline --no-llm --format both --force
```
Expected：`report.html`、`report.pdf`、`facts.json` 生成；`facts.json` 中：
- `modules.disease.facts.disease_count == 2262`
- `modules.disease.facts.top_disease == "Noonan syndrome"`
- `modules.disease.facts.loeuf` ≈ 0.2264（±0.001）、`constrained == "Yes"`
- `modules.disease.facts.clinvar_total == 628`、`clinvar_pathogenic_submissions == 216`
- `modules.tractability.facts.tractable == "Yes"`、`approved_modalities` 含 `Small molecule`
- `modules.tractability.facts.n_probes == 7`、`n_drugs == 3`、`approved_drug_count == 2`
- `modules.safety.facts.n_safety_liabilities == 0`，且 `caveats` 含 `无安全记录不代表安全`
- `modules.safety.facts.n_mouse_phenotypes == 91`、`common_essential == "Yes"`

检查命令：
```bash
uv run python -c "
import json
f=json.load(open('out/KRAS_20261030/facts.json'))
for m in ('disease','tractability','safety'):
    print(m, f['modules'][m]['status'])
    print(json.dumps(f['modules'][m]['facts'], ensure_ascii=False, indent=1))
    print('caveats:', f['modules'][m]['caveats'])
"
```

- [x] **Step 3: 离线生成 TP53 报告**

Run:
```bash
uv run target-profile run TP53 --offline --no-llm --format html --force
```
Expected：成功；`modules.disease.facts.disease_count == 5198`、`top_disease == "Li-Fraumeni syndrome"`、`clinvar_total == 4059`、`clinvar_pathogenic_submissions == 1767`；`modules.tractability.facts.tractable == "Yes"`、`n_drugs == 9`；`modules.safety.facts.n_safety_liabilities == 4`、`common_essential == "No"`。

- [x] **Step 4: 视觉检查**

```bash
uv run python - <<'EOF'
from pathlib import Path
from playwright.sync_api import sync_playwright
html = Path('out/KRAS_20261030/report.html').resolve()
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1200, "height": 1600})
    page.goto(html.as_uri(), wait_until="load")
    for section in ("disease", "tractability", "safety"):
        page.query_selector(f"section#{section}").screenshot(
            path=f"out/KRAS_20261030/preview_{section}.png"
        )
    browser.close()
EOF
```
Expected：三个章节中文正文与英文图表标签正常；安全章节明确显示"无安全记录不代表安全"。

---

## 里程碑对照

- **M4**：Task 1–10（disease / tractability / safety 三个模块 + 图表 + 报告 + CLI + 验收）
- 后续 **M5**：cancer / comparative / summary / LLM 润色 + 12 章结构完整

## 已知限制（M4 范围）

- 疾病章节不含 `associationTimeSeries` 时间趋势（每病种需额外请求，列入 Tier3 优化）
- ClinVar 计数来自 `esearch` 的"存在致病/可能致病提交"过滤；聚合分类可能为 VUS/冲突，报告以 caveat 明示，表格仅展示聚合分类为致病且非冲突的记录
- tractability 的"靶点类别/亚细胞定位/AlphaFold 可用性"已在 basic 章节呈现，M4 不重复取数
- 安全性维度天然稀疏："无记录 ≠ 安全"以固定 caveat 呈现；旁系同源仅做数量与最高一致性摘要（完整比较基因组学在 M5）
- 小鼠表型取 Open Targets 的 IMPC 汇总，不做每基因 KO 显著性统计
