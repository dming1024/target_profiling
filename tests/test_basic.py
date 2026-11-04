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
    (global_dir / "alphafold_P01116.json").write_text(
        json.dumps(
            [
                {
                    "globalMetricValue": 91.5,
                    "fractionPlddtVeryHigh": 0.8,
                    "fractionPlddtConfident": 0.1,
                    "fractionPlddtLow": 0.05,
                    "fractionPlddtVeryLow": 0.05,
                    "entryId": "AF-P01116-F1",
                    "latestVersion": 6,
                    "uniprotStart": 1,
                    "uniprotEnd": 189,
                    "plddtDocUrl": "https://example/confidence.json",
                    "pdbUrl": "https://example/model.pdb",
                    "cifUrl": "https://example/model.cif",
                }
            ]
        )
    )
    (global_dir / "alphafold_plddt_P01116.json").write_text(
        json.dumps(
            {
                "residueNumber": [1, 2, 3, 4, 5],
                "confidenceScore": [90.0, 91.0, 92.0, 93.0, 94.0],
                "confidenceCategory": ["A", "A", "A", "A", "A"],
            }
        )
    )
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


def test_basic_alphafold_panel(tmp_path):
    ctx = GeneContext(
        symbol="KRAS",
        ensembl_id="ENSG00000133703",
        uniprot_id="P01116",
    )
    result = analyze_basic(ctx, _settings(tmp_path), offline=True)

    assert result.facts["alphafold_very_high_pct"] == 80.0
    assert result.facts["alphafold_confident_pct"] == 10.0
    assert result.facts["alphafold_low_pct"] == 5.0
    assert result.facts["alphafold_very_low_pct"] == 5.0
    assert result.facts["alphafold_entry_id"] == "AF-P01116-F1"
    assert result.facts["alphafold_model_version"] == "v6"
    assert result.facts["alphafold_coverage"] == "1–189 aa (100%)"

    categories = result.tables["alphafold_categories"]
    assert list(categories["category"])[0] == "Very high (≥90)"
    assert int(categories["residues"].iloc[0]) == 5

    plddt = result.tables["alphafold_plddt"]
    assert list(plddt.columns) == ["residue", "plddt", "category"]
    assert len(plddt) == 5

    labels = {link["label"] for link in result.links}
    assert labels == {"AlphaFold DB", "PDB", "CIF"}
    assert any("单模型逐残基置信度" in caveat for caveat in result.caveats)


def test_basic_alphafold_degrades_without_confidence_doc(tmp_path):
    settings = _settings(tmp_path)
    (tmp_path / "data" / "cache" / "_global" / "alphafold_plddt_P01116.json").unlink()
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703", uniprot_id="P01116")
    result = analyze_basic(ctx, settings, offline=True)

    assert result.status == "ok"
    assert "alphafold_plddt" not in result.tables
    assert result.tables["alphafold_categories"]["residues"].isna().all()
    assert any("逐残基置信度缓存" in caveat for caveat in result.caveats)
