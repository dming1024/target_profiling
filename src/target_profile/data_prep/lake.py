from pathlib import Path

import pandas as pd

from target_profile.config import Settings
from target_profile.data_prep.manifest import (
    SourceEntry,
    now_iso,
    sha256_file,
    write_manifest,
)

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
