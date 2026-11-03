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
