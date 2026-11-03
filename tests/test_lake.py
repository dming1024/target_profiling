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
