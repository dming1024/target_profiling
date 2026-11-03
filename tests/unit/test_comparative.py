import json

from target_profile.analysis.comparative import analyze_comparative
from target_profile.config import Settings
from target_profile.models import GeneContext

ENSG = "ENSG00000133703"


def _settings(tmp_path, homologues):
    ensg = tmp_path / "data" / "cache" / ENSG
    ensg.mkdir(parents=True)
    (ensg / "opentargets_safety.json").write_text(
        json.dumps(
            {"data": {"target": {"id": ENSG, "isEssential": False, "homologues": homologues}}}
        )
    )
    return Settings(lake_root=tmp_path / "lake", data_root=tmp_path / "data", out_root=tmp_path / "out")


def test_comparative_facts(tmp_path):
    homologues = [
        {
            "speciesName": "Chimpanzee",
            "homologyType": "ortholog",
            "targetGeneId": "ENSG00000228327",
            "queryPercentageIdentity": 99.5,
        },
        {
            "speciesName": "Human",
            "homologyType": "within_species_paralog",
            "targetGeneId": "ENSG00000126458",
            "queryPercentageIdentity": 53.7,
        },
        {
            "speciesName": "Mouse",
            "homologyType": "ortholog",
            "targetGeneId": "ENSG00000000001",
            "queryPercentageIdentity": 88.1,
        },
    ]
    ctx = GeneContext(symbol="KRAS", ensembl_id=ENSG)
    result = analyze_comparative(ctx, _settings(tmp_path, homologues), offline=True)
    assert result.status == "ok"
    assert result.facts["n_homologues"] == 3
    assert result.facts["top_homologue"] == "Chimpanzee"
    assert result.facts["top_homologue_identity"] == 99.5
    assert result.facts["top_paralogue_identity"] == 53.7
    assert list(result.tables["homologues"]["identity"]) == [99.5, 88.1, 53.7]


def test_comparative_no_homologues_degrades(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id=ENSG)
    result = analyze_comparative(ctx, _settings(tmp_path, []), offline=True)
    assert result.status == "no_data"
