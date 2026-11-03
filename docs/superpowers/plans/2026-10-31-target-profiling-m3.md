# Target Profiling M3（基础报告补齐）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 M2 垂直切片上补齐「基因与蛋白基础」「通路与相互作用」「蛋白修饰」三个模块，使报告第 2/4/5/6/7/8 章完整。

**Architecture:** 新增三个 API 适配器（OT basic/pathway 查询、UniProt、STRING、AlphaFold），全部经 `CachedFetcher` 按基因缓存；新增三个 analysis 模块输出 `ModuleResult`；新增两组图（通路、PTM）；扩展 CLI 的 `fetch` 预热全部 API 缓存。所有测试离线，真实网络只用于手工验收。

**Tech Stack:** Python 3.13、uv、pandas、matplotlib、Jinja2、Typer、httpx、pytest。

**约束：** 用户要求暂不使用 git，本计划不含 commit 步骤。项目根 `/root/target_profiling`，命令一律用 `uv run`。

**已验证的外部接口（2026-10-30 实测）：**
- OT `target(ensemblId:)` 支持 `functionDescriptions`、`targetClass{label level}`、`subcellularLocations{location termSL labelSL}`、`synonyms{label source}`、`pathways{pathwayId pathway topLevelTerm}`、`geneOntology{aspect evidence term{id label}}`；KRAS 有 71 条通路、193 条 GO 记录（C 151 / P 24 / F 18）
- UniProt `uniprotkb/{acc}.json`：`sequence.length`、`proteinDescription.recommendedName.fullName.value`、`comments[commentType==FUNCTION].texts[0].value`、`features[{type,location.start.value,location.end.value,description}]`；KRAS P01116 长 189 aa，`Modified residue`×4、`Lipidation`×5、`Glycosylation`×1、`Region`×1
- STRING `interaction_partners` 返回 `preferredName_B` 与 `score`（0–1 浮点，combined score）；阈值取 ≥0.7 对应 700/1000
- AlphaFold `api/prediction/{acc}` 返回列表，`[0].globalMetricValue` 为平均 pLDDT（KRAS 91.5）

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `src/target_profile/api/opentargets.py`（改） | 新增 `target_basic()`、`target_pathways()` |
| `src/target_profile/api/uniprot.py`（新） | `uniprot_record()`：完整 UniProt JSON |
| `src/target_profile/api/stringdb.py`（新） | `interaction_partners()`：Top 100 互作伙伴 |
| `src/target_profile/api/alphafold.py`（新） | `alphafold_prediction()`：结构可用性 + pLDDT |
| `src/target_profile/analysis/basic.py`（新） | 基因/蛋白基础 facts |
| `src/target_profile/analysis/pathway.py`（新） | Reactome/GO + STRING 伙伴 |
| `src/target_profile/analysis/ptm.py`（新） | UniProt curated PTM 位点 + 结构域/区域 |
| `src/target_profile/figures/charts.py`（改） | 新增 `plot_pathway()`、`plot_ptm()` |
| `src/target_profile/report/render.py`（改） | 新增章节标题与 fact 标签 |
| `src/target_profile/report/templates/report.html.j2`（改） | 页脚数据来源更新 |
| `src/target_profile/cli.py`（改） | 6 个模块接线；`fetch` 预热新缓存 |
| `src/target_profile/api/cbioportal.py`（改） | `fetch_pancan_mutations` 支持 `refresh` |
| `src/target_profile/config.py` + `config/settings.toml`（改） | 新增 `string_min_score = 0.7` |
| `tests/test_opentargets.py`（新）、`tests/test_api_sources.py`（新） | 适配器层 |
| `tests/test_basic.py`、`tests/test_pathway.py`、`tests/test_ptm.py`（新） | 分析模块 |
| `tests/test_figures.py`（改）、`tests/test_render.py`（改）、`tests/integration/test_vertical_slice.py`（改） | 图表/报告/集成 |

缓存布局（沿用 M2）：OT 查询按 Ensembl 存 `data/cache/<ENSG>/<name>.json`；STRING 按符号存 `data/cache/<SYMBOL>/string_partners.json`；UniProt/AlphaFold 存 `data/cache/_global/`。

---

### Task 1: OT 基础/通路查询 + STRING 阈值配置

**Files:**
- Modify: `src/target_profile/api/opentargets.py`
- Modify: `src/target_profile/config.py`
- Modify: `config/settings.toml`
- Create: `tests/test_opentargets.py`

- [x] **Step 1: 写失败测试**

```python
# tests/test_opentargets.py
import json

from target_profile.api.cache import CachedFetcher
from target_profile.api.opentargets import target_basic, target_pathways


def test_target_basic_reads_cache(tmp_path):
    cache = tmp_path / "ENSG00000133703"
    cache.mkdir(parents=True)
    (cache / "opentargets_basic.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "id": "ENSG00000133703",
                        "approvedName": "KRAS proto-oncogene, GTPase",
                        "targetClass": [{"label": "Enzyme", "level": "l1"}, {"label": "Hydrolase", "level": "l2"}],
                        "subcellularLocations": [{"location": "Cytoplasm"}],
                        "synonyms": [{"label": "K-Ras", "source": "uniprot"}],
                    }
                }
            }
        )
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    details = target_basic("ENSG00000133703", fetcher)
    assert details["approvedName"].startswith("KRAS")
    assert details["targetClass"][0]["label"] == "Enzyme"


def test_target_pathways_reads_cache(tmp_path):
    cache = tmp_path / "ENSG00000133703"
    cache.mkdir(parents=True)
    (cache / "opentargets_pathways.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "id": "ENSG00000133703",
                        "pathways": [
                            {"pathwayId": "R-HSA-1", "pathway": "Signalling to RAS", "topLevelTerm": "Signal Transduction"},
                            {"pathwayId": "R-HSA-2", "pathway": "RAF/MAP kinase cascade", "topLevelTerm": "Signal Transduction"},
                        ],
                        "geneOntology": [
                            {"aspect": "C", "evidence": "TAS", "term": {"id": "GO:1", "label": "plasma membrane"}},
                            {"aspect": "P", "evidence": "IEA", "term": {"id": "GO:2", "label": "Ras signaling"}},
                        ],
                    }
                }
            }
        )
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    details = target_pathways("ENSG00000133703", fetcher)
    assert len(details["pathways"]) == 2
    assert details["geneOntology"][0]["aspect"] == "C"
```

- [x] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_opentargets.py -v`
Expected: FAIL（`target_basic` / `target_pathways` 不存在）

- [x] **Step 3: 扩展 OT 适配器与配置**

在 `src/target_profile/api/opentargets.py` 末尾追加：

```python
BASIC_QUERY = """
query Basic($id: String!) {
  target(ensemblId: $id) {
    id
    approvedSymbol
    approvedName
    biotype
    functionDescriptions
    targetClass { label level }
    subcellularLocations { location termSL labelSL }
    proteinIds { id source }
    synonyms { label source }
  }
}
"""

PATHWAY_QUERY = """
query Pathways($id: String!) {
  target(ensemblId: $id) {
    id
    pathways { pathwayId pathway topLevelTerm }
    geneOntology { aspect evidence term { id label } }
  }
}
"""


def _target_query(
    ensembl_id: str,
    query: str,
    name: str,
    fetcher: CachedFetcher,
    refresh: bool = False,
) -> dict[str, Any] | None:
    payload = fetcher.request_json(
        name,
        "POST",
        OT_URL,
        gene=ensembl_id,
        json_body={"query": query, "variables": {"id": ensembl_id}},
        refresh=refresh,
    )
    return payload.get("data", {}).get("target")


def target_basic(
    ensembl_id: str, fetcher: CachedFetcher, refresh: bool = False
) -> dict[str, Any] | None:
    return _target_query(ensembl_id, BASIC_QUERY, "opentargets_basic", fetcher, refresh)


def target_pathways(
    ensembl_id: str, fetcher: CachedFetcher, refresh: bool = False
) -> dict[str, Any] | None:
    return _target_query(ensembl_id, PATHWAY_QUERY, "opentargets_pathways", fetcher, refresh)
```

同时给现有 `target_details` 增加可选 `refresh` 参数（供 `fetch --refresh` 使用），签名改为：

```python
def target_details(
    ensembl_id: str, fetcher: CachedFetcher, refresh: bool = False
) -> dict[str, Any] | None:
    payload = fetcher.request_json(
        "opentargets_target",
        "POST",
        OT_URL,
        gene=ensembl_id,
        json_body={"query": TARGET_QUERY, "variables": {"id": ensembl_id}},
        refresh=refresh,
    )
    return payload.get("data", {}).get("target")
```

`src/target_profile/config.py` 的 `Thresholds` 增加一行：

```python
    string_min_score: float = 0.7
```

`config/settings.toml` 的 `[thresholds]` 下增加：

```toml
string_min_score = 0.7
```

- [x] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_opentargets.py -v`
Expected: 2 passed

---

### Task 2: UniProt / STRING / AlphaFold 适配器

**Files:**
- Create: `src/target_profile/api/uniprot.py`
- Create: `src/target_profile/api/stringdb.py`
- Create: `src/target_profile/api/alphafold.py`
- Create: `tests/test_api_sources.py`

- [x] **Step 1: 写失败测试**

```python
# tests/test_api_sources.py
import json

from target_profile.api.alphafold import alphafold_prediction
from target_profile.api.cache import CachedFetcher
from target_profile.api.stringdb import interaction_partners
from target_profile.api.uniprot import uniprot_record


def test_uniprot_record_reads_cache(tmp_path):
    global_dir = tmp_path / "_global"
    global_dir.mkdir(parents=True)
    (global_dir / "uniprot_P01116.json").write_text(
        json.dumps({"sequence": {"length": 189}})
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    record = uniprot_record("P01116", fetcher)
    assert record["sequence"]["length"] == 189


def test_uniprot_record_without_accession_returns_none(tmp_path):
    fetcher = CachedFetcher(tmp_path, offline=True)
    assert uniprot_record(None, fetcher) is None


def test_interaction_partners_reads_cache(tmp_path):
    gene_dir = tmp_path / "KRAS"
    gene_dir.mkdir(parents=True)
    (gene_dir / "string_partners.json").write_text(
        json.dumps([{"preferredName_B": "RAF1", "score": 0.99}])
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    partners = interaction_partners("KRAS", fetcher)
    assert partners[0]["preferredName_B"] == "RAF1"


def test_alphafold_reads_cache(tmp_path):
    global_dir = tmp_path / "_global"
    global_dir.mkdir(parents=True)
    (global_dir / "alphafold_P01116.json").write_text(
        json.dumps([{"globalMetricValue": 91.5}])
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    prediction = alphafold_prediction("P01116", fetcher)
    assert prediction["globalMetricValue"] == 91.5


def test_alphafold_without_accession_returns_none(tmp_path):
    fetcher = CachedFetcher(tmp_path, offline=True)
    assert alphafold_prediction(None, fetcher) is None
```

- [x] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_api_sources.py -v`
Expected: FAIL（模块不存在）

- [x] **Step 3: 实现三个适配器**

```python
# src/target_profile/api/uniprot.py
from typing import Any

from target_profile.api.cache import CachedFetcher

UNIPROT_URL = "https://rest.uniprot.org/uniprotkb/{acc}.json"


def uniprot_record(
    acc: str | None, fetcher: CachedFetcher, refresh: bool = False
) -> dict[str, Any] | None:
    if not acc:
        return None
    return fetcher.request_json(
        f"uniprot_{acc}",
        "GET",
        UNIPROT_URL.format(acc=acc),
        gene="_global",
        refresh=refresh,
    )
```

```python
# src/target_profile/api/stringdb.py
from typing import Any

from target_profile.api.cache import CachedFetcher

STRING_URL = "https://string-db.org/api/json/interaction_partners"


def interaction_partners(
    symbol: str,
    fetcher: CachedFetcher,
    limit: int = 100,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    payload = fetcher.request_json(
        "string_partners",
        "GET",
        STRING_URL,
        gene=symbol,
        params={
            "identifiers": symbol,
            "species": 9606,
            "limit": limit,
            "caller_identity": "target_profile",
        },
        refresh=refresh,
    )
    return payload or []
```

```python
# src/target_profile/api/alphafold.py
from typing import Any

from target_profile.api.cache import CachedFetcher

AF_URL = "https://alphafold.ebi.ac.uk/api/prediction/{acc}"


def alphafold_prediction(
    acc: str | None, fetcher: CachedFetcher, refresh: bool = False
) -> dict[str, Any] | None:
    if not acc:
        return None
    rows = fetcher.request_json(
        f"alphafold_{acc}",
        "GET",
        AF_URL.format(acc=acc),
        gene="_global",
        refresh=refresh,
    )
    return rows[0] if rows else None
```

- [x] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_api_sources.py -v`
Expected: 5 passed

---

### Task 3: basic 分析模块（基因与蛋白基础）

**Files:**
- Create: `src/target_profile/analysis/basic.py`
- Create: `tests/test_basic.py`

- [x] **Step 1: 写失败测试**

```python
# tests/test_basic.py
import json

from target_profile.analysis.basic import analyze_basic
from target_profile.config import Settings
from target_profile.models import GeneContext


def _settings(tmp_path):
    ensg = tmp_path / "data" / "cache" / "ENSG00000133703"
    ensg.mkdir(parents=True)
    (ensg / "opentargets_basic.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "approvedName": "KRAS proto-oncogene, GTPase",
                        "targetClass": [{"label": "Enzyme"}, {"label": "Hydrolase"}],
                        "subcellularLocations": [{"location": "Cell membrane"}, {"location": "Cytoplasm"}],
                        "synonyms": [{"label": "K-Ras"}, {"label": "KRAS2"}],
                    }
                }
            }
        )
    )
    global_dir = tmp_path / "data" / "cache" / "_global"
    global_dir.mkdir(parents=True)
    (global_dir / "uniprot_P01116.json").write_text(
        json.dumps(
            {
                "sequence": {"length": 189},
                "proteinDescription": {"recommendedName": {"fullName": {"value": "GTPase KRas"}}},
                "comments": [{"commentType": "FUNCTION", "texts": [{"value": "Signal transducer."}]}],
                "features": [],
            }
        )
    )
    (global_dir / "alphafold_P01116.json").write_text(json.dumps([{"globalMetricValue": 91.5}]))
    return Settings(lake_root=tmp_path / "lake", data_root=tmp_path / "data", out_root=tmp_path / "out")


def test_basic_facts(tmp_path):
    ctx = GeneContext(
        symbol="KRAS",
        ensembl_id="ENSG00000133703",
        uniprot_id="P01116",
        biotype="protein_coding",
    )
    result = analyze_basic(ctx, _settings(tmp_path), offline=True)
    assert result.status == "ok"
    assert result.facts["approved_name"] == "KRAS proto-oncogene, GTPase"
    assert result.facts["target_class"] == "Enzyme / Hydrolase"
    assert result.facts["protein_length"] == 189
    assert result.facts["protein_name"] == "GTPase KRas"
    assert result.facts["alphafold_available"] == "Yes"
    assert result.facts["alphafold_mean_plddt"] == 91.5
    assert result.facts["synonym_count"] == 2
```

- [x] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_basic.py -v`
Expected: FAIL（`target_profile.analysis.basic` 不存在）

- [x] **Step 3: 实现 basic 分析**

```python
# src/target_profile/analysis/basic.py
from target_profile.api.alphafold import alphafold_prediction
from target_profile.api.cache import CachedFetcher
from target_profile.api.opentargets import target_basic
from target_profile.api.uniprot import uniprot_record
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult


def _uniprot_function(record: dict) -> str | None:
    for comment in record.get("comments") or []:
        if comment.get("commentType") != "FUNCTION":
            continue
        texts = comment.get("texts") or []
        if texts and texts[0].get("value"):
            return texts[0]["value"]
    return None


def analyze_basic(
    ctx: GeneContext,
    settings: Settings,
    offline: bool = True,
    fetcher: CachedFetcher | None = None,
) -> ModuleResult:
    result = ModuleResult(name="basic")
    fetcher = fetcher or CachedFetcher(settings.data_root / "cache", offline=offline)
    result.facts.update({"symbol": ctx.symbol, "ensembl_id": ctx.ensembl_id})
    if ctx.biotype:
        result.facts["biotype"] = ctx.biotype

    details = None
    try:
        details = target_basic(ctx.ensembl_id, fetcher)
    except Exception as exc:
        result.caveats.append(f"basic: Open Targets unavailable ({exc})")

    if details:
        if details.get("approvedName"):
            result.facts["approved_name"] = details["approvedName"]
        classes = [c["label"] for c in details.get("targetClass") or [] if c.get("label")]
        if classes:
            result.facts["target_class"] = " / ".join(classes)
        locations = [
            loc["location"]
            for loc in details.get("subcellularLocations") or []
            if loc.get("location")
        ]
        if locations:
            result.facts["subcellular_locations"] = "; ".join(dict.fromkeys(locations))
        descriptions = details.get("functionDescriptions") or []
        if descriptions:
            result.facts["function_summary"] = descriptions[0]
        synonyms = sorted(
            {syn["label"] for syn in details.get("synonyms") or [] if syn.get("label")}
        )
        if synonyms:
            result.facts["synonym_count"] = len(synonyms)

    record = None
    try:
        record = uniprot_record(ctx.uniprot_id, fetcher)
    except Exception as exc:
        result.caveats.append(f"basic: UniProt unavailable ({exc})")

    if record:
        sequence = record.get("sequence") or {}
        if sequence.get("length"):
            result.facts["protein_length"] = int(sequence["length"])
        protein_name = (
            ((record.get("proteinDescription") or {}).get("recommendedName") or {})
            .get("fullName", {})
            .get("value")
        )
        if protein_name:
            result.facts["protein_name"] = protein_name
        if not result.facts.get("function_summary"):
            function = _uniprot_function(record)
            if function:
                result.facts["function_summary"] = function

    try:
        prediction = alphafold_prediction(ctx.uniprot_id, fetcher)
    except Exception:
        prediction = None
    result.facts["alphafold_available"] = "Yes" if prediction else "No"
    if prediction and prediction.get("globalMetricValue") is not None:
        result.facts["alphafold_mean_plddt"] = round(
            float(prediction["globalMetricValue"]), 1
        )

    if not details and not record:
        return result.degrade("basic: target metadata unavailable")
    return result
```

- [x] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_basic.py -v`
Expected: PASS

---

### Task 4: pathway 分析模块（Reactome/GO + STRING）

**Files:**
- Create: `src/target_profile/analysis/pathway.py`
- Create: `tests/test_pathway.py`

- [x] **Step 1: 写失败测试**

```python
# tests/test_pathway.py
import json

from target_profile.analysis.pathway import analyze_pathway
from target_profile.config import Settings
from target_profile.models import GeneContext


def _settings(tmp_path):
    ensg = tmp_path / "data" / "cache" / "ENSG00000133703"
    ensg.mkdir(parents=True)
    (ensg / "opentargets_pathways.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "pathways": [
                            {"pathwayId": "R-HSA-1", "pathway": "Signalling to RAS", "topLevelTerm": "Signal Transduction"},
                            {"pathwayId": "R-HSA-2", "pathway": "RAF/MAP kinase cascade", "topLevelTerm": "Signal Transduction"},
                            {"pathwayId": "R-HSA-2", "pathway": "RAF/MAP kinase cascade", "topLevelTerm": "Signal Transduction"},
                            {"pathwayId": "R-HSA-3", "pathway": "Oncogene induced senescence", "topLevelTerm": "Cellular Senescence"},
                        ],
                        "geneOntology": [
                            {"aspect": "C", "evidence": "TAS", "term": {"id": "GO:0005886", "label": "plasma membrane"}},
                            {"aspect": "C", "evidence": "IDA", "term": {"id": "GO:0005886", "label": "plasma membrane"}},
                            {"aspect": "P", "evidence": "IEA", "term": {"id": "GO:0007265", "label": "Ras protein signal transduction"}},
                            {"aspect": "F", "evidence": "IEA", "term": {"id": "GO:0003924", "label": "GTPase activity"}},
                        ],
                    }
                }
            }
        )
    )
    gene_dir = tmp_path / "data" / "cache" / "KRAS"
    gene_dir.mkdir(parents=True)
    (gene_dir / "string_partners.json").write_text(
        json.dumps(
            [
                {"preferredName_B": "RAF1", "score": 0.99},
                {"preferredName_B": "PIK3CA", "score": 0.95},
                {"preferredName_B": "RAB1A", "score": 0.6},
            ]
        )
    )
    return Settings(lake_root=tmp_path / "lake", data_root=tmp_path / "data", out_root=tmp_path / "out")


def test_pathway_facts(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703")
    result = analyze_pathway(ctx, _settings(tmp_path), offline=True)
    assert result.status == "ok"
    assert result.facts["n_pathways"] == 3
    assert result.facts["top_level_term"] == "Signal Transduction"
    assert result.facts["n_go_terms"] == 3
    assert result.facts["go_aspect_summary"] == "Cellular component 1 / Molecular function 1 / Biological process 1"
    assert result.facts["n_partners_high_conf"] == 2
    assert result.facts["top_partner"] == "RAF1"
    assert len(result.tables["partners"]) == 2
```

- [x] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_pathway.py -v`
Expected: FAIL

- [x] **Step 3: 实现 pathway 分析**

```python
# src/target_profile/analysis/pathway.py
import pandas as pd

from target_profile.api.cache import CachedFetcher
from target_profile.api.opentargets import target_pathways
from target_profile.api.stringdb import interaction_partners
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult

ASPECT_NAMES = {
    "P": "Biological process",
    "F": "Molecular function",
    "C": "Cellular component",
}


def analyze_pathway(
    ctx: GeneContext,
    settings: Settings,
    offline: bool = True,
    fetcher: CachedFetcher | None = None,
) -> ModuleResult:
    result = ModuleResult(name="pathway")
    fetcher = fetcher or CachedFetcher(settings.data_root / "cache", offline=offline)

    details = None
    try:
        details = target_pathways(ctx.ensembl_id, fetcher)
    except Exception as exc:
        result.caveats.append(f"pathway: Open Targets unavailable ({exc})")

    if details:
        pathways = details.get("pathways") or []
        if pathways:
            frame = pd.DataFrame(pathways).drop_duplicates(subset=["pathwayId"])
            counts = (
                frame["topLevelTerm"]
                .fillna("Other")
                .value_counts()
                .rename_axis("topLevelTerm")
                .reset_index(name="count")
            )
            result.tables["pathways"] = frame.sort_values("topLevelTerm")[
                ["pathwayId", "pathway", "topLevelTerm"]
            ]
            result.tables["top_levels"] = counts
            result.facts["n_pathways"] = int(len(frame))
            result.facts["top_level_term"] = str(counts.iloc[0]["topLevelTerm"])
            result.facts["top_level_terms"] = ", ".join(
                counts.head(3)["topLevelTerm"].astype(str)
            )

        ontology = details.get("geneOntology") or []
        if ontology:
            rows = [
                {
                    "aspect": ASPECT_NAMES.get(item.get("aspect"), item.get("aspect")),
                    "term_id": (item.get("term") or {}).get("id"),
                    "term": (item.get("term") or {}).get("label"),
                    "evidence": item.get("evidence"),
                }
                for item in ontology
            ]
            go_frame = pd.DataFrame(rows).dropna(subset=["term"])
            grouped = (
                go_frame.groupby(["aspect", "term"])
                .size()
                .reset_index(name="evidence_count")
                .sort_values("evidence_count", ascending=False)
            )
            result.tables["go_terms"] = grouped.head(30)
            result.facts["n_go_terms"] = int(go_frame["term"].nunique())
            aspect_counts = (
                go_frame.drop_duplicates(subset=["term"]).groupby("aspect").size()
            )
            result.facts["go_aspect_summary"] = " / ".join(
                f"{name} {int(count)}" for name, count in aspect_counts.items()
            )

    partners = []
    try:
        partners = interaction_partners(ctx.symbol, fetcher)
    except Exception as exc:
        result.caveats.append(f"pathway: STRING unavailable ({exc})")

    if partners:
        frame = pd.DataFrame(partners)
        if {"preferredName_B", "score"} <= set(frame.columns):
            threshold = settings.thresholds.string_min_score
            frame = frame[frame["preferredName_B"] != ctx.symbol]
            frame = frame.drop_duplicates(subset=["preferredName_B"])
            high = frame[frame["score"] >= threshold].sort_values(
                "score", ascending=False
            )
            if not high.empty:
                result.tables["partners"] = high[
                    ["preferredName_B", "score"]
                ].head(30).reset_index(drop=True)
                result.facts["n_partners_high_conf"] = int(len(high))
                result.facts["top_partner"] = str(high.iloc[0]["preferredName_B"])
                result.facts["top_partner_score"] = round(
                    float(high.iloc[0]["score"]), 3
                )

    if not result.tables:
        return result.degrade("pathway: no pathway or interaction data")
    return result
```

- [x] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_pathway.py -v`
Expected: PASS

---

### Task 5: ptm 分析模块（UniProt curated PTM + 结构域）

**Files:**
- Create: `src/target_profile/analysis/ptm.py`
- Create: `tests/test_ptm.py`

- [x] **Step 1: 写失败测试**

```python
# tests/test_ptm.py
import json

from target_profile.analysis.ptm import analyze_ptm
from target_profile.config import Settings
from target_profile.models import GeneContext


def _feature(ftype, start, end, description):
    return {
        "type": ftype,
        "location": {
            "start": {"value": start, "modifier": "EXACT"},
            "end": {"value": end, "modifier": "EXACT"},
        },
        "description": description,
    }


def _settings(tmp_path):
    global_dir = tmp_path / "data" / "cache" / "_global"
    global_dir.mkdir(parents=True)
    (global_dir / "uniprot_P01116.json").write_text(
        json.dumps(
            {
                "sequence": {"length": 189},
                "features": [
                    _feature("Modified residue", 104, 104, "N6-acetyllysine"),
                    _feature("Modified residue", 186, 186, "Cysteine methyl ester"),
                    _feature("Lipidation", 186, 186, "S-farnesyl cysteine"),
                    _feature("Region", 166, 185, "Hypervariable region"),
                    _feature("Binding site", 10, 18, "GTP"),
                ],
            }
        )
    )
    return Settings(lake_root=tmp_path / "lake", data_root=tmp_path / "data", out_root=tmp_path / "out")


def test_ptm_facts(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703", uniprot_id="P01116")
    result = analyze_ptm(ctx, _settings(tmp_path), offline=True)
    assert result.status == "ok"
    assert result.facts["sequence_length"] == 189
    assert result.facts["n_ptm_sites"] == 3
    assert result.facts["top_ptm_type"] == "Modified residue"
    assert result.facts["n_domains"] == 1
    assert result.facts["domain_summary"] == "Hypervariable region (166-185)"
    assert len(result.tables["ptm_sites"]) == 3


def test_ptm_without_uniprot_degrades(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703")
    result = analyze_ptm(ctx, _settings(tmp_path), offline=True)
    assert result.status == "no_data"
```

- [x] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_ptm.py -v`
Expected: FAIL

- [x] **Step 3: 实现 ptm 分析**

```python
# src/target_profile/analysis/ptm.py
import pandas as pd

from target_profile.api.cache import CachedFetcher
from target_profile.api.uniprot import uniprot_record
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult

PTM_TYPES = (
    "Modified residue",
    "Lipidation",
    "Glycosylation",
    "Disulfide bond",
    "Cross-link",
)
REGION_TYPES = (
    "Domain",
    "Region",
    "Zinc finger",
    "Repeat",
    "Coiled coil",
    "Motif",
)


def analyze_ptm(
    ctx: GeneContext,
    settings: Settings,
    offline: bool = True,
    fetcher: CachedFetcher | None = None,
) -> ModuleResult:
    result = ModuleResult(name="ptm")
    if not ctx.uniprot_id:
        return result.degrade("ptm: UniProt ID unavailable")
    fetcher = fetcher or CachedFetcher(settings.data_root / "cache", offline=offline)

    try:
        record = uniprot_record(ctx.uniprot_id, fetcher)
    except Exception as exc:
        return result.degrade(f"ptm: UniProt unavailable ({exc})")
    if not record:
        return result.degrade("ptm: UniProt record unavailable")

    sequence_length = (record.get("sequence") or {}).get("length")
    if sequence_length:
        result.facts["sequence_length"] = int(sequence_length)

    sites: list[dict] = []
    regions: list[dict] = []
    for feature in record.get("features") or []:
        feature_type = feature.get("type")
        location = feature.get("location") or {}
        start = (location.get("start") or {}).get("value")
        end = (location.get("end") or {}).get("value")
        if start is None:
            continue
        if feature_type in PTM_TYPES:
            sites.append(
                {
                    "type": feature_type,
                    "position": int(start),
                    "end": int(end or start),
                    "description": feature.get("description") or "",
                }
            )
        elif feature_type in REGION_TYPES:
            regions.append(
                {
                    "type": feature_type,
                    "name": feature.get("description") or feature_type,
                    "start": int(start),
                    "end": int(end or start),
                }
            )

    if sites:
        site_frame = pd.DataFrame(sites).sort_values(["position", "type"])
        result.tables["ptm_sites"] = site_frame
        counts = (
            site_frame["type"]
            .value_counts()
            .rename_axis("type")
            .reset_index(name="count")
        )
        result.tables["ptm_types"] = counts
        result.facts["n_ptm_sites"] = int(len(site_frame))
        result.facts["ptm_types"] = ", ".join(
            f"{row.type} {row.count}" for row in counts.itertuples()
        )
        result.facts["top_ptm_type"] = str(counts.iloc[0]["type"])

    if regions:
        region_frame = pd.DataFrame(regions).sort_values("start")
        result.tables["domains"] = region_frame
        result.facts["n_domains"] = int(len(region_frame))
        result.facts["domain_summary"] = "; ".join(
            f"{row.name} ({row.start}-{row.end})"
            for row in region_frame.head(3).itertuples()
        )

    if not sites and not regions:
        return result.degrade("ptm: no curated PTM or domain features")
    return result
```

- [x] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_ptm.py -v`
Expected: 2 passed

---

### Task 6: 通路与 PTM 图表

**Files:**
- Modify: `src/target_profile/figures/charts.py`
- Modify: `tests/test_figures.py`

- [x] **Step 1: 写失败测试（在 `tests/test_figures.py` 末尾追加）**

```python
from target_profile.figures.charts import plot_pathway, plot_ptm


def test_pathway_figure(tmp_path):
    r = _result(
        "pathway",
        {
            "top_levels": pd.DataFrame({"topLevelTerm": ["Signal Transduction", "Disease"], "count": [36, 24]}),
            "partners": pd.DataFrame({"preferredName_B": ["RAF1", "PIK3CA"], "score": [0.99, 0.95]}),
        },
    )
    paths = plot_pathway(r, tmp_path)
    assert len(paths) == 1
    assert paths[0].exists() and paths[0].stat().st_size > 0


def test_ptm_figure(tmp_path):
    r = _result(
        "ptm",
        {
            "ptm_types": pd.DataFrame({"type": ["Modified residue", "Lipidation"], "count": [2, 1]}),
            "ptm_sites": pd.DataFrame(
                {
                    "type": ["Modified residue", "Modified residue", "Lipidation"],
                    "position": [104, 186, 186],
                    "end": [104, 186, 186],
                    "description": ["N6-acetyllysine", "Cysteine methyl ester", "S-farnesyl cysteine"],
                }
            ),
            "domains": pd.DataFrame(
                {"type": ["Region"], "name": ["Hypervariable region"], "start": [166], "end": [185]}
            ),
        },
        {"sequence_length": 189},
    )
    paths = plot_ptm(r, tmp_path)
    assert len(paths) == 1
    assert paths[0].exists() and paths[0].stat().st_size > 0
```

- [x] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_figures.py -v`
Expected: FAIL（`plot_pathway` / `plot_ptm` 未定义）

- [x] **Step 3: 实现两组图（追加到 `figures/charts.py`）**

```python
def plot_pathway(result: ModuleResult, out_dir: Path) -> list[Path]:
    apply_theme()
    fig, axes = plt.subplots(1, 2, figsize=(16.5 / 2.54, 6 / 2.54 * 1.6))
    levels = result.tables.get("top_levels")
    if levels is not None and not levels.empty:
        top = levels.head(10).iloc[::-1]
        axes[0].barh(top["topLevelTerm"], top["count"], color=PALETTE[4])
        axes[0].set_title("Reactome top-level pathways")
        axes[0].set_xlabel("Pathway count")
        axes[0].tick_params(labelsize=6)
    else:
        axes[0].text(0.5, 0.5, "No pathway data", ha="center", va="center")
        axes[0].set_axis_off()

    partners = result.tables.get("partners")
    if partners is not None and not partners.empty:
        top_partners = partners.head(15).iloc[::-1]
        axes[1].barh(top_partners["preferredName_B"], top_partners["score"], color=PALETTE[1])
        axes[1].set_title("STRING interaction partners")
        axes[1].set_xlabel("Combined score")
        axes[1].set_xlim(0, 1)
        axes[1].tick_params(labelsize=6)
    else:
        axes[1].text(0.5, 0.5, "No partner data", ha="center", va="center")
        axes[1].set_axis_off()

    fig.tight_layout()
    return [save(fig, out_dir, "pathway")]


def plot_ptm(result: ModuleResult, out_dir: Path) -> list[Path]:
    apply_theme()
    fig, axes = plt.subplots(1, 2, figsize=(16.5 / 2.54, 6 / 2.54 * 1.6))
    types = result.tables.get("ptm_types")
    if types is not None and not types.empty:
        top_types = types.iloc[::-1]
        axes[0].barh(top_types["type"], top_types["count"], color=PALETTE[3])
        axes[0].set_title("Curated PTM types")
        axes[0].set_xlabel("Site count")
        axes[0].tick_params(labelsize=6)
    else:
        axes[0].text(0.5, 0.5, "No PTM data", ha="center", va="center")
        axes[0].set_axis_off()

    sites = result.tables.get("ptm_sites")
    if sites is not None and not sites.empty:
        domains = result.tables.get("domains")
        if domains is not None and not domains.empty:
            for _, domain in domains.iterrows():
                axes[1].axvspan(domain["start"], domain["end"], color="#e2e8f0", zorder=0)
        categories = list(dict.fromkeys(sites["type"]))
        for index, category in enumerate(categories):
            subset = sites[sites["type"] == category]
            axes[1].scatter(
                subset["position"],
                [index] * len(subset),
                color=PALETTE[index % len(PALETTE)],
                s=28,
                zorder=3,
            )
        axes[1].set_yticks(range(len(categories)), categories)
        axes[1].set_ylim(-0.6, len(categories) - 0.4)
        sequence_length = result.facts.get("sequence_length") or int(sites["end"].max())
        axes[1].set_xlim(0, int(sequence_length) + 2)
        axes[1].set_xlabel("Residue position")
        axes[1].set_title("Curated PTM sites (shaded: regions)")
        axes[1].tick_params(labelsize=6)
    else:
        axes[1].text(0.5, 0.5, "No PTM sites", ha="center", va="center")
        axes[1].set_axis_off()

    fig.tight_layout()
    return [save(fig, out_dir, "ptm")]
```

- [x] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_figures.py -v`
Expected: 5 passed

---

### Task 7: 报告标签、章节标题与页脚

**Files:**
- Modify: `src/target_profile/report/render.py`
- Modify: `src/target_profile/report/templates/report.html.j2`
- Modify: `tests/test_render.py`

- [x] **Step 1: 写失败测试（追加到 `tests/test_render.py`）**

```python
def test_render_basic_section_title(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703")
    r = ModuleResult(
        name="basic",
        facts={"protein_length": 189, "target_class": "Enzyme / Hydrolase"},
    )
    html_path, _ = render_report(ctx, [r], tmp_path / "out")
    html = html_path.read_text(encoding="utf-8")
    assert "基因与蛋白基础" in html
    assert "蛋白长度 (aa)" in html
    assert "靶点类别" in html
```

- [x] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_render.py::test_render_basic_section_title -v`
Expected: FAIL（标题显示为 `basic`、标签显示原始 key）

- [x] **Step 3: 扩充映射与页脚**

`render.py` 的 `FACT_LABELS` 增加以下条目：

```python
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
```

`SECTION_TITLES` 增加：

```python
    "basic": "基因与蛋白基础",
    "pathway": "通路与相互作用",
    "ptm": "蛋白修饰",
```

`report.html.j2` 页脚整段替换为：

```html
<footer>
  <p>数据来源：GTEx v8、DepMap、HPA、cBioPortal TCGA PanCancer Atlas、Open Targets（Reactome/GO）、STRING、UniProt、AlphaFold DB。仅供科研参考，不构成临床诊疗建议。</p>
</footer>
```

- [x] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_render.py -v`
Expected: 2 passed

---

### Task 8: CLI 接线与 fetch 预热

**Files:**
- Modify: `src/target_profile/cli.py`
- Modify: `src/target_profile/api/cbioportal.py`
- Modify: `tests/test_cli_run.py`

- [x] **Step 1: 写失败测试（追加到 `tests/test_cli_run.py`）**

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
        "expression",
        "mutation",
        "dependency",
        "pathway",
        "ptm",
    }
```

- [x] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_cli_run.py::test_run_offline_declares_new_sections -v`
Expected: FAIL（modules 只有 3 个）

- [x] **Step 3: 接线 CLI 与 refresh 透传**

`src/target_profile/analysis/...` 无需改。修改 `cli.py`：

导入区增加：

```python
from target_profile.analysis.basic import analyze_basic
from target_profile.analysis.pathway import analyze_pathway
from target_profile.analysis.ptm import analyze_ptm
from target_profile.api.alphafold import alphafold_prediction
from target_profile.api.opentargets import target_basic, target_details, target_pathways
from target_profile.api.stringdb import interaction_partners
from target_profile.api.uniprot import uniprot_record
```

模块与绘图注册：

```python
MODULES = [
    analyze_basic,
    analyze_expression,
    analyze_mutation,
    analyze_dependency,
    analyze_pathway,
    analyze_ptm,
]
PLOTTERS = {
    "expression": plot_expression,
    "mutation": plot_mutation,
    "dependency": plot_dependency,
    "pathway": plot_pathway,
    "ptm": plot_ptm,
}
```

`plot_*` 导入改为：

```python
from target_profile.figures.charts import (
    plot_dependency,
    plot_expression,
    plot_mutation,
    plot_pathway,
    plot_ptm,
)
```

`fetch` 函数体替换为：

```python
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
    for label, action in steps:
        try:
            action()
            typer.echo(f"cached: {label}")
        except Exception as exc:
            typer.echo(f"warning: {label} failed: {exc}", err=True)
    typer.echo(f"cached gene: {ctx.symbol}")
```

`api/cbioportal.py` 的 `fetch_pancan_mutations` 增加 `refresh: bool = False` 参数，并把 `refresh=refresh` 传给三次 `request_json` 调用（studies、sample-lists、mutations）。

- [x] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_cli_run.py -v`
Expected: 3 passed

---

### Task 9: 集成测试扩展

**Files:**
- Modify: `tests/integration/test_vertical_slice.py`

- [x] **Step 1: 扩展 fixture 并添加断言**

在 `_build_home` 中，写完 bCbioPortal 缓存后，为两个基因追加以下缓存（放在 `return home` 之前）：

```python
    for gene, ensg, acc in [
        ("KRAS", "ENSG00000133703", "P01116"),
        ("TP53", "ENSG00000141510", "P04637"),
    ]:
        ensg_dir = home / "data" / "cache" / ensg
        ensg_dir.mkdir(parents=True)
        (ensg_dir / "opentargets_target.json").write_text(
            json.dumps(
                {
                    "data": {
                        "target": {
                            "id": ensg,
                            "proteinIds": [{"id": acc, "source": "uniprot_swissprot"}],
                        }
                    }
                }
            )
        )
        (ensg_dir / "opentargets_basic.json").write_text(
            json.dumps(
                {
                    "data": {
                        "target": {
                            "approvedName": gene,
                            "targetClass": [{"label": "Enzyme"}],
                            "subcellularLocations": [{"location": "Cytoplasm"}],
                            "synonyms": [{"label": gene}],
                        }
                    }
                }
            )
        )
        (ensg_dir / "opentargets_pathways.json").write_text(
            json.dumps(
                {
                    "data": {
                        "target": {
                            "pathways": [
                                {"pathwayId": "R-HSA-1", "pathway": "Signalling to RAS", "topLevelTerm": "Signal Transduction"}
                            ],
                            "geneOntology": [
                                {"aspect": "C", "evidence": "TAS", "term": {"id": "GO:0005886", "label": "plasma membrane"}}
                            ],
                        }
                    }
                }
            )
        )
        (home / "data" / "cache" / gene / "string_partners.json").write_text(
            json.dumps([{"preferredName_B": "RAF1", "score": 0.99}])
        )
        global_dir = home / "data" / "cache" / "_global"
        global_dir.mkdir(parents=True, exist_ok=True)
        (global_dir / f"uniprot_{acc}.json").write_text(
            json.dumps(
                {
                    "sequence": {"length": 189},
                    "proteinDescription": {"recommendedName": {"fullName": {"value": gene}}},
                    "comments": [],
                    "features": [
                        {
                            "type": "Modified residue",
                            "location": {
                                "start": {"value": 10, "modifier": "EXACT"},
                                "end": {"value": 10, "modifier": "EXACT"},
                            },
                            "description": "N6-acetyllysine",
                        }
                    ],
                }
            )
        )
        (global_dir / f"alphafold_{acc}.json").write_text(
            json.dumps([{"globalMetricValue": 90.0}])
        )
```

断言追加：

```python
        assert facts["modules"]["basic"]["status"] == "ok"
        assert facts["modules"]["pathway"]["status"] == "ok"
        assert facts["modules"]["ptm"]["status"] == "ok"
```

注意：`opentargets_basic/pathways` 的缓存目录是 Ensembl（与 M2 的 `opentargets_target` 一致），STRING 是基因符号目录，UniProt/AlphaFold 在 `_global`。

- [x] **Step 2: 运行确认通过**

Run: `uv run pytest tests/integration/test_vertical_slice.py -v`
Expected: PASS

- [x] **Step 3: 全量测试**

Run: `uv run pytest -q`
Expected: 全部通过（约 40 个用例）

---

### Task 10: 真实数据验收（KRAS / TP53）

**Files:** 无（仅运行命令与检查）

- [x] **Step 1: 预热新缓存**

Run:
```bash
uv run target-profile fetch KRAS
uv run target-profile fetch TP53
```
Expected：输出含 `cached: Open Targets basic`、`cached: Open Targets pathways`、`cached: STRING partners`、`cached: UniProt record`、`cached: AlphaFold prediction`、`cached: cBioPortal TCGA mutations`。

- [x] **Step 2: 离线生成 KRAS 报告**

Run:
```bash
uv run target-profile run KRAS --offline --no-llm --format both --force
```
Expected：`report.html`、`report.pdf`、`facts.json` 生成；`facts.json` 中：
- `modules.basic.facts.protein_length == 189`
- `modules.basic.facts.target_class` 含 `Enzyme` 与 `Hydrolase`
- `modules.basic.facts.alphafold_available == "Yes"`
- `modules.pathway.facts.n_pathways == 71`（容差 ±3）
- `modules.pathway.facts.top_level_term == "Signal Transduction"`
- `modules.pathway.facts.top_partner` 属于 {PIK3CA, EGFR, RAF1, SOS1} 之一且 `top_partner_score >= 0.99`
- `modules.ptm.facts.n_ptm_sites >= 8`，`ptm_types` 含 `Lipidation`

检查命令：
```bash
uv run python -c "
import json
f=json.load(open('out/KRAS_20261030/facts.json'))
for m in ('basic','pathway','ptm'):
    print(m, f['modules'][m]['status'], f['modules'][m]['facts'])
"
```

- [x] **Step 3: 离线生成 TP53 报告**

Run:
```bash
uv run target-profile run TP53 --offline --no-llm --format html --force
```
Expected：成功；`modules.basic.facts.protein_length == 393`；`modules.ptm.facts.n_ptm_sites > 0`；若 STRING/OT 缓存缺失，对应章节显示"暂无可用数据"且 `run.log` 有警告，但退出码为 0。

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
    page.screenshot(path="out/KRAS_20261030/preview_basic.png")
    browser.close()
EOF
```
Expected：中文正文与英文图表标签正常，基础/通路/PTM 章节图可见。

---

## 里程碑对照

- **M3**：Task 1–10（基础/通路/PTM 三个模块 + 图表 + 报告 + CLI + 验收）
- 后续 **M4**：disease / tractability / safety（Tier1）
- 后续 **M5**：cancer / comparative / summary / LLM 润色 + 12 章结构

## 已知限制（M3 范围）

- PTM 只覆盖 UniProt curated features；不做激酶-底物推断（无商用安全源）
- 结构域来自 UniProt 注释（Domain/Region/Zinc finger/Repeat/Coiled coil/Motif），不引入 InterPro API
- STRING 仅存 combined score ≥ 0.7（700/1000）的伙伴；`fetch` 缓存的是 Top 100 原始响应。实测 KRAS 前 100 名全部 ≥0.7，故 `n_partners_high_conf` 上限为 100
- GO/Reactome 数据来自 Open Targets target 查询，不做本体层级展开
- 无 Disease/Tractability/Safety 章节（M4）
