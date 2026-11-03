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
