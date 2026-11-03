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
