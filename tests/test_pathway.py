import json

from target_profile.analysis.pathway import analyze_pathway
from target_profile.config import Settings
from target_profile.models import GeneContext


def _settings(tmp_path):
    ensg = tmp_path / "data" / "cache" / "ENSG00000133703"
    ensg.mkdir(parents=True)
    (ensg / "opentargets_pathways.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "pathways": [
                            {"pathwayId": "R-HSA-1", "pathway": "Signalling to RAS", "topLevelTerm": "Signal Transduction"},
                            {"pathwayId": "R-HSA-2", "pathway": "RAF/MAP kinase cascade", "topLevelTerm": "Signal Transduction"},
                            {"pathwayId": "R-HSA-2", "pathway": "RAF/MAP kinase cascade", "topLevelTerm": "Signal Transduction"},
                            {"pathwayId": "R-HSA-3", "pathway": "Oncogene induced senescence", "topLevelTerm": "Cellular Senescence"},
                        ],
                        "geneOntology": [
                            {"aspect": "C", "evidence": "TAS", "term": {"id": "GO:0005886", "label": "plasma membrane"}},
                            {"aspect": "C", "evidence": "IDA", "term": {"id": "GO:0005886", "label": "plasma membrane"}},
                            {"aspect": "P", "evidence": "IEA", "term": {"id": "GO:0007265", "label": "Ras protein signal transduction"}},
                            {"aspect": "F", "evidence": "IEA", "term": {"id": "GO:0003924", "label": "GTPase activity"}},
                        ],
                    }
                }
            }
        )
    )
    gene_dir = tmp_path / "data" / "cache" / "KRAS"
    gene_dir.mkdir(parents=True)
    (gene_dir / "string_partners.json").write_text(
        json.dumps(
            [
                {"preferredName_B": "RAF1", "score": 0.99},
                {"preferredName_B": "PIK3CA", "score": 0.95},
                {"preferredName_B": "RAB1A", "score": 0.6},
            ]
        )
    )
    return Settings(lake_root=tmp_path / "lake", data_root=tmp_path / "data", out_root=tmp_path / "out")


def test_pathway_facts(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703")
    result = analyze_pathway(ctx, _settings(tmp_path), offline=True)
    assert result.status == "ok"
    assert result.facts["n_pathways"] == 3
    assert result.facts["top_level_term"] == "Signal Transduction"
    assert result.facts["n_go_terms"] == 3
    assert result.facts["go_aspect_summary"] == "Cellular component 1 / Molecular function 1 / Biological process 1"
    assert result.facts["n_partners_high_conf"] == 2
    assert result.facts["top_partner"] == "RAF1"
    assert len(result.tables["partners"]) == 2
