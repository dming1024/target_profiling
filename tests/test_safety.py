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
