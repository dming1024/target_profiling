import json
import re
import socket

import pandas as pd
from typer.testing import CliRunner

from target_profile.cli import app


def _build_home(tmp_path):
    home = tmp_path / "home"
    (home / "config").mkdir(parents=True)
    (home / "config/settings.toml").write_text(
        f'lake_root = "{tmp_path}/lake"\ndata_root = "data"\nout_root = "out"\n',
        encoding="utf-8",
    )
    parquet = home / "data" / "parquet"
    parquet.mkdir(parents=True)
    pd.DataFrame(
        {
            "gene_id": ["ENSG00000133703", "ENSG00000141510"],
            "gene_name": ["KRAS", "TP53"],
            "chr": ["12", "17"],
            "gene_start": [25205246, 7661779],
            "gene_end": [25250936, 7687538],
            "gene_type": ["protein_coding", "protein_coding"],
        }
    ).to_parquet(parquet / "gene_info.parquet", index=False)
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
            "KRAS (3845)": [-1.5, -0.8, -0.1],
            "TP53 (7157)": [-0.2, -0.1, -0.3],
        }
    ).to_parquet(parquet / "depmap_gene_effect.parquet", index=False)
    pd.DataFrame(
        {"ModelID": ["ACH-1", "ACH-2", "ACH-3"], "KRAS (3845)": [5.0, 6.0, 7.0]}
    ).to_parquet(parquet / "depmap_expression.parquet", index=False)
    pd.DataFrame(
        {
            "ModelID": ["ACH-1", "ACH-2", "ACH-3"],
            "CellLineName": ["A", "B", "C"],
            "OncotreeLineage": ["Lung", "Lung", "Bowel"],
            "OncotreePrimaryDisease": ["LUAD", "LUAD", "COAD"],
        }
    ).to_parquet(parquet / "depmap_model.parquet", index=False)
    pd.DataFrame({"Gene": ["KRAS", "TP53"], "RNA tissue specificity": ["all", "all"]}).to_parquet(
        parquet / "hpa.parquet", index=False
    )
    for gene, study, sample_list, mutation in [
        ("KRAS", "tcga_pan_can_atlas_2018_luad", "luad_all", "G12C"),
        ("TP53", "tcga_pan_can_atlas_2018_luad", "luad_all", "R175H"),
    ]:
        cache = home / "data" / "cache" / gene
        cache.mkdir(parents=True)
        (cache / "cbioportal_studies.json").write_text(
            '[{"studyId": "tcga_pan_can_atlas_2018_luad", "name": "Lung Adenocarcinoma (TCGA, PanCancer Atlas)", "allSampleCount": 100}]'
        )
        (cache / f"cbioportal_{study}_samplelists.json").write_text(
            f'[{{"sampleListId": "{sample_list}", "category": "all_cases_in_study"}}]'
        )
        (cache / f"cbioportal_{study}_mutations.json").write_text(
            json.dumps([{"sampleId": "S1", "proteinChange": mutation, "mutationType": "Missense_Mutation"}])
        )
    for gene, ensg, acc in [
        ("KRAS", "ENSG00000133703", "P01116"),
        ("TP53", "ENSG00000141510", "P04637"),
    ]:
        ensg_dir = home / "data" / "cache" / ensg
        ensg_dir.mkdir(parents=True)
        (ensg_dir / "opentargets_target.json").write_text(
            json.dumps(
                {
                    "data": {
                        "target": {
                            "id": ensg,
                            "proteinIds": [{"id": acc, "source": "uniprot_swissprot"}],
                        }
                    }
                }
            )
        )
        (ensg_dir / "opentargets_basic.json").write_text(
            json.dumps(
                {
                    "data": {
                        "target": {
                            "approvedName": gene,
                            "targetClass": [{"label": "Enzyme"}],
                            "subcellularLocations": [{"location": "Cytoplasm"}],
                            "synonyms": [{"label": gene}],
                        }
                    }
                }
            )
        )
        (ensg_dir / "opentargets_pathways.json").write_text(
            json.dumps(
                {
                    "data": {
                        "target": {
                            "pathways": [
                                {"pathwayId": "R-HSA-1", "pathway": "Signalling to RAS", "topLevelTerm": "Signal Transduction"}
                            ],
                            "geneOntology": [
                                {"aspect": "C", "evidence": "TAS", "term": {"id": "GO:0005886", "label": "plasma membrane"}}
                            ],
                        }
                    }
                }
            )
        )
        (home / "data" / "cache" / gene / "string_partners.json").write_text(
            json.dumps([{"preferredName_B": "RAF1", "score": 0.99}])
        )
        global_dir = home / "data" / "cache" / "_global"
        global_dir.mkdir(parents=True, exist_ok=True)
        (global_dir / f"uniprot_{acc}.json").write_text(
            json.dumps(
                {
                    "sequence": {"length": 189},
                    "proteinDescription": {"recommendedName": {"fullName": {"value": gene}}},
                    "comments": [],
                    "features": [
                        {
                            "type": "Modified residue",
                            "location": {
                                "start": {"value": 10, "modifier": "EXACT"},
                                "end": {"value": 10, "modifier": "EXACT"},
                            },
                            "description": "N6-acetyllysine",
                        }
                    ],
                }
            )
        )
        (global_dir / f"alphafold_{acc}.json").write_text(
            json.dumps([{"globalMetricValue": 90.0}])
        )
        (ensg_dir / "opentargets_disease.json").write_text(
            json.dumps(
                {
                    "data": {
                        "target": {
                            "associatedDiseases": {
                                "count": 1,
                                "rows": [
                                    {
                                        "disease": {"id": "MONDO_1", "name": "Noonan syndrome"},
                                        "score": 0.8,
                                        "datatypeScores": [{"id": "genetic_association", "score": 0.9}],
                                    }
                                ],
                            },
                            "geneticConstraint": [
                                {"constraintType": "lof", "score": 0.99, "oe": 0.05, "oeUpper": 0.22}
                            ],
                        }
                    }
                }
            )
        )
        (ensg_dir / "opentargets_tractability.json").write_text(
            json.dumps(
                {
                    "data": {
                        "target": {
                            "tractability": [
                                {"modality": "SM", "label": "Approved Drug", "value": True}
                            ],
                            "chemicalProbes": [],
                            "drugAndClinicalCandidates": {
                                "count": 1,
                                "rows": [
                                    {
                                        "id": "d1",
                                        "maxClinicalStage": "APPROVAL",
                                        "drug": {"id": "CHEMBL1", "name": "SOTORASIB"},
                                        "diseases": [{"disease": {"id": "MONDO_1", "name": "NSCLC"}}],
                                    }
                                ],
                            },
                        }
                    }
                }
            )
        )
        (ensg_dir / "opentargets_safety.json").write_text(
            json.dumps(
                {
                    "data": {
                        "target": {
                            "safetyLiabilities": [],
                            "mousePhenotypes": [
                                {
                                    "modelPhenotypeLabel": "small liver",
                                    "modelPhenotypeClasses": [{"id": "MP:1", "label": "liver/biliary system phenotype"}],
                                }
                            ],
                            "geneticConstraint": [{"constraintType": "lof", "score": 0.99, "oeUpper": 0.22}],
                            "isEssential": False,
                            "homologues": [
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
                            ],
                        }
                    }
                }
            )
        )
        (ensg_dir / "opentargets_cancer.json").write_text(
            json.dumps(
                {
                    "data": {
                        "target": {
                            "id": ensg,
                            "hallmarks": {
                                "attributes": [{"name": "role in cancer"}],
                                "cancerHallmarks": [
                                    {"label": "proliferative signalling", "impact": "promotes"},
                                    {"label": "invasion and metastasis", "impact": "promotes"},
                                ],
                            },
                        }
                    }
                }
            )
        )
        (home / "data" / "cache" / gene / "clinvar_search.json").write_text(
            json.dumps({"esearchresult": {"count": "10"}})
        )
        (home / "data" / "cache" / gene / "clinvar_search_pathogenic.json").write_text(
            json.dumps({"esearchresult": {"count": "2", "idlist": ["1", "2"]}})
        )
        (home / "data" / "cache" / gene / "clinvar_summary_pathogenic.json").write_text(
            json.dumps(
                {
                    "result": {
                        "uids": ["1", "2"],
                        "1": {
                            "title": f"{gene} variant 1",
                            "germline_classification": {"description": "Pathogenic", "review_status": "reviewed by expert panel"},
                        },
                        "2": {
                            "title": f"{gene} variant 2",
                            "germline_classification": {"description": "Uncertain significance", "review_status": "criteria provided, single submitter"},
                        },
                    }
                }
            )
        )
    return home


def test_full_chain_offline(tmp_path, monkeypatch):
    home = _build_home(tmp_path)
    monkeypatch.setenv("TARGET_PROFILE_HOME", str(home))

    def no_network(*args, **kwargs):
        raise RuntimeError("network disabled in test")

    monkeypatch.setattr(socket.socket, "connect", no_network)

    for gene in ["KRAS", "TP53"]:
        result = CliRunner().invoke(app, ["run", gene, "--offline", "--no-llm", "--format", "html"])
        assert result.exit_code == 0, result.output
        out_dir = next((home / "out").glob(f"{gene}_*"))
        html = (out_dir / "report.html").read_text(encoding="utf-8")
        facts = json.loads((out_dir / "facts.json").read_text(encoding="utf-8"))
        assert facts["gene"]["symbol"] == gene
        assert 'id="chart-data"' in html
        assert "echarts" in html.lower()
        assert "data:font/woff2;base64," in html
        assert 'src="http' not in html
        assert 'href="http' not in html
        assert facts["modules"]["expression"]["status"] == "ok"
        assert facts["modules"]["mutation"]["status"] == "ok"
        assert facts["modules"]["dependency"]["status"] == "ok"
        assert facts["modules"]["basic"]["status"] == "ok"
        assert facts["modules"]["pathway"]["status"] == "ok"
        assert facts["modules"]["ptm"]["status"] == "ok"
        assert facts["modules"]["disease"]["status"] == "ok"
        assert facts["modules"]["tractability"]["status"] == "ok"
        assert facts["modules"]["safety"]["status"] == "ok"
        assert facts["modules"]["cancer"]["status"] == "ok"
        assert facts["modules"]["comparative"]["status"] == "ok"
        assert facts["modules"]["summary"]["status"] == "ok"


def test_report_is_self_contained(tmp_path, monkeypatch):
    home = _build_home(tmp_path)
    monkeypatch.setenv("TARGET_PROFILE_HOME", str(home))
    result = CliRunner().invoke(app, ["run", "KRAS", "--offline", "--no-llm"])
    assert result.exit_code == 0, result.output
    out_dir = next((home / "out").glob("KRAS_*"))
    html = (out_dir / "report.html").read_text(encoding="utf-8")

    assert "echarts" in html.lower()
    assert "data:font/woff2;base64," in html
    assert not re.search(r'(src|href)\s*=\s*["\']https?://', html)
    assert "url(http" not in html
    assert "@import url(http" not in html

    payload = json.loads(
        html.split('<script id="chart-data" type="application/json">')[1].split("</script>")[0]
    )
    assert "expression-gtex" in payload
    assert "mutation-cancers" in payload
    assert "dependency-dist" in payload
    assert "cancer-hallmarks" in payload
    assert "comparative-identity" in payload
    for entry in payload.values():
        assert "option" in entry

    for number in range(1, 13):
        assert f'id="ch-{number}"' in html
