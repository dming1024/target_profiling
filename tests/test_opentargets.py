import json

from target_profile.api.cache import CachedFetcher
from target_profile.api.opentargets import (
    target_basic,
    target_cancer,
    target_disease,
    target_pathways,
    target_safety,
    target_tractability,
)


def test_target_basic_reads_cache(tmp_path):
    cache = tmp_path / "ENSG00000133703"
    cache.mkdir(parents=True)
    (cache / "opentargets_basic.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "id": "ENSG00000133703",
                        "approvedName": "KRAS proto-oncogene, GTPase",
                        "targetClass": [{"label": "Enzyme", "level": "l1"}, {"label": "Hydrolase", "level": "l2"}],
                        "subcellularLocations": [{"location": "Cytoplasm"}],
                        "synonyms": [{"label": "K-Ras", "source": "uniprot"}],
                    }
                }
            }
        )
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    details = target_basic("ENSG00000133703", fetcher)
    assert details["approvedName"].startswith("KRAS")
    assert details["targetClass"][0]["label"] == "Enzyme"


def test_target_pathways_reads_cache(tmp_path):
    cache = tmp_path / "ENSG00000133703"
    cache.mkdir(parents=True)
    (cache / "opentargets_pathways.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "id": "ENSG00000133703",
                        "pathways": [
                            {"pathwayId": "R-HSA-1", "pathway": "Signalling to RAS", "topLevelTerm": "Signal Transduction"},
                            {"pathwayId": "R-HSA-2", "pathway": "RAF/MAP kinase cascade", "topLevelTerm": "Signal Transduction"},
                        ],
                        "geneOntology": [
                            {"aspect": "C", "evidence": "TAS", "term": {"id": "GO:1", "label": "plasma membrane"}},
                            {"aspect": "P", "evidence": "IEA", "term": {"id": "GO:2", "label": "Ras signaling"}},
                        ],
                    }
                }
            }
        )
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    details = target_pathways("ENSG00000133703", fetcher)
    assert len(details["pathways"]) == 2
    assert details["geneOntology"][0]["aspect"] == "C"


def test_target_disease_reads_cache(tmp_path):
    cache = tmp_path / "ENSG00000133703"
    cache.mkdir(parents=True)
    (cache / "opentargets_disease.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "associatedDiseases": {
                            "count": 2,
                            "rows": [
                                {"disease": {"id": "MONDO_0018997", "name": "Noonan syndrome"}, "score": 0.83, "datatypeScores": [{"id": "genetic_association", "score": 0.9}]}
                            ],
                        },
                        "geneticConstraint": [{"constraintType": "lof", "score": 0.99, "oe": 0.05, "oeUpper": 0.22}],
                    }
                }
            }
        )
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    details = target_disease("ENSG00000133703", fetcher)
    assert details["associatedDiseases"]["count"] == 2
    assert details["geneticConstraint"][0]["constraintType"] == "lof"


def test_target_tractability_reads_cache(tmp_path):
    cache = tmp_path / "ENSG00000133703"
    cache.mkdir(parents=True)
    (cache / "opentargets_tractability.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "tractability": [{"modality": "SM", "label": "Approved Drug", "value": True}],
                        "chemicalProbes": [{"id": "ARS-1620", "drugId": "CHEMBL4214264", "mechanismOfAction": ["inhibitor"], "isHighQuality": False}],
                        "drugAndClinicalCandidates": {"count": 1, "rows": []},
                    }
                }
            }
        )
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    details = target_tractability("ENSG00000133703", fetcher)
    assert details["tractability"][0]["modality"] == "SM"
    assert details["chemicalProbes"][0]["id"] == "ARS-1620"


def test_target_safety_reads_cache(tmp_path):
    cache = tmp_path / "ENSG00000133703"
    cache.mkdir(parents=True)
    (cache / "opentargets_safety.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "safetyLiabilities": [],
                        "mousePhenotypes": [{"modelPhenotypeLabel": "small liver", "modelPhenotypeClasses": [{"id": "MP:0005370", "label": "liver/biliary system phenotype"}]}],
                        "geneticConstraint": [{"constraintType": "lof", "score": 0.99, "oeUpper": 0.22}],
                        "isEssential": True,
                        "homologues": [],
                    }
                }
            }
        )
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    details = target_safety("ENSG00000133703", fetcher)
    assert details["isEssential"] is True
    assert details["mousePhenotypes"][0]["modelPhenotypeLabel"] == "small liver"


def test_target_cancer_reads_cache(tmp_path):
    cache = tmp_path / "ENSG00000133703"
    cache.mkdir(parents=True)
    (cache / "opentargets_cancer.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "id": "ENSG00000133703",
                        "hallmarks": {
                            "attributes": [{"name": "role in cancer"}],
                            "cancerHallmarks": [
                                {"label": "proliferative signalling", "impact": "promotes"},
                                {"label": "proliferative signalling", "impact": "promotes"},
                                {"label": "invasion and metastasis", "impact": "suppresses"},
                            ],
                        },
                    }
                }
            }
        )
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    details = target_cancer("ENSG00000133703", fetcher)
    assert details["hallmarks"]["cancerHallmarks"][0]["label"] == "proliferative signalling"
