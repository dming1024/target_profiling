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
