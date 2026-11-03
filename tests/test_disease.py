# tests/test_disease.py
import json

from target_profile.analysis.disease import analyze_disease
from target_profile.config import Settings
from target_profile.models import GeneContext


def _settings(tmp_path):
    ensg = tmp_path / "data" / "cache" / "ENSG00000133703"
    ensg.mkdir(parents=True)
    (ensg / "opentargets_disease.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "associatedDiseases": {
                            "count": 2262,
                            "rows": [
                                {
                                    "disease": {"id": "MONDO_0018997", "name": "Noonan syndrome"},
                                    "score": 0.8336,
                                    "datatypeScores": [
                                        {"id": "genetic_association", "score": 0.86},
                                        {"id": "literature", "score": 0.19},
                                    ],
                                },
                                {
                                    "disease": {"id": "MONDO_0005233", "name": "non-small cell lung carcinoma"},
                                    "score": 0.8035,
                                    "datatypeScores": [
                                        {"id": "somatic_mutation", "score": 0.84},
                                        {"id": "genetic_association", "score": 0.40},
                                    ],
                                },
                            ],
                        },
                        "geneticConstraint": [
                            {"constraintType": "lof", "score": 0.9998, "oe": 0.0477, "oeUpper": 0.2264},
                            {"constraintType": "syn", "score": 0.3861, "oe": 0.924, "oeUpper": 0.95},
                        ],
                    }
                }
            }
        )
    )
    gene_dir = tmp_path / "data" / "cache" / "KRAS"
    gene_dir.mkdir(parents=True)
    (gene_dir / "clinvar_search.json").write_text(
        json.dumps({"esearchresult": {"count": "628"}})
    )
    (gene_dir / "clinvar_search_pathogenic.json").write_text(
        json.dumps({"esearchresult": {"count": "216", "idlist": ["1", "2"]}})
    )
    (gene_dir / "clinvar_summary_pathogenic.json").write_text(
        json.dumps(
            {
                "result": {
                    "uids": ["1", "2"],
                    "1": {
                        "title": "NM_004985.5(KRAS):c.34G>T (p.Gly12Cys)",
                        "germline_classification": {"description": "Pathogenic", "review_status": "reviewed by expert panel"},
                    },
                    "2": {
                        "title": "NM_004985.5(KRAS):c.173C>T (p.Thr58Ile)",
                        "germline_classification": {"description": "Uncertain significance", "review_status": "criteria provided, single submitter"},
                    },
                }
            }
        )
    )
    return Settings(lake_root=tmp_path / "lake", data_root=tmp_path / "data", out_root=tmp_path / "out")


def test_disease_facts(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703")
    result = analyze_disease(ctx, _settings(tmp_path), offline=True)
    assert result.status == "ok"
    assert result.facts["disease_count"] == 2262
    assert result.facts["top_disease"] == "Noonan syndrome"
    assert result.facts["top_disease_score"] == 0.834
    assert result.facts["pli"] == 0.9998
    assert result.facts["loeuf"] == 0.2264
    assert result.facts["constrained"] == "Yes"
    assert result.facts["clinvar_total"] == 628
    assert result.facts["clinvar_pathogenic_submissions"] == 216
    assert result.facts["clinvar_top_variant"].startswith("NM_004985.5(KRAS):c.34G")
    # 只有聚合分类为 Pathogenic 的记录进入表格
    assert len(result.tables["clinvar"]) == 1
    assert set(result.tables["datasources"]["datasource"]) == {
        "Genetic association",
        "Literature",
        "Somatic mutation",
    }


def test_disease_all_null_disease_rows_degrades(tmp_path):
    ensg = tmp_path / "data" / "cache" / "ENSG00000133703"
    ensg.mkdir(parents=True)
    (ensg / "opentargets_disease.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "associatedDiseases": {
                            "count": 1,
                            "rows": [
                                {"disease": None, "score": 0.8, "datatypeScores": []}
                            ],
                        },
                        "geneticConstraint": [],
                    }
                }
            }
        )
    )
    # ClinVar absent in offline mode -> fetch fails -> caveat, no tables
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703")
    result = analyze_disease(
        ctx,
        Settings(lake_root=tmp_path / "lake", data_root=tmp_path / "data", out_root=tmp_path / "out"),
        offline=True,
    )
    assert result.status == "no_data"
