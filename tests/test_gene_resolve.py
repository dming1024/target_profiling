import pandas as pd
import pytest

from target_profile.api.cache import CachedFetcher
from target_profile.config import Settings
from target_profile.errors import GeneNotFound
from target_profile.gene_resolve import resolve_gene


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
    return Settings(
        lake_root=tmp_path / "lake",
        data_root=tmp_path / "data",
        out_root=tmp_path / "out",
    )


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
    cache = settings.data_root / "cache" / "_global"
    cache.mkdir(parents=True)
    (cache / "opentargets_search_K-RAS.json").write_text(
        '{"data": {"search": {"hits": [{"id": "ENSG00000133703", "name": "KRAS"}]}}}'
    )
    fetcher = CachedFetcher(settings.data_root / "cache", offline=True)
    ctx = resolve_gene("K-RAS", settings, offline=True, fetcher=fetcher)
    assert ctx.symbol == "KRAS"
