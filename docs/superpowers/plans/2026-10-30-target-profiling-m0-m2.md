# Target Profiling M0–M2（垂直切片）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 打通"基因解析 → 数据准备/缓存 → 表达/突变/依赖分析 → 图表 → 自包含 HTML → PDF"最小全链路，用 KRAS/TP53 验收。

**Architecture:** 复用 Biomni data lake 的本地数据（GTEx、DepMap、HPA、gene_info），lake 未覆盖的源（cBioPortal TCGA、Open Targets、UniProt）走 API 并按基因缓存。分析模块输出结构化 `ModuleResult`，图表只消费该结果，Jinja2 渲染单文件 HTML，Playwright 打印 PDF。

**Tech Stack:** Python 3.13、uv、DuckDB、pandas/pyarrow、matplotlib、Jinja2、Typer、Pydantic、httpx、Playwright、pytest。

**约束：** 用户要求暂不使用 git，本计划不含 commit 步骤。项目根目录 `/root/target_profiling`。参考项目 `/root/Biomni/Biomni/KRAS_profiling`（只读参考，不修改）。

---

## 全局约定

- 所有命令在 `/root/target_profiling` 下执行，Python 一律用 `.venv/bin/python` 或 `uv run`。
- Python 3.13；依赖用 uv 安装到项目 `.venv`，不使用全局 pip。
- 数据根：`data/`；lake 根：`/root/Biomni/Biomni/data/biomni_data/data_lake`（可在 `config/settings.toml` 覆盖）。
- API 缓存：`data/cache/<GENE>/<name>.json`；lake 派生数据：`data/parquet/*.parquet`。
- 报告产物：`out/<SYMBOL>_<YYYYMMDD>/`。
- 测试全程离线；真实网络只在手工验收步骤使用。

---

### Task 1: 项目骨架与 version 命令

**Files:**
- Create: `pyproject.toml`
- Create: `src/target_profile/__init__.py`
- Create: `src/target_profile/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_cli.py
from typer.testing import CliRunner

from target_profile.cli import app


def test_version_command():
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert "target-profile 0.1.0" in result.output
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_cli.py::test_version_command -v`
Expected: FAIL（`target_profile.cli` 不存在）

- [ ] **Step 3: 写 pyproject 与最小 CLI**

```toml
# pyproject.toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "target-profile"
version = "0.1.0"
description = "Single-gene target profiling report generator"
requires-python = ">=3.13"
dependencies = [
  "duckdb>=1.1",
  "pandas>=2.2",
  "pyarrow>=17.0",
  "matplotlib>=3.9",
  "jinja2>=3.1",
  "typer>=0.12",
  "pydantic>=2.8",
  "pyyaml>=6.0",
  "httpx>=0.27",
  "playwright>=1.47",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "pytest-mock>=3.14"]

[project.scripts]
target-profile = "target_profile.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["src/target_profile"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = "-q"
```

```python
# src/target_profile/__init__.py
__version__ = "0.1.0"
```

```python
# src/target_profile/cli.py
import typer

from target_profile import __version__

app = typer.Typer(no_args_is_help=True, help="Single-gene target profiling")


@app.command()
def version() -> None:
    """Show version."""
    typer.echo(f"target-profile {__version__}")
```

- [ ] **Step 4: 创建 venv 并安装**

Run:
```bash
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/test_cli.py::test_version_command -v`
Expected: PASS

---

### Task 2: 配置、错误类型与结构化模型

**Files:**
- Create: `config/settings.toml`
- Create: `config/licenses.yaml`
- Create: `src/target_profile/errors.py`
- Create: `src/target_profile/models.py`
- Create: `src/target_profile/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_config.py
from pathlib import Path

from target_profile.config import load_settings


def test_load_settings_resolves_relative_paths(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/settings.toml").write_text(
        'lake_root = "/lake"\ndata_root = "local_data"\nout_root = "local_out"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGET_PROFILE_HOME", str(tmp_path))

    settings = load_settings()

    assert settings.lake_root == Path("/lake")
    assert settings.data_root == tmp_path / "local_data"
    assert settings.out_root == tmp_path / "local_out"
    assert settings.thresholds.strong_dependency_effect == -0.5
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL（`target_profile.config` 不存在）

- [ ] **Step 3: 写配置与模型**

```python
# src/target_profile/errors.py
class TargetProfileError(Exception):
    """Base error for target profiling."""


class GeneNotFound(TargetProfileError):
    """Gene identifier could not be resolved."""


class DataMissing(TargetProfileError):
    """Required local data file is missing or unreadable."""


class OfflineCacheMiss(TargetProfileError):
    """Offline mode requested but the API response is not cached."""
```

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


@dataclass
class ModuleResult:
    name: str
    status: Literal["ok", "no_data"] = "ok"
    facts: dict[str, Any] = field(default_factory=dict)
    tables: dict[str, Any] = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)
    figure_paths: list[Path] = field(default_factory=list)

    def degrade(self, reason: str) -> "ModuleResult":
        self.status = "no_data"
        self.caveats.append(reason)
        return self
```

```python
# src/target_profile/config.py
import os
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field


class Thresholds(BaseModel):
    tissue_specific_tau: float = 0.9
    tissue_partial_tau: float = 0.6
    pan_cancer_hotspot_pct: float = 5.0
    strong_dependency_effect: float = -0.5
    loeuf_constrained: float = 0.6


class LLMSettings(BaseModel):
    enabled: bool = False
    base_url: str = "https://api.openai.com/v1"
    model: str = ""
    api_key_env: str = "TARGET_PROFILE_LLM_API_KEY"


class Settings(BaseModel):
    lake_root: Path
    data_root: Path
    out_root: Path
    thresholds: Thresholds = Field(default_factory=Thresholds)
    llm: LLMSettings = Field(default_factory=LLMSettings)


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def load_settings(config_path: Path | None = None) -> Settings:
    root = Path(os.environ.get("TARGET_PROFILE_HOME", Path.cwd()))
    path = config_path or root / "config/settings.toml"
    raw: dict = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    raw.setdefault("lake_root", "/root/Biomni/Biomni/data/biomni_data/data_lake")
    raw.setdefault("data_root", "data")
    raw.setdefault("out_root", "out")
    raw["lake_root"] = _resolve(root, raw["lake_root"])
    raw["data_root"] = _resolve(root, raw["data_root"])
    raw["out_root"] = _resolve(root, raw["out_root"])
    return Settings(**raw)
```

```toml
# config/settings.toml
lake_root = "/root/Biomni/Biomni/data/biomni_data/data_lake"
data_root = "data"
out_root = "out"

[thresholds]
tissue_specific_tau = 0.9
tissue_partial_tau = 0.6
pan_cancer_hotspot_pct = 5.0
strong_dependency_effect = -0.5
loeuf_constrained = 0.6

[llm]
enabled = false
base_url = "https://api.openai.com/v1"
model = ""
api_key_env = "TARGET_PROFILE_LLM_API_KEY"
```

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
not_for_delivery:
  - DisGeNET
  - OMIM
  - MSigDB
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS

---

### Task 3: manifest 与 lake 数据派生

**Files:**
- Create: `src/target_profile/data_prep/__init__.py`
- Create: `src/target_profile/data_prep/manifest.py`
- Create: `src/target_profile/data_prep/lake.py`
- Create: `tests/test_lake.py`

- [ ] **Step 1: 写失败测试（用小样本 CSV/parquet 模拟 lake）**

```python
# tests/test_lake.py
import json

import pandas as pd

from target_profile.config import Settings
from target_profile.data_prep.lake import derive_all


def test_derive_all_writes_parquet_and_manifest(tmp_path):
    lake = tmp_path / "lake"
    lake.mkdir()
    pd.DataFrame(
        {
            "Unnamed: 0": ["ACH-1"],
            "KRAS (3845)": [-1.2],
            "TP53 (7157)": [-0.1],
        }
    ).to_csv(lake / "DepMap_CRISPRGeneEffect.csv", index=False)
    pd.DataFrame(
        {
            "ModelID": ["ACH-1"],
            "CellLineName": ["LINE1"],
            "OncotreeLineage": ["Lung"],
            "OncotreePrimaryDisease": ["Lung Adenocarcinoma"],
        }
    ).to_csv(lake / "DepMap_Model.csv", index=False)
    pd.DataFrame({"Unnamed: 0": ["ACH-1"], "KRAS (3845)": [5.0]}).to_csv(
        lake / "DepMap_OmicsExpressionProteinCodingGenesTPMLogp1.csv", index=False
    )
    pd.DataFrame(
        {
            "Description": ["ENSG1"],
            "Tissue": ["Lung"],
            "Expression": [10.0],
            "Gene": ["KRAS"],
        }
    ).to_parquet(lake / "gtex_tissue_gene_tpm.parquet", index=False)
    pd.DataFrame({"Gene": ["KRAS"], "Uniprot": ["P01116"]}).to_csv(
        lake / "proteinatlas.tsv", sep="\t", index=False
    )
    pd.DataFrame(
        {
            "gene_id": ["ENSG00000133703"],
            "gene_name": ["KRAS"],
            "chr": ["12"],
            "gene_start": [25205246],
            "gene_end": [25250936],
            "gene_type": ["protein_coding"],
        }
    ).to_parquet(lake / "gene_info.parquet", index=False)

    settings = Settings(
        lake_root=lake,
        data_root=tmp_path / "data",
        out_root=tmp_path / "out",
    )
    entries = derive_all(settings)

    assert {e.name for e in entries} == {
        "depmap_gene_effect",
        "depmap_expression",
        "depmap_model",
        "gtex",
        "hpa",
        "gene_info",
    }
    for entry in entries:
        assert (tmp_path / "data" / "parquet" / f"{entry.name}.parquet").exists()
    manifest = json.loads((tmp_path / "data" / "manifest.json").read_text())
    assert len(manifest["sources"]) == 6
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_lake.py -v`
Expected: FAIL（`target_profile.data_prep.lake` 不存在）

- [ ] **Step 3: 实现 manifest 与派生**

```python
# src/target_profile/data_prep/__init__.py
"""Data preparation from local Biomni data lake."""
```

```python
# src/target_profile/data_prep/manifest.py
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SourceEntry(BaseModel):
    name: str
    path: str
    version: str
    license: str
    fetched_at: str
    sha256: str
    rows: int | None = None
    note: str = ""


class Manifest(BaseModel):
    generated_at: str = Field(default_factory=now_iso)
    sources: list[SourceEntry] = Field(default_factory=list)


def write_manifest(entries: list[SourceEntry], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(sources=entries)
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
```

```python
# src/target_profile/data_prep/lake.py
from pathlib import Path

import pandas as pd

from target_profile.config import Settings
from target_profile.data_prep.manifest import SourceEntry, now_iso, sha256_file, write_manifest

LICENSE = "CC BY 4.0"


def _out(settings: Settings, name: str) -> Path:
    path = settings.data_root / "parquet" / f"{name}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _entry(name: str, path: Path, version: str, rows: int) -> SourceEntry:
    return SourceEntry(
        name=name,
        path=str(path),
        version=version,
        license=LICENSE,
        fetched_at=now_iso(),
        sha256=sha256_file(path),
        rows=rows,
    )


def derive_gtex(settings: Settings) -> SourceEntry:
    src = settings.lake_root / "gtex_tissue_gene_tpm.parquet"
    df = pd.read_parquet(src)
    out = _out(settings, "gtex")
    df.to_parquet(out, index=False)
    return _entry("gtex", out, "GTEx v8 (Biomni lake)", len(df))


def derive_depmap_gene_effect(settings: Settings) -> SourceEntry:
    src = settings.lake_root / "DepMap_CRISPRGeneEffect.csv"
    df = pd.read_csv(src, low_memory=False).rename(columns={"Unnamed: 0": "ModelID"})
    value_cols = [c for c in df.columns if c != "ModelID"]
    df[value_cols] = df[value_cols].astype("float32")
    out = _out(settings, "depmap_gene_effect")
    df.to_parquet(out, index=False)
    return _entry("depmap_gene_effect", out, "DepMap CRISPR/Chronos (Biomni lake)", len(df))


def derive_depmap_expression(settings: Settings) -> SourceEntry:
    src = settings.lake_root / "DepMap_OmicsExpressionProteinCodingGenesTPMLogp1.csv"
    df = pd.read_csv(src, low_memory=False).rename(columns={"Unnamed: 0": "ModelID"})
    value_cols = [c for c in df.columns if c != "ModelID"]
    df[value_cols] = df[value_cols].astype("float32")
    out = _out(settings, "depmap_expression")
    df.to_parquet(out, index=False)
    return _entry("depmap_expression", out, "DepMap CCLE expression (Biomni lake)", len(df))


def derive_depmap_model(settings: Settings) -> SourceEntry:
    src = settings.lake_root / "DepMap_Model.csv"
    df = pd.read_csv(src, low_memory=False)
    out = _out(settings, "depmap_model")
    df.to_parquet(out, index=False)
    return _entry("depmap_model", out, "DepMap Model (Biomni lake)", len(df))


def derive_hpa(settings: Settings) -> SourceEntry:
    src = settings.lake_root / "proteinatlas.tsv"
    df = pd.read_csv(src, sep="\t", low_memory=False)
    out = _out(settings, "hpa")
    df.to_parquet(out, index=False)
    return _entry("hpa", out, "Human Protein Atlas (Biomni lake)", len(df))


def derive_gene_info(settings: Settings) -> SourceEntry:
    src = settings.lake_root / "gene_info.parquet"
    df = pd.read_parquet(src)
    out = _out(settings, "gene_info")
    df.to_parquet(out, index=False)
    return _entry("gene_info", out, "Ensembl gene_info (Biomni lake)", len(df))


DERIVERS = {
    "gtex": derive_gtex,
    "depmap_gene_effect": derive_depmap_gene_effect,
    "depmap_expression": derive_depmap_expression,
    "depmap_model": derive_depmap_model,
    "hpa": derive_hpa,
    "gene_info": derive_gene_info,
}


def derive_all(settings: Settings) -> list[SourceEntry]:
    entries = [fn(settings) for fn in DERIVERS.values()]
    write_manifest(entries, settings.data_root / "manifest.json")
    return entries
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_lake.py -v`
Expected: PASS

---

### Task 4: API 缓存客户端（缓存优先 + offline）

**Files:**
- Create: `src/target_profile/api/__init__.py`
- Create: `src/target_profile/api/cache.py`
- Create: `tests/test_cache.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_cache.py
import json

import pytest

from target_profile.api.cache import CachedFetcher
from target_profile.errors import OfflineCacheMiss


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def request(self, method, url, params=None, json=None):
        self.calls += 1
        return FakeResponse(self.payload)


def test_cache_hit_avoids_network(tmp_path):
    fetcher = CachedFetcher(tmp_path, offline=False, client=FakeClient({"ok": 1}))
    first = fetcher.request_json("t", "GET", "https://example.org/x", gene="KRAS")
    second = fetcher.request_json("t", "GET", "https://example.org/x", gene="KRAS")
    assert first == second == {"ok": 1}
    assert fetcher.client.calls == 1
    assert json.loads((tmp_path / "KRAS" / "t.json").read_text()) == {"ok": 1}


def test_offline_miss_raises(tmp_path):
    fetcher = CachedFetcher(tmp_path, offline=True, client=FakeClient({"ok": 1}))
    with pytest.raises(OfflineCacheMiss):
        fetcher.request_json("t", "GET", "https://example.org/x", gene="KRAS")


def test_refresh_forces_network(tmp_path):
    client = FakeClient({"ok": 2})
    fetcher = CachedFetcher(tmp_path, offline=False, client=client)
    fetcher.request_json("t", "GET", "https://example.org/x", gene="KRAS")
    fetcher.request_json("t", "GET", "https://example.org/x", gene="KRAS", refresh=True)
    assert client.calls == 2
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_cache.py -v`
Expected: FAIL（`target_profile.api.cache` 不存在）

- [ ] **Step 3: 实现缓存客户端**

```python
# src/target_profile/api/__init__.py
"""External API adapters with per-gene caching."""
```

```python
# src/target_profile/api/cache.py
import json
from pathlib import Path
from typing import Any

import httpx

from target_profile.data_prep.manifest import now_iso
from target_profile.errors import OfflineCacheMiss


class CachedFetcher:
    """Cache-first JSON fetcher. Cache path: <cache_dir>/<gene>/<name>.json."""

    def __init__(
        self,
        cache_dir: Path,
        offline: bool = False,
        client: Any | None = None,
        timeout: float = 90.0,
    ) -> None:
        self.cache_dir = cache_dir
        self.offline = offline
        self.client = client or httpx.Client(timeout=timeout)

    def _path(self, gene: str, name: str) -> Path:
        safe = name.replace("/", "_").replace(" ", "_")
        return self.cache_dir / gene / f"{safe}.json"

    def request_json(
        self,
        name: str,
        method: str,
        url: str,
        gene: str,
        params: dict | None = None,
        json_body: dict | None = None,
        refresh: bool = False,
    ) -> Any:
        path = self._path(gene, name)
        if path.exists() and not refresh:
            return json.loads(path.read_text(encoding="utf-8"))
        if self.offline:
            raise OfflineCacheMiss(f"offline: missing cache {path}")
        response = self.client.request(method, url, params=params, json=json_body)
        response.raise_for_status()
        payload = response.json()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        meta = path.with_suffix(".meta.json")
        meta.write_text(
            json.dumps(
                {"url": url, "method": method, "fetched_at": now_iso()},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return payload
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_cache.py -v`
Expected: PASS

---

### Task 5: 基因解析（symbol / Ensembl / 别名 / UniProt）

**Files:**
- Create: `src/target_profile/api/opentargets.py`
- Create: `src/target_profile/gene_resolve.py`
- Create: `tests/test_gene_resolve.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_gene_resolve.py
import pandas as pd
import pytest

from target_profile.api.cache import CachedFetcher
from target_profile.config import Settings
from target_profile.errors import GeneNotFound
from target_profile.gene_resolve import resolve_gene


class FakeClient:
    def __init__(self, payloads):
        self.payloads = payloads

    def request(self, method, url, params=None, json=None):
        for key, payload in self.payloads.items():
            if key in url or (json and key in str(json)):
                return FakeResponse(payload)
        return FakeResponse({})


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def _settings(tmp_path):
    data = tmp_path / "data" / "parquet"
    data.mkdir(parents=True)
    pd.DataFrame(
        {
            "gene_id": ["ENSG00000133703"],
            "gene_name": ["KRAS"],
            "chr": ["12"],
            "gene_start": [25205246],
            "gene_end": [25250936],
            "gene_type": ["protein_coding"],
        }
    ).to_parquet(data / "gene_info.parquet", index=False)
    pd.DataFrame({"ModelID": ["ACH-1"], "KRAS (3845)": [-1.0]}).to_parquet(
        data / "depmap_gene_effect.parquet", index=False
    )
    return Settings(lake_root=tmp_path / "lake", data_root=tmp_path / "data", out_root=tmp_path / "out")


def test_resolve_symbol(tmp_path):
    ctx = resolve_gene("KRAS", _settings(tmp_path), offline=True)
    assert ctx.symbol == "KRAS"
    assert ctx.ensembl_id == "ENSG00000133703"
    assert ctx.entrez_id == "3845"


def test_resolve_ensembl(tmp_path):
    ctx = resolve_gene("ENSG00000133703", _settings(tmp_path), offline=True)
    assert ctx.symbol == "KRAS"


def test_unknown_gene_raises(tmp_path):
    with pytest.raises(GeneNotFound):
        resolve_gene("NOTAGENE", _settings(tmp_path), offline=True)


def test_alias_uses_ot_cache(tmp_path):
    settings = _settings(tmp_path)
    (settings.data_root / "cache" / "_global").mkdir(parents=True)
    (settings.data_root / "cache" / "_global" / "opentargets_search_K-RAS.json").write_text(
        '{"data": {"search": {"hits": [{"id": "ENSG00000133703", "name": "KRAS"}]}}}'
    )
    fetcher = CachedFetcher(settings.data_root / "cache", offline=True)
    ctx = resolve_gene("K-RAS", settings, offline=True, fetcher=fetcher)
    assert ctx.symbol == "KRAS"
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_gene_resolve.py -v`
Expected: FAIL（`target_profile.gene_resolve` 不存在）

- [ ] **Step 3: 实现 OT 适配器与解析器**

```python
# src/target_profile/api/opentargets.py
from typing import Any

from target_profile.api.cache import CachedFetcher

OT_URL = "https://api.platform.opentargets.org/api/v4/graphql"

SEARCH_QUERY = """
query Search($q: String!) {
  search(queryString: $q, entityNames: ["target"]) {
    hits { id name entity }
  }
}
"""

TARGET_QUERY = """
query Target($id: String!) {
  target(ensemblId: $id) {
    id
    approvedSymbol
    biotype
    genomicLocation { chromosome start end }
    proteinIds { id source }
    dbXrefs { id source }
  }
}
"""


def search_targets(query: str, fetcher: CachedFetcher) -> list[dict[str, Any]]:
    payload = fetcher.request_json(
        f"opentargets_search_{query}",
        "POST",
        OT_URL,
        gene="_global",
        json_body={"query": SEARCH_QUERY, "variables": {"q": query}},
    )
    return payload.get("data", {}).get("search", {}).get("hits", [])


def target_details(ensembl_id: str, fetcher: CachedFetcher) -> dict[str, Any] | None:
    payload = fetcher.request_json(
        "opentargets_target",
        "POST",
        OT_URL,
        gene=ensembl_id,
        json_body={"query": TARGET_QUERY, "variables": {"id": ensembl_id}},
    )
    return payload.get("data", {}).get("target")
```

```python
# src/target_profile/gene_resolve.py
import difflib

import pandas as pd
import pyarrow.parquet as pq

from target_profile.api.cache import CachedFetcher
from target_profile.api.opentargets import search_targets, target_details
from target_profile.config import Settings
from target_profile.errors import DataMissing, GeneNotFound
from target_profile.models import GeneContext

UNIPROT_URL = "https://rest.uniprot.org/uniprotkb/{acc}.json"


def _gene_info(settings: Settings) -> pd.DataFrame:
    path = settings.data_root / "parquet" / "gene_info.parquet"
    if not path.exists():
        raise DataMissing(f"missing local data: {path}; run `target-profile data`")
    return pd.read_parquet(path)


def _entrez_from_depmap(settings: Settings, symbol: str) -> str | None:
    path = settings.data_root / "parquet" / "depmap_gene_effect.parquet"
    if not path.exists():
        return None
    names = pq.read_schema(path).names
    for column in names:
        if column.startswith(f"{symbol} (") and column.endswith(")"):
            return column[column.rfind("(") + 1 : -1]
    return None


def _row_to_context(row: pd.Series, settings: Settings, fetcher: CachedFetcher) -> GeneContext:
    symbol = str(row["gene_name"])
    ensembl = str(row["gene_id"])
    uniprot = None
    try:
        details = target_details(ensembl, fetcher)
        if details:
            for protein in details.get("proteinIds") or []:
                if protein.get("source") == "uniprot_swissprot":
                    uniprot = protein.get("id")
                    break
    except Exception:
        details = None
    return GeneContext(
        symbol=symbol,
        ensembl_id=ensembl,
        entrez_id=_entrez_from_depmap(settings, symbol),
        uniprot_id=uniprot,
        chromosome=str(row["chr"]),
        start=int(row["gene_start"]),
        end=int(row["gene_end"]),
        biotype=str(row["gene_type"]),
    )


def resolve_gene(
    query: str,
    settings: Settings,
    offline: bool = False,
    fetcher: CachedFetcher | None = None,
) -> GeneContext:
    fetcher = fetcher or CachedFetcher(settings.data_root / "cache", offline=offline)
    info = _gene_info(settings)
    q = query.strip()

    row = None
    if q.upper().startswith("ENSG"):
        match = info[info["gene_id"] == q]
    else:
        match = info[info["gene_name"] == q]
        if match.empty and 6 <= len(q) <= 10 and q.isalnum() and q.upper() == q:
            try:
                payload = fetcher.request_json(
                    f"uniprot_{q}",
                    "GET",
                    UNIPROT_URL.format(acc=q),
                    gene="_global",
                )
                symbol = payload["genes"][0]["geneName"]["value"]
                match = info[info["gene_name"] == symbol]
            except Exception:
                match = info.iloc[0:0]
    if not match.empty:
        row = match.iloc[0]

    if row is None:
        try:
            hits = search_targets(q, fetcher)
        except Exception:
            hits = []
        if hits:
            match = info[info["gene_id"] == hits[0]["id"]]
            if not match.empty:
                row = match.iloc[0]

    if row is None:
        candidates = difflib.get_close_matches(q, info["gene_name"].dropna().tolist(), n=5)
        hint = f"; did you mean: {', '.join(candidates)}" if candidates else ""
        raise GeneNotFound(f"cannot resolve gene '{query}'{hint}")

    return _row_to_context(row, settings, fetcher)
```

注意：`_row_to_context` 调用 OT 可能在离线且无缓存时抛异常；它已用 `try/except` 降级，UniProt ID 为空不影响后续模块。

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_gene_resolve.py -v`
Expected: PASS

---

### Task 6: cBioPortal TCGA 突变适配器

**Files:**
- Create: `src/target_profile/api/cbioportal.py`
- Create: `tests/test_cbioportal.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_cbioportal.py
import pandas as pd

from target_profile.api.cache import CachedFetcher
from target_profile.api.cbioportal import fetch_pancan_mutations


class FakeClient:
    def __init__(self):
        self.calls = []

    def request(self, method, url, params=None, json=None):
        self.calls.append((method, url, json))
        if url.endswith("/studies"):
            return FakeResponse(
                [
                    {"studyId": "tcga_pan_can_atlas_2018_luad", "name": "Lung Adenocarcinoma (TCGA, PanCancer Atlas)", "allSampleCount": 100},
                    {"studyId": "tcga_pan_can_atlas_2018_paad", "name": "Pancreatic Adenocarcinoma (TCGA, PanCancer Atlas)", "allSampleCount": 50},
                ]
            )
        if url.endswith("/sample-lists"):
            return FakeResponse([{"sampleListId": "luad_all", "category": "all_cases_in_study"}])
        if url.endswith("/mutations/fetch"):
            return FakeResponse(
                [
                    {
                        "sampleId": "S1",
                        "proteinChange": "G12C",
                        "mutationType": "Missense_Mutation",
                    }
                ]
            )
        return FakeResponse({})


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_fetch_returns_mutation_rows_and_study_counts(tmp_path):
    fetcher = CachedFetcher(tmp_path, offline=False, client=FakeClient())
    mutations, studies = fetch_pancan_mutations("KRAS", "3845", fetcher)
    assert len(studies) == 2
    assert studies["n_samples"].sum() == 150
    assert len(mutations) == 2
    assert set(mutations.columns) >= {"cancer", "sampleId", "proteinChange", "mutationType"}
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_cbioportal.py -v`
Expected: FAIL

- [ ] **Step 3: 实现适配器**

```python
# src/target_profile/api/cbioportal.py
import pandas as pd

from target_profile.api.cache import CachedFetcher

CBIO = "https://www.cbioportal.org/api"


def _study_label(name: str) -> str:
    return name.split(" (TCGA")[0]


def fetch_pancan_mutations(
    symbol: str, entrez_id: str, fetcher: CachedFetcher
) -> tuple[pd.DataFrame, pd.DataFrame]:
    studies_payload = fetcher.request_json(
        "cbioportal_studies",
        "GET",
        f"{CBIO}/studies",
        gene=symbol,
        params={"projection": "SUMMARY", "pageSize": 100000},
    )
    pan = {s["studyId"]: s for s in studies_payload if "tcga_pan_can_atlas" in s["studyId"]}

    mutation_rows: list[dict] = []
    study_rows: list[dict] = []
    for study_id in sorted(pan):
        study = pan[study_id]
        sample_lists = fetcher.request_json(
            f"cbioportal_{study_id}_samplelists",
            "GET",
            f"{CBIO}/studies/{study_id}/sample-lists",
            gene=symbol,
        )
        sample_list_id = next(
            (
                item["sampleListId"]
                for item in sample_lists
                if item.get("category") == "all_cases_in_study"
                or item["sampleListId"].endswith("_all")
            ),
            sample_lists[0]["sampleListId"] if sample_lists else None,
        )
        if sample_list_id is None:
            continue
        mutations = fetcher.request_json(
            f"cbioportal_{study_id}_mutations",
            "POST",
            f"{CBIO}/molecular-profiles/{study_id}_mutations/mutations/fetch",
            gene=symbol,
            json_body={"entrezGeneIds": [int(entrez_id)], "sampleListId": sample_list_id},
        )
        cancer = _study_label(study["name"])
        mutated = {m["sampleId"] for m in mutations}
        study_rows.append(
            {
                "studyId": study_id,
                "cancer": cancer,
                "n_samples": int(study.get("allSampleCount") or 0),
                "n_mutated_samples": len(mutated),
                "n_mutations": len(mutations),
            }
        )
        for mutation in mutations:
            mutation_rows.append(
                {
                    "cancer": cancer,
                    "sampleId": mutation["sampleId"],
                    "proteinChange": mutation.get("proteinChange"),
                    "mutationType": mutation.get("mutationType"),
                }
            )

    studies_df = pd.DataFrame(
        study_rows, columns=["studyId", "cancer", "n_samples", "n_mutated_samples", "n_mutations"]
    )
    mutations_df = pd.DataFrame(
        mutation_rows, columns=["cancer", "sampleId", "proteinChange", "mutationType"]
    )
    return mutations_df, studies_df
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_cbioportal.py -v`
Expected: PASS

---

### Task 7: 表达分析模块

**Files:**
- Create: `src/target_profile/analysis/__init__.py`
- Create: `src/target_profile/analysis/expression.py`
- Create: `tests/test_expression.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_expression.py
import pandas as pd

from target_profile.analysis.expression import analyze_expression
from target_profile.config import Settings
from target_profile.models import GeneContext


def _settings(tmp_path):
    parquet = tmp_path / "data" / "parquet"
    parquet.mkdir(parents=True)
    pd.DataFrame(
        {
            "Gene": ["KRAS", "KRAS", "TP53", "TP53", "EGFR", "EGFR"],
            "Tissue": ["Lung", "Liver", "Lung", "Liver", "Lung", "Liver"],
            "Expression": [10.0, 2.0, 20.0, 1.0, 5.0, 3.0],
        }
    ).to_parquet(parquet / "gtex.parquet", index=False)
    pd.DataFrame(
        {
            "ModelID": ["ACH-1", "ACH-2", "ACH-3"],
            "KRAS (3845)": [5.0, 6.0, 7.0],
        }
    ).to_parquet(parquet / "depmap_expression.parquet", index=False)
    pd.DataFrame(
        {
            "ModelID": ["ACH-1", "ACH-2", "ACH-3"],
            "OncotreeLineage": ["Lung", "Lung", "Bowel"],
        }
    ).to_parquet(parquet / "depmap_model.parquet", index=False)
    pd.DataFrame(
        {
            "Gene": ["KRAS"],
            "RNA tissue specificity": ["Expressed in all"],
            "Subcellular location": ["Plasma membrane"],
        }
    ).to_parquet(parquet / "hpa.parquet", index=False)
    return Settings(lake_root=tmp_path / "lake", data_root=tmp_path / "data", out_root=tmp_path / "out")


def test_expression_facts_and_tables(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703")
    result = analyze_expression(ctx, _settings(tmp_path), offline=True)
    assert result.status == "ok"
    assert result.facts["gtex_tissue_count"] == 2
    assert result.facts["gtex_top_tissue"] == "Lung"
    assert result.facts["tau"] > 0
    assert result.facts["depmap_n_lines"] == 3
    assert "gtex" in result.tables
    assert "depmap_lineage" in result.tables
    assert result.facts["hpa_tissue_specificity"] == "Expressed in all"
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_expression.py -v`
Expected: FAIL

- [ ] **Step 3: 实现表达分析**

```python
# src/target_profile/analysis/__init__.py
"""Analysis modules producing structured ModuleResult objects."""
```

```python
# src/target_profile/analysis/expression.py
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from target_profile.config import Settings
from target_profile.errors import DataMissing
from target_profile.models import GeneContext, ModuleResult


def _read(path):
    if not path.exists():
        raise DataMissing(f"missing local data: {path}; run `target-profile data`")
    return pd.read_parquet(path)


def _tau(values: pd.Series) -> float:
    arr = values.to_numpy(dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 2 or arr.max() <= 0:
        return 0.0
    return float(((1 - arr / arr.max()).sum()) / (len(arr) - 1))


def analyze_expression(ctx: GeneContext, settings: Settings, offline: bool = True) -> ModuleResult:
    result = ModuleResult(name="expression")
    parquet = settings.data_root / "parquet"

    gtex = _read(parquet / "gtex.parquet")
    sub = gtex[gtex["Gene"] == ctx.symbol].copy()
    if sub.empty:
        return result.degrade("GTEx: no expression record")

    tissue = (
        sub.groupby("Tissue")["Expression"]
        .agg(["median", "mean", "max", "count"])
        .reset_index()
        .sort_values("median", ascending=False)
    )
    tissues = sub["Tissue"].unique()
    percentiles = []
    all_genes = gtex[gtex["Tissue"].isin(tissues)]
    for tissue_name, group in all_genes.groupby("Tissue"):
        value = sub.loc[sub["Tissue"] == tissue_name, "Expression"].iloc[0]
        percentiles.append(
            {
                "Tissue": tissue_name,
                "percentile": round(float((group["Expression"] < value).mean() * 100), 1),
            }
        )
    percentile_df = pd.DataFrame(percentiles).sort_values("percentile", ascending=False)

    result.tables["gtex"] = tissue
    result.tables["gtex_percentile"] = percentile_df
    result.facts.update(
        {
            "gtex_tissue_count": int(len(tissue)),
            "gtex_top_tissue": str(tissue.iloc[0]["Tissue"]),
            "gtex_top_median_tpm": round(float(tissue.iloc[0]["median"]), 2),
            "gtex_median_across_tissues": round(float(tissue["median"].median()), 2),
            "tau": round(_tau(tissue["median"]), 3),
            "gtex_mean_percentile": round(float(percentile_df["percentile"].mean()), 1),
        }
    )

    expr_path = parquet / "depmap_expression.parquet"
    if expr_path.exists():
        schema = pq.read_schema(expr_path).names
        column = next((c for c in schema if c.startswith(f"{ctx.symbol} (")), None)
        if column:
            expr = pq.read_table(expr_path, columns=["ModelID", column]).to_pandas()
            expr = expr.rename(columns={column: "value"}).dropna()
            model = _read(parquet / "depmap_model.parquet")[
                ["ModelID", "CellLineName", "OncotreeLineage", "OncotreePrimaryDisease"]
            ]
            expr = expr.merge(model, on="ModelID", how="left")
            lineage = (
                expr.groupby("OncotreeLineage")["value"]
                .agg(["median", "mean", "count"])
                .reset_index()
                .query("count >= 3")
                .sort_values("median", ascending=False)
            )
            result.tables["depmap_lineage"] = lineage
            result.tables["depmap_lines"] = expr.sort_values("value", ascending=False)
            result.facts.update(
                {
                    "depmap_n_lines": int(len(expr)),
                    "depmap_median_logtpm": round(float(expr["value"].median()), 2),
                    "depmap_top_lineage": (
                        str(lineage.iloc[0]["OncotreeLineage"]) if not lineage.empty else None
                    ),
                }
            )

    hpa_path = parquet / "hpa.parquet"
    if hpa_path.exists():
        hpa = _read(hpa_path)
        row = hpa[hpa["Gene"] == ctx.symbol]
        if not row.empty:
            record = row.iloc[0]
            result.facts["hpa_tissue_specificity"] = str(record.get("RNA tissue specificity"))
            result.facts["hpa_subcellular_location"] = str(record.get("Subcellular location"))

    return result
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_expression.py -v`
Expected: PASS

---

### Task 8: 突变分析模块

**Files:**
- Create: `src/target_profile/analysis/mutation.py`
- Create: `tests/test_mutation.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_mutation.py
import pandas as pd

from target_profile.analysis.mutation import analyze_mutation
from target_profile.config import Settings
from target_profile.models import GeneContext


class FakeFetcher:
    def request_json(self, *args, **kwargs):
        raise AssertionError("offline path must not fetch")


def _settings(tmp_path):
    cache = tmp_path / "data" / "cache" / "KRAS"
    cache.mkdir(parents=True)
    (cache / "cbioportal_studies.json").write_text(
        '[{"studyId": "tcga_pan_can_atlas_2018_luad", "name": "Lung Adenocarcinoma (TCGA, PanCancer Atlas)", "allSampleCount": 100},'
        ' {"studyId": "tcga_pan_can_atlas_2018_paad", "name": "Pancreatic Adenocarcinoma (TCGA, PanCancer Atlas)", "allSampleCount": 40}]'
    )
    for study, sample_list, mutations in [
        (
            "tcga_pan_can_atlas_2018_luad",
            "luad_all",
            [
                {"sampleId": "S1", "proteinChange": "G12C", "mutationType": "Missense_Mutation"},
                {"sampleId": "S2", "proteinChange": "G12C", "mutationType": "Missense_Mutation"},
            ],
        ),
        (
            "tcga_pan_can_atlas_2018_paad",
            "paad_all",
            [{"sampleId": "S3", "proteinChange": "G12D", "mutationType": "Missense_Mutation"}],
        ),
    ]:
        (cache / f"cbioportal_{study}_samplelists.json").write_text(
            f'[{{"sampleListId": "{sample_list}", "category": "all_cases_in_study"}}]'
        )
        import json
        (cache / f"cbioportal_{study}_mutations.json").write_text(json.dumps(mutations))
    return Settings(lake_root=tmp_path / "lake", data_root=tmp_path / "data", out_root=tmp_path / "out")


def test_mutation_facts(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703", entrez_id="3845")
    result = analyze_mutation(ctx, _settings(tmp_path), offline=True)
    assert result.status == "ok"
    assert result.facts["n_samples"] == 140
    assert result.facts["n_mutated_samples"] == 3
    assert result.facts["overall_freq_pct"] == 2.14
    assert result.facts["top_cancer"] == "Pancreatic Adenocarcinoma"
    assert result.facts["top_protein_change"] == "G12C"
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_mutation.py -v`
Expected: FAIL

- [ ] **Step 3: 实现突变分析**

```python
# src/target_profile/analysis/mutation.py
import pandas as pd

from target_profile.api.cache import CachedFetcher
from target_profile.api.cbioportal import fetch_pancan_mutations
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult


def analyze_mutation(
    ctx: GeneContext,
    settings: Settings,
    offline: bool = True,
    fetcher: CachedFetcher | None = None,
) -> ModuleResult:
    result = ModuleResult(name="mutation")
    if not ctx.entrez_id:
        return result.degrade("mutation: entrez ID unavailable")
    fetcher = fetcher or CachedFetcher(settings.data_root / "cache", offline=offline)

    try:
        mutations, studies = fetch_pancan_mutations(ctx.symbol, ctx.entrez_id, fetcher)
    except Exception as exc:
        return result.degrade(f"mutation: cBioPortal unavailable ({exc})")

    if studies.empty:
        return result.degrade("mutation: no TCGA PanCancer studies")

    studies = studies.copy()
    studies["freq_pct"] = studies.apply(
        lambda row: round(100 * row["n_mutated_samples"] / row["n_samples"], 2)
        if row["n_samples"]
        else 0.0,
        axis=1,
    )
    studies = studies.sort_values("freq_pct", ascending=False)
    total_samples = int(studies["n_samples"].sum())
    total_mutated = int(studies["n_mutated_samples"].sum())

    type_counts = (
        mutations["mutationType"].fillna("Unknown").value_counts().rename_axis("mutationType").reset_index(name="count")
    )
    protein_counts = (
        mutations["proteinChange"].dropna().value_counts().rename_axis("proteinChange").reset_index(name="count")
    )

    result.tables["cancers"] = studies
    result.tables["types"] = type_counts
    result.tables["protein_changes"] = protein_counts
    result.facts.update(
        {
            "n_studies": int(len(studies)),
            "n_samples": total_samples,
            "n_mutated_samples": total_mutated,
            "overall_freq_pct": round(100 * total_mutated / total_samples, 2) if total_samples else 0.0,
            "top_cancer": str(studies.iloc[0]["cancer"]),
            "top_cancer_freq_pct": float(studies.iloc[0]["freq_pct"]),
            "top_protein_change": (
                str(protein_counts.iloc[0]["proteinChange"]) if not protein_counts.empty else None
            ),
            "top_protein_change_count": (
                int(protein_counts.iloc[0]["count"]) if not protein_counts.empty else 0
            ),
        }
    )
    return result
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_mutation.py -v`
Expected: PASS

---

### Task 9: 依赖分析模块

**Files:**
- Create: `src/target_profile/analysis/dependency.py`
- Create: `tests/test_dependency.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_dependency.py
import pandas as pd

from target_profile.analysis.dependency import analyze_dependency
from target_profile.config import Settings
from target_profile.models import GeneContext


def _settings(tmp_path):
    parquet = tmp_path / "data" / "parquet"
    parquet.mkdir(parents=True)
    pd.DataFrame(
        {
            "ModelID": ["ACH-1", "ACH-2", "ACH-3", "ACH-4", "ACH-5", "ACH-6"],
            "KRAS (3845)": [-1.5, -0.8, -0.6, -0.1, -0.2, 0.1],
        }
    ).to_parquet(parquet / "depmap_gene_effect.parquet", index=False)
    pd.DataFrame(
        {
            "ModelID": ["ACH-1", "ACH-2", "ACH-3", "ACH-4", "ACH-5", "ACH-6"],
            "CellLineName": ["A", "B", "C", "D", "E", "F"],
            "OncotreeLineage": ["Lung", "Lung", "Lung", "Bowel", "Bowel", "Bowel"],
            "OncotreePrimaryDisease": ["LUAD", "LUAD", "LUAD", "COAD", "COAD", "COAD"],
        }
    ).to_parquet(parquet / "depmap_model.parquet", index=False)
    return Settings(lake_root=tmp_path / "lake", data_root=tmp_path / "data", out_root=tmp_path / "out")


def test_dependency_facts(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703")
    result = analyze_dependency(ctx, _settings(tmp_path), offline=True)
    assert result.status == "ok"
    assert result.facts["n_lines"] == 6
    assert result.facts["median_effect"] == -0.4
    assert result.facts["strong_dependency_count"] == 3
    assert result.facts["top_lineage"] == "Lung"
    assert "by_lineage" in result.tables
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_dependency.py -v`
Expected: FAIL

- [ ] **Step 3: 实现依赖分析**

```python
# src/target_profile/analysis/dependency.py
import pandas as pd
import pyarrow.parquet as pq

from target_profile.config import Settings
from target_profile.errors import DataMissing
from target_profile.models import GeneContext, ModuleResult


def analyze_dependency(ctx: GeneContext, settings: Settings, offline: bool = True) -> ModuleResult:
    result = ModuleResult(name="dependency")
    parquet = settings.data_root / "parquet"
    effect_path = parquet / "depmap_gene_effect.parquet"
    model_path = parquet / "depmap_model.parquet"
    if not effect_path.exists() or not model_path.exists():
        raise DataMissing(f"missing DepMap data under {parquet}; run `target-profile data`")

    schema = pq.read_schema(effect_path).names
    column = next((c for c in schema if c.startswith(f"{ctx.symbol} (")), None)
    if not column:
        return result.degrade(f"dependency: no DepMap column for {ctx.symbol}")

    effect = pq.read_table(effect_path, columns=["ModelID", column]).to_pandas()
    effect = effect.rename(columns={column: "effect"}).dropna()
    model = pd.read_parquet(model_path)[
        ["ModelID", "CellLineName", "OncotreeLineage", "OncotreePrimaryDisease"]
    ]
    df = effect.merge(model, on="ModelID", how="left")

    threshold = settings.thresholds.strong_dependency_effect
    strong = df[df["effect"] <= threshold].sort_values("effect")
    by_lineage = (
        df.groupby("OncotreeLineage")["effect"]
        .agg(["median", "mean", "count"])
        .reset_index()
        .query("count >= 3")
        .sort_values("median")
    )

    result.tables["distribution"] = df
    result.tables["strong_lines"] = strong
    result.tables["by_lineage"] = by_lineage
    result.facts.update(
        {
            "n_lines": int(len(df)),
            "median_effect": round(float(df["effect"].median()), 3),
            "mean_effect": round(float(df["effect"].mean()), 3),
            "strong_dependency_count": int(len(strong)),
            "strong_dependency_fraction": round(float(len(strong) / len(df)), 3) if len(df) else 0.0,
            "threshold_effect": threshold,
            "top_lineage": str(by_lineage.iloc[0]["OncotreeLineage"]) if not by_lineage.empty else None,
            "top_lineage_median": (
                round(float(by_lineage.iloc[0]["median"]), 3) if not by_lineage.empty else None
            ),
            "most_dependent_line": (
                str(strong.iloc[0]["CellLineName"]) if not strong.empty else None
            ),
        }
    )
    return result
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_dependency.py -v`
Expected: PASS

---

### Task 10: 图表主题与三组图

**Files:**
- Create: `src/target_profile/figures/__init__.py`
- Create: `src/target_profile/figures/theme.py`
- Create: `src/target_profile/figures/charts.py`
- Create: `tests/test_figures.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_figures.py
import pandas as pd

from target_profile.figures.charts import plot_dependency, plot_expression, plot_mutation
from target_profile.models import ModuleResult


def _result(name, table, extra=None):
    r = ModuleResult(name=name)
    r.tables.update(table)
    if extra:
        r.facts.update(extra)
    return r


def test_expression_figure(tmp_path):
    r = _result(
        "expression",
        {
            "gtex": pd.DataFrame({"Tissue": ["Lung", "Liver"], "median": [10.0, 2.0]}),
            "depmap_lineage": pd.DataFrame(
                {"OncotreeLineage": ["Lung", "Bowel"], "median": [5.0, 6.0], "count": [10, 8]}
            ),
        },
    )
    paths = plot_expression(r, tmp_path)
    assert len(paths) == 1
    assert paths[0].exists() and paths[0].stat().st_size > 0


def test_mutation_figure(tmp_path):
    r = _result(
        "mutation",
        {
            "cancers": pd.DataFrame({"cancer": ["LUAD", "PAAD"], "freq_pct": [30.0, 60.0], "n_mutated_samples": [30, 30]}),
            "types": pd.DataFrame({"mutationType": ["Missense_Mutation"], "count": [60]}),
            "protein_changes": pd.DataFrame({"proteinChange": ["G12D", "G12C"], "count": [20, 10]}),
        },
    )
    paths = plot_mutation(r, tmp_path)
    assert len(paths) == 1
    assert paths[0].exists() and paths[0].stat().st_size > 0


def test_dependency_figure(tmp_path):
    r = _result(
        "dependency",
        {
            "distribution": pd.DataFrame({"effect": [-1.5, -0.5, 0.0, 0.2]}),
            "by_lineage": pd.DataFrame({"OncotreeLineage": ["Lung", "Bowel"], "median": [-0.8, -0.2], "count": [10, 8]}),
        },
    )
    paths = plot_dependency(r, tmp_path)
    assert len(paths) == 1
    assert paths[0].exists() and paths[0].stat().st_size > 0
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_figures.py -v`
Expected: FAIL

- [ ] **Step 3: 实现图表**

```python
# src/target_profile/figures/__init__.py
"""Figure builders."""
```

```python
# src/target_profile/figures/theme.py
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

PALETTE = ["#b91c1c", "#0369a1", "#047857", "#b45309", "#6d28d9", "#475569"]


def apply_theme() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": 300,
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.alpha": 0.25,
            "grid.linewidth": 0.6,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )


def save(fig, out_dir: Path, name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path
```

```python
# src/target_profile/figures/charts.py
from pathlib import Path

from target_profile.figures.theme import PALETTE, apply_theme, save

import matplotlib.pyplot as plt

from target_profile.models import ModuleResult


def plot_expression(result: ModuleResult, out_dir: Path) -> list[Path]:
    apply_theme()
    fig, axes = plt.subplots(1, 2, figsize=(16.5 / 2.54, 6 / 2.54 * 1.6))
    gtex = result.tables.get("gtex")
    if gtex is not None and not gtex.empty:
        top = gtex.head(20).iloc[::-1]
        axes[0].barh(top["Tissue"], top["median"], color=PALETTE[0])
        axes[0].set_title("GTEx tissue expression")
        axes[0].set_xlabel("Median TPM")
        axes[0].tick_params(labelsize=6)
    else:
        axes[0].text(0.5, 0.5, "No GTEx data", ha="center", va="center")
        axes[0].set_axis_off()

    lineage = result.tables.get("depmap_lineage")
    if lineage is not None and not lineage.empty:
        top_lineage = lineage.head(12).iloc[::-1]
        axes[1].barh(top_lineage["OncotreeLineage"], top_lineage["median"], color=PALETTE[1])
        axes[1].set_title("DepMap cell-line expression")
        axes[1].set_xlabel("Median log2(TPM+1)")
        axes[1].tick_params(labelsize=6)
    else:
        axes[1].text(0.5, 0.5, "No DepMap data", ha="center", va="center")
        axes[1].set_axis_off()

    fig.tight_layout()
    return [save(fig, out_dir, "expression")]


def plot_mutation(result: ModuleResult, out_dir: Path) -> list[Path]:
    apply_theme()
    fig, axes = plt.subplots(1, 2, figsize=(16.5 / 2.54, 6 / 2.54 * 1.6))
    cancers = result.tables.get("cancers")
    if cancers is not None and not cancers.empty:
        top = cancers.head(15).iloc[::-1]
        axes[0].barh(top["cancer"], top["freq_pct"], color=PALETTE[0])
        axes[0].set_title("TCGA PanCancer mutation frequency")
        axes[0].set_xlabel("% mutated samples")
        axes[0].tick_params(labelsize=6)
    else:
        axes[0].text(0.5, 0.5, "No mutation data", ha="center", va="center")
        axes[0].set_axis_off()

    proteins = result.tables.get("protein_changes")
    if proteins is not None and not proteins.empty:
        top = proteins.head(10).iloc[::-1]
        axes[1].barh(top["proteinChange"], top["count"], color=PALETTE[2])
        axes[1].set_title("Top protein changes")
        axes[1].set_xlabel("Mutation count")
        axes[1].tick_params(labelsize=6)
    else:
        axes[1].text(0.5, 0.5, "No protein changes", ha="center", va="center")
        axes[1].set_axis_off()

    fig.tight_layout()
    return [save(fig, out_dir, "mutation")]


def plot_dependency(result: ModuleResult, out_dir: Path) -> list[Path]:
    apply_theme()
    fig, axes = plt.subplots(1, 2, figsize=(16.5 / 2.54, 6 / 2.54 * 1.6))
    dist = result.tables.get("distribution")
    if dist is not None and not dist.empty:
        axes[0].hist(dist["effect"], bins=30, color=PALETTE[1], edgecolor="white")
        axes[0].set_title("DepMap CRISPR gene effect")
        axes[0].set_xlabel("Chronos effect score")
        axes[0].set_ylabel("Cell lines")
    else:
        axes[0].text(0.5, 0.5, "No dependency data", ha="center", va="center")
        axes[0].set_axis_off()

    lineage = result.tables.get("by_lineage")
    if lineage is not None and not lineage.empty:
        top = lineage.head(12).iloc[::-1]
        axes[1].barh(top["OncotreeLineage"], top["median"], color=PALETTE[0])
        axes[1].set_title("Dependency by lineage")
        axes[1].set_xlabel("Median effect")
        axes[1].tick_params(labelsize=6)
    else:
        axes[1].text(0.5, 0.5, "No lineage data", ha="center", va="center")
        axes[1].set_axis_off()

    fig.tight_layout()
    return [save(fig, out_dir, "dependency")]
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_figures.py -v`
Expected: PASS

---

### Task 11: 自包含 HTML 报告

**Files:**
- Create: `src/target_profile/report/__init__.py`
- Create: `src/target_profile/report/templates/report.html.j2`
- Create: `src/target_profile/report/print.css`
- Create: `src/target_profile/report/render.py`
- Create: `tests/test_render.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_render.py
import json

import pandas as pd

from target_profile.models import GeneContext, ModuleResult
from target_profile.report.render import render_report


def test_render_embeds_facts_and_images(tmp_path):
    figure = tmp_path / "fig.png"
    figure.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703", entrez_id="3845")
    r = ModuleResult(name="expression", facts={"tau": 0.42, "gtex_top_tissue": "Lung"})
    r.tables["gtex"] = pd.DataFrame({"Tissue": ["Lung"], "median": [10.0]})
    r.figure_paths = [figure]

    html_path, facts_path = render_report(ctx, [r], tmp_path / "out")

    html = html_path.read_text(encoding="utf-8")
    assert "KRAS" in html
    assert "data:image/png;base64," in html
    assert "Lung" in html
    facts = json.loads(facts_path.read_text(encoding="utf-8"))
    assert facts["gene"]["symbol"] == "KRAS"
    assert facts["modules"]["expression"]["facts"]["tau"] == 0.42
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_render.py -v`
Expected: FAIL

- [ ] **Step 3: 实现模板与渲染器**

```html
{# src/target_profile/report/templates/report.html.j2 #}
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ gene.symbol }} 靶点画像</title>
<style>{{ css | safe }}</style>
</head>
<body>
<header>
  <h1>{{ gene.symbol }} 靶点全方位画像</h1>
  <div class="meta">
    Ensembl {{ gene.ensembl_id }}{% if gene.entrez_id %} · Entrez {{ gene.entrez_id }}{% endif %}
    {% if gene.chromosome %} · chr{{ gene.chromosome }}:{{ gene.start }}-{{ gene.end }}{% endif %}
    · 生成时间 {{ generated_at }}
  </div>
</header>
<main>
{% for section in sections %}
<section id="{{ section.id }}">
  <h2>{{ section.title }}</h2>
  {% if section.status == "no_data" %}
  <p class="nodata">暂无可用数据。{% for caveat in section.caveats %}{{ caveat }} {% endfor %}</p>
  {% else %}
  {% for figure in section.figures %}
  <figure><img src="{{ figure.src }}" alt="{{ section.title }}"><figcaption>{{ figure.caption }}</figcaption></figure>
  {% endfor %}
  <table class="facts">
    <tr><th>指标</th><th>数值</th></tr>
    {% for fact in section.fact_rows %}
    <tr><td>{{ fact.label }}</td><td>{{ fact.value }}</td></tr>
    {% endfor %}
  </table>
  {% for table in section.tables %}
  <h3>{{ table.title }}</h3>
  {{ table.html | safe }}
  {% endfor %}
  {% if section.caveats %}<p class="caveat">注：{% for caveat in section.caveats %}{{ caveat }} {% endfor %}</p>{% endif %}
  {% endif %}
</section>
{% endfor %}
</main>
<footer>
  <p>数据来源：GTEx v8、DepMap、HPA、cBioPortal TCGA PanCancer Atlas。仅供科研参考，不构成临床诊疗建议。</p>
</footer>
</body>
</html>
```

```css
/* src/target_profile/report/print.css */
@page { size: A4; margin: 16mm 14mm; }
body { margin: 0; font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; color: #1e293b; font-size: 13px; line-height: 1.65; }
header { background: linear-gradient(135deg, #7f1d1d, #b91c1c 50%, #0369a1); color: #fff; padding: 28px 24px; }
header h1 { margin: 0 0 8px; font-size: 26px; }
header .meta { font-size: 11px; opacity: .9; font-family: ui-monospace, Menlo, monospace; }
main { padding: 20px 24px 40px; }
section { margin-bottom: 28px; page-break-inside: avoid; }
h2 { border-left: 5px solid #b91c1c; padding-left: 10px; font-size: 18px; }
h3 { font-size: 14px; color: #334155; }
figure { margin: 12px 0; }
figure img { width: 100%; border: 1px solid #e2e8f0; border-radius: 6px; }
figcaption { font-size: 11px; color: #64748b; margin-top: 4px; }
table { border-collapse: collapse; width: 100%; font-size: 12px; margin: 8px 0; }
th, td { border: 1px solid #e2e8f0; padding: 5px 7px; text-align: left; }
th { background: #f8fafc; }
table.facts td:first-child { color: #475569; width: 55%; }
.nodata { background: #fff7ed; border: 1px solid #fed7aa; padding: 12px; border-radius: 6px; }
.caveat { font-size: 11px; color: #92400e; }
footer { padding: 12px 24px 28px; font-size: 11px; color: #64748b; border-top: 1px solid #e2e8f0; }
</style>
```

```python
# src/target_profile/report/__init__.py
"""HTML/PDF report rendering."""
```

```python
# src/target_profile/report/render.py
import base64
import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from target_profile.data_prep.manifest import now_iso
from target_profile.models import GeneContext, ModuleResult

TEMPLATE_DIR = Path(__file__).parent / "templates"
CSS_PATH = Path(__file__).parent / "print.css"

FACT_LABELS = {
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
}

SECTION_TITLES = {
    "expression": "表达",
    "mutation": "突变与变异",
    "dependency": "依赖性与癌症特征",
}


def _image_data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _table_html(df, max_rows: int = 20) -> str:
    return df.head(max_rows).to_html(index=False, classes="dt", border=0, escape=True)


def render_report(
    gene: GeneContext, modules: list[ModuleResult], out_dir: Path
) -> tuple[Path, Path]:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
    )
    template = env.get_template("report.html.j2")
    sections: list[dict[str, Any]] = []
    for module in modules:
        title = SECTION_TITLES.get(module.name, module.name)
        figures = [
            {"src": _image_data_uri(path), "caption": f"{title} · {path.stem}"}
            for path in module.figure_paths
        ]
        fact_rows = [
            {"label": FACT_LABELS.get(key, key), "value": value}
            for key, value in module.facts.items()
        ]
        tables = [
            {"title": key.replace("_", " "), "html": _table_html(df)}
            for key, df in module.tables.items()
            if hasattr(df, "head")
        ]
        sections.append(
            {
                "id": module.name,
                "title": title,
                "status": module.status,
                "figures": figures,
                "fact_rows": fact_rows,
                "tables": tables,
                "caveats": module.caveats,
            }
        )

    html = template.render(
        gene=gene,
        sections=sections,
        css=CSS_PATH.read_text(encoding="utf-8"),
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
        "modules": {
            module.name: {
                "status": module.status,
                "facts": module.facts,
                "caveats": module.caveats,
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

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_render.py -v`
Expected: PASS

---

### Task 12: PDF 导出

**Files:**
- Create: `src/target_profile/report/pdf.py`
- Create: `tests/test_pdf.py`

- [ ] **Step 1: 写失败测试（不依赖已安装浏览器）**

```python
# tests/test_pdf.py
from target_profile.report.pdf import html_to_pdf


def test_pdf_failure_returns_false(tmp_path, monkeypatch):
    html = tmp_path / "report.html"
    html.write_text("<html><body>x</body></html>", encoding="utf-8")

    def boom(html_path, pdf_path):
        raise RuntimeError("no browser")

    monkeypatch.setattr("target_profile.report.pdf._print_with_playwright", boom)
    assert html_to_pdf(html, tmp_path / "report.pdf") is False
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_pdf.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 PDF 导出**

```python
# src/target_profile/report/pdf.py
from pathlib import Path
from typing import Callable


def _print_with_playwright(html_path: Path, pdf_path: Path) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.resolve().as_uri(), wait_until="load")
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

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_pdf.py -v`
Expected: PASS

---

### Task 13: CLI 全量接线（run / fetch / data / doctor）

**Files:**
- Modify: `src/target_profile/cli.py`
- Create: `tests/test_cli_run.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_cli_run.py
import json
from pathlib import Path

import pandas as pd
from typer.testing import CliRunner

from target_profile.cli import app


def _home(tmp_path):
    home = tmp_path / "home"
    (home / "config").mkdir(parents=True)
    (home / "config/settings.toml").write_text(
        f'lake_root = "{tmp_path}/lake"\ndata_root = "data"\nout_root = "out"\n',
        encoding="utf-8",
    )
    parquet = home / "data" / "parquet"
    parquet.mkdir(parents=True)
    pd.DataFrame(
        {
            "gene_id": ["ENSG00000133703"],
            "gene_name": ["KRAS"],
            "chr": ["12"],
            "gene_start": [25205246],
            "gene_end": [25250936],
            "gene_type": ["protein_coding"],
        }
    ).to_parquet(parquet / "gene_info.parquet", index=False)
    pd.DataFrame(
        {"Gene": ["KRAS", "TP53"], "Tissue": ["Lung", "Lung"], "Expression": [10.0, 5.0]}
    ).to_parquet(parquet / "gtex.parquet", index=False)
    pd.DataFrame({"ModelID": ["ACH-1"], "KRAS (3845)": [-1.0]}).to_parquet(
        parquet / "depmap_gene_effect.parquet", index=False
    )
    pd.DataFrame({"ModelID": ["ACH-1"], "KRAS (3845)": [5.0]}).to_parquet(
        parquet / "depmap_expression.parquet", index=False
    )
    pd.DataFrame(
        {
            "ModelID": ["ACH-1"],
            "CellLineName": ["A"],
            "OncotreeLineage": ["Lung"],
            "OncotreePrimaryDisease": ["LUAD"],
        }
    ).to_parquet(parquet / "depmap_model.parquet", index=False)
    pd.DataFrame({"Gene": ["KRAS"], "RNA tissue specificity": ["all"]}).to_parquet(
        parquet / "hpa.parquet", index=False
    )
    cache = home / "data" / "cache" / "KRAS"
    cache.mkdir(parents=True)
    (cache / "cbioportal_studies.json").write_text(
        '[{"studyId": "tcga_pan_can_atlas_2018_luad", "name": "Lung Adenocarcinoma (TCGA, PanCancer Atlas)", "allSampleCount": 100}]'
    )
    (cache / "cbioportal_tcga_pan_can_atlas_2018_luad_samplelists.json").write_text(
        '[{"sampleListId": "luad_all", "category": "all_cases_in_study"}]'
    )
    (cache / "cbioportal_tcga_pan_can_atlas_2018_luad_mutations.json").write_text(
        '[{"sampleId": "S1", "proteinChange": "G12C", "mutationType": "Missense_Mutation"}]'
    )
    return home


def test_run_offline_produces_artifacts(tmp_path, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setenv("TARGET_PROFILE_HOME", str(home))
    result = CliRunner().invoke(
        app, ["run", "KRAS", "--offline", "--no-llm", "--format", "html"]
    )
    assert result.exit_code == 0, result.output
    out_dirs = list((home / "out").glob("KRAS_*"))
    assert out_dirs
    assert (out_dirs[0] / "report.html").exists()
    assert (out_dirs[0] / "facts.json").exists()
    facts = json.loads((out_dirs[0] / "facts.json").read_text())
    assert facts["gene"]["symbol"] == "KRAS"


def test_unknown_gene_exit_code(tmp_path, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setenv("TARGET_PROFILE_HOME", str(home))
    result = CliRunner().invoke(app, ["run", "NOTAGENE", "--offline", "--no-llm"])
    assert result.exit_code == 2
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_cli_run.py -v`
Expected: FAIL（run 命令不存在）

- [ ] **Step 3: 实现 CLI**

```python
# src/target_profile/cli.py
import logging
from datetime import datetime
from pathlib import Path

import typer

from target_profile import __version__
from target_profile.analysis.dependency import analyze_dependency
from target_profile.analysis.expression import analyze_expression
from target_profile.analysis.mutation import analyze_mutation
from target_profile.config import Settings, load_settings
from target_profile.data_prep.lake import DERIVERS, derive_all
from target_profile.errors import DataMissing, GeneNotFound
from target_profile.figures.charts import plot_dependency, plot_expression, plot_mutation
from target_profile.gene_resolve import resolve_gene
from target_profile.report.pdf import html_to_pdf
from target_profile.report.render import render_report

app = typer.Typer(no_args_is_help=True, help="Single-gene target profiling")

MODULES = [analyze_expression, analyze_mutation, analyze_dependency]
PLOTTERS = {
    "expression": plot_expression,
    "mutation": plot_mutation,
    "dependency": plot_dependency,
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
    if ctx.entrez_id:
        try:
            fetch_pancan_mutations(ctx.symbol, ctx.entrez_id, fetcher)
            typer.echo("cached: cBioPortal TCGA mutations")
        except Exception as exc:
            typer.echo(f"warning: cBioPortal fetch failed: {exc}", err=True)
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


@app.command()
def run(
    gene: str = typer.Argument(..., help="Gene symbol, alias, Ensembl or UniProt ID"),
    out: Path | None = typer.Option(None, "--out", help="Output directory"),
    format: str = typer.Option("both", "--format", help="html|pdf|both"),
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

    modules = []
    for analyzer in MODULES:
        name = analyzer.__name__.replace("analyze_", "")
        try:
            result = analyzer(ctx, settings, offline=offline)
        except DataMissing as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=3)
        except Exception as exc:
            logging.exception("module %s failed", name)
            from target_profile.models import ModuleResult

            result = ModuleResult(name=name).degrade(f"{name}: internal error ({exc})")
        plotter = PLOTTERS.get(result.name)
        if plotter and result.status == "ok":
            result.figure_paths = plotter(result, out_dir / "figures")
        modules.append(result)

    html_path, facts_path = render_report(ctx, modules, out_dir)
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

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_cli_run.py -v`
Expected: PASS

---

### Task 14: 端到端离线集成测试与真实数据验收

**Files:**
- Create: `tests/integration/test_vertical_slice.py`

- [ ] **Step 1: 写集成测试（复用 Task 13 的 fixture 构造）**

```python
# tests/integration/test_vertical_slice.py
import json
import socket

import pandas as pd
from typer.testing import CliRunner

from target_profile.cli import app


def _build_home(tmp_path):
    home = tmp_path / "home"
    (home / "config").mkdir(parents=True)
    (home / "config/settings.toml").write_text(
        f'lake_root = "{tmp_path}/lake"\ndata_root = "data"\nout_root = "out"\n',
        encoding="utf-8",
    )
    parquet = home / "data" / "parquet"
    parquet.mkdir(parents=True)
    pd.DataFrame(
        {
            "gene_id": ["ENSG00000133703", "ENSG00000141510"],
            "gene_name": ["KRAS", "TP53"],
            "chr": ["12", "17"],
            "gene_start": [25205246, 7661779],
            "gene_end": [25250936, 7687538],
            "gene_type": ["protein_coding", "protein_coding"],
        }
    ).to_parquet(parquet / "gene_info.parquet", index=False)
    pd.DataFrame(
        {
            "Gene": ["KRAS", "KRAS", "TP53", "TP53", "EGFR", "EGFR"],
            "Tissue": ["Lung", "Liver", "Lung", "Liver", "Lung", "Liver"],
            "Expression": [10.0, 2.0, 20.0, 1.0, 5.0, 3.0],
        }
    ).to_parquet(parquet / "gtex.parquet", index=False)
    pd.DataFrame(
        {
            "ModelID": ["ACH-1", "ACH-2", "ACH-3"],
            "KRAS (3845)": [-1.5, -0.8, -0.1],
            "TP53 (7157)": [-0.2, -0.1, -0.3],
        }
    ).to_parquet(parquet / "depmap_gene_effect.parquet", index=False)
    pd.DataFrame(
        {"ModelID": ["ACH-1", "ACH-2", "ACH-3"], "KRAS (3845)": [5.0, 6.0, 7.0]}
    ).to_parquet(parquet / "depmap_expression.parquet", index=False)
    pd.DataFrame(
        {
            "ModelID": ["ACH-1", "ACH-2", "ACH-3"],
            "CellLineName": ["A", "B", "C"],
            "OncotreeLineage": ["Lung", "Lung", "Bowel"],
            "OncotreePrimaryDisease": ["LUAD", "LUAD", "COAD"],
        }
    ).to_parquet(parquet / "depmap_model.parquet", index=False)
    pd.DataFrame({"Gene": ["KRAS", "TP53"], "RNA tissue specificity": ["all", "all"]}).to_parquet(
        parquet / "hpa.parquet", index=False
    )
    for gene, study, sample_list, mutation in [
        ("KRAS", "tcga_pan_can_atlas_2018_luad", "luad_all", "G12C"),
        ("TP53", "tcga_pan_can_atlas_2018_luad", "luad_all", "R175H"),
    ]:
        cache = home / "data" / "cache" / gene
        cache.mkdir(parents=True)
        (cache / "cbioportal_studies.json").write_text(
            '[{"studyId": "tcga_pan_can_atlas_2018_luad", "name": "Lung Adenocarcinoma (TCGA, PanCancer Atlas)", "allSampleCount": 100}]'
        )
        (cache / f"cbioportal_{study}_samplelists.json").write_text(
            f'[{{"sampleListId": "{sample_list}", "category": "all_cases_in_study"}}]'
        )
        (cache / f"cbioportal_{study}_mutations.json").write_text(
            json.dumps([{"sampleId": "S1", "proteinChange": mutation, "mutationType": "Missense_Mutation"}])
        )
    return home


def test_full_chain_offline(tmp_path, monkeypatch):
    home = _build_home(tmp_path)
    monkeypatch.setenv("TARGET_PROFILE_HOME", str(home))

    def no_network(*args, **kwargs):
        raise RuntimeError("network disabled in test")

    monkeypatch.setattr(socket.socket, "connect", no_network)

    for gene in ["KRAS", "TP53"]:
        result = CliRunner().invoke(app, ["run", gene, "--offline", "--no-llm", "--format", "html"])
        assert result.exit_code == 0, result.output
        out_dir = next((home / "out").glob(f"{gene}_*"))
        html = (out_dir / "report.html").read_text(encoding="utf-8")
        facts = json.loads((out_dir / "facts.json").read_text(encoding="utf-8"))
        assert facts["gene"]["symbol"] == gene
        assert "data:image/png;base64," in html
        assert facts["modules"]["expression"]["status"] == "ok"
        assert facts["modules"]["mutation"]["status"] == "ok"
        assert facts["modules"]["dependency"]["status"] == "ok"
```

- [ ] **Step 2: 运行全部测试**

Run: `uv run pytest -v`
Expected: 全部 PASS

- [ ] **Step 3: 真实数据派生（一次）**

Run:
```bash
uv run target-profile data all
uv run target-profile doctor
```
Expected: 6 个 parquet 生成；doctor 全部 OK；`data/parquet` 总大小约 300–500MB。

- [ ] **Step 4: 抓取 KRAS/TP53 的 API 缓存**

Run:
```bash
uv run target-profile fetch KRAS
uv run target-profile fetch TP53
```
Expected: `data/cache/KRAS/` 与 `data/cache/TP53/` 出现 cBioPortal JSON 文件。

- [ ] **Step 5: 生成 KRAS 报告（离线）**

Run:
```bash
uv run target-profile run KRAS --offline --no-llm --format html --force
```
Expected: `out/KRAS_YYYYMMDD/report.html` 与 `facts.json`；`facts.json` 中：
- `modules.mutation.facts.overall_freq_pct` 与参考项目 6.96%（容差 ±0.5，因样本计数口径可能略有差异）
- `modules.dependency.facts.n_lines` > 1000
- `modules.expression.facts.gtex_tissue_count` == 54

- [ ] **Step 6: 生成 TP53 报告并检查降级**

Run:
```bash
uv run target-profile run TP53 --offline --no-llm --format html --force
```
Expected: 成功产出；若某维度缓存缺失，该章节显示"暂无可用数据"且 `run.log` 有警告。

- [ ] **Step 7: PDF（需 Chromium）**

Run:
```bash
uv run playwright install chromium
uv run target-profile run KRAS --offline --no-llm --format both --force
```
Expected: `report.pdf` 生成；若 Chromium 不可用，脚本保留 HTML 并以退出码 4 提示。

---

## 里程碑对照

- **M0**：Task 1–2（骨架、配置、模型）
- **M1**：Task 3–6（lake 派生、API 缓存、基因解析、cBioPortal）
- **M2**：Task 7–14（三模块分析、图表、HTML、PDF、CLI、端到端验收）

## 已知限制（M2 范围）

- 仅覆盖表达/突变/依赖；通路、PTM、疾病、可成药性、安全性等章节在 M3–M5 接入。
- cBioPortal 每次 `fetch` 会发 32×2 次请求；首次较慢，缓存后离线可用。
- GTEx 为 lake 中的 v8 聚合数据，不是 v10 原始下载；manifest 会标注版本。
- 别名解析依赖 Open Targets API 缓存；完全离线且无缓存时仅支持标准符号/Ensembl。
