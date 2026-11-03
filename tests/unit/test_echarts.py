import json

import pandas as pd

from target_profile.figures.chart_specs import (
    build_cancer,
    build_comparative,
    build_dependency,
    build_disease,
    build_expression,
    build_mutation,
    build_pathway,
    build_ptm,
    build_safety,
    build_tractability,
)
from target_profile.models import ModuleResult


def _result(name, tables=None, facts=None):
    result = ModuleResult(name=name)
    result.tables.update(tables or {})
    result.facts.update(facts or {})
    return result


def test_expression_builders():
    result = _result(
        "expression",
        {
            "gtex": pd.DataFrame({"Tissue": ["Lung", "Liver"], "median": [10.0, 2.0]}),
            "depmap_lineage": pd.DataFrame(
                {"OncotreeLineage": ["Lung", "Bowel"], "median": [5.0, 6.0], "count": [10, 8]}
            ),
        },
    )
    specs = build_expression(result)
    assert [spec.id for spec in specs] == ["expression-gtex", "expression-depmap"]
    assert specs[0].option["yAxis"]["data"] == ["Lung", "Liver"]
    assert specs[0].option["series"][0]["data"] == [10.0, 2.0]
    json.dumps(specs[0].option)


def test_expression_empty_state():
    specs = build_expression(_result("expression"))
    assert specs[0].option["graphic"]["style"]["text"] == "No data available"
    assert specs[0].option["series"] == []


def test_mutation_builders():
    result = _result(
        "mutation",
        {
            "cancers": pd.DataFrame(
                {"cancer": ["LUAD", "PAAD"], "freq_pct": [30.0, 60.0]}
            ),
            "protein_changes": pd.DataFrame(
                {"proteinChange": ["G12D", "G12C"], "count": [20, 10]}
            ),
        },
    )
    specs = build_mutation(result)
    assert [spec.id for spec in specs] == ["mutation-cancers", "mutation-proteins"]
    assert specs[0].option["series"][0]["data"] == [30.0, 60.0]
    assert specs[0].option["xAxis"]["axisLabel"]["formatter"] == "{value}%"


def test_dependency_histogram():
    result = _result(
        "dependency",
        {
            "distribution": pd.DataFrame({"effect": [-1.5, -0.5, 0.0, 0.2]}),
            "by_lineage": pd.DataFrame(
                {"OncotreeLineage": ["Lung", "Bowel"], "median": [-0.8, -0.2], "count": [10, 8]}
            ),
        },
    )
    specs = build_dependency(result)
    assert specs[0].id == "dependency-dist"
    assert len(specs[0].option["xAxis"]["data"]) == 30
    assert sum(specs[0].option["series"][0]["data"]) == 4


def test_pathway_graph():
    result = _result(
        "pathway",
        {
            "top_levels": pd.DataFrame(
                {"topLevelTerm": ["Signal Transduction", "Disease"], "count": [36, 24]}
            ),
            "partners": pd.DataFrame(
                {"preferredName_B": ["RAF1", "PIK3CA"], "score": [0.99, 0.95]}
            ),
        },
        {"symbol": "KRAS"},
    )
    specs = build_pathway(result)
    assert specs[1].id == "pathway-network"
    graph = specs[1].option["series"][0]
    assert len(graph["data"]) == 3
    assert len(graph["links"]) == 2
    assert graph["data"][0]["name"] == "KRAS"


def test_all_builder_options_are_json_serialisable():
    populated = [
        (
            build_expression,
            _result(
                "expression",
                {
                    "gtex": pd.DataFrame({"Tissue": ["Lung", "Liver"], "median": [10.0, 2.0]}),
                    "depmap_lineage": pd.DataFrame(
                        {
                            "OncotreeLineage": ["Lung", "Bowel"],
                            "median": [5.0, 6.0],
                            "count": [10, 8],
                        }
                    ),
                },
            ),
        ),
        (
            build_mutation,
            _result(
                "mutation",
                {
                    "cancers": pd.DataFrame(
                        {"cancer": ["LUAD", "PAAD"], "freq_pct": [30.0, 60.0]}
                    ),
                    "protein_changes": pd.DataFrame(
                        {"proteinChange": ["G12D", "G12C"], "count": [20, 10]}
                    ),
                },
            ),
        ),
        (
            build_dependency,
            _result(
                "dependency",
                {
                    "distribution": pd.DataFrame({"effect": [-1.5, -0.5, 0.0, 0.2]}),
                    "by_lineage": pd.DataFrame(
                        {
                            "OncotreeLineage": ["Lung", "Bowel"],
                            "median": [-0.8, -0.2],
                            "count": [10, 8],
                        }
                    ),
                },
            ),
        ),
        (
            build_pathway,
            _result(
                "pathway",
                {
                    "top_levels": pd.DataFrame(
                        {"topLevelTerm": ["Signal Transduction", "Disease"], "count": [36, 24]}
                    ),
                    "partners": pd.DataFrame(
                        {"preferredName_B": ["RAF1", "PIK3CA"], "score": [0.99, 0.95]}
                    ),
                },
                {"symbol": "KRAS"},
            ),
        ),
        (
            build_ptm,
            _result(
                "ptm",
                {
                    "ptm_types": pd.DataFrame(
                        {"type": ["Modified residue", "Lipidation"], "count": [2, 1]}
                    ),
                    "ptm_sites": pd.DataFrame(
                        {
                            "type": ["Modified residue", "Modified residue", "Lipidation"],
                            "position": [104, 186, 186],
                            "end": [104, 186, 186],
                        }
                    ),
                    "domains": pd.DataFrame(
                        {
                            "type": ["Region"],
                            "name": ["Hypervariable region"],
                            "start": [166],
                            "end": [185],
                        }
                    ),
                },
                {"sequence_length": 189},
            ),
        ),
        (
            build_disease,
            _result(
                "disease",
                {
                    "diseases": pd.DataFrame(
                        {"disease": ["Noonan syndrome", "NSCLC"], "score": [0.83, 0.8]}
                    ),
                    "datasources": pd.DataFrame(
                        {"datasource": ["Genetic association", "Literature"], "diseases": [2, 2]}
                    ),
                },
            ),
        ),
        (
            build_tractability,
            _result(
                "tractability",
                {
                    "tractability": pd.DataFrame(
                        {
                            "modality": ["Small molecule", "Small molecule", "Antibody"],
                            "bucket": ["Approved Drug", "Structure with Ligand", "Advanced Clinical"],
                            "available": [True, True, True],
                        }
                    ),
                    "drug_stages": pd.DataFrame(
                        {"stage": ["Approved", "Phase 2"], "count": [1, 1]}
                    ),
                },
            ),
        ),
        (
            build_safety,
            _result(
                "safety",
                {
                    "mouse_phenotypes": pd.DataFrame(
                        {
                            "phenotype_class": ["cardiovascular system phenotype"],
                            "models": [22],
                        }
                    ),
                    "expression_breadth": pd.DataFrame(
                        {"tissue": ["Lung", "Liver"], "median": [12.0, 2.0]}
                    ),
                },
            ),
        ),
        (
            build_cancer,
            _result(
                "cancer",
                {
                    "hallmarks": pd.DataFrame(
                        {
                            "label": ["proliferative signalling", "invasion and metastasis"],
                            "promotes": [2, 1],
                            "suppresses": [0, 1],
                            "total": [2, 2],
                        }
                    )
                },
            ),
        ),
        (
            build_comparative,
            _result(
                "comparative",
                {
                    "homologues": pd.DataFrame(
                        {
                            "species": ["Chimpanzee", "Mouse"],
                            "type": ["ortholog", "ortholog"],
                            "identity": [99.5, 88.1],
                        }
                    )
                },
            ),
        ),
    ]
    builders = [
        build_expression,
        build_mutation,
        build_dependency,
        build_pathway,
        build_ptm,
        build_disease,
        build_tractability,
        build_safety,
        build_cancer,
        build_comparative,
    ]

    for builder, result in populated:
        for spec in builder(result):
            serialised = json.dumps(spec.option, allow_nan=False)
            assert isinstance(serialised, str)

    for builder in builders:
        for spec in builder(_result(builder.__name__)):
            serialised = json.dumps(spec.option, allow_nan=False)
            assert isinstance(serialised, str)


def test_ptm_lollipop_with_domains():
    result = _result(
        "ptm",
        {
            "ptm_types": pd.DataFrame(
                {"type": ["Modified residue", "Lipidation"], "count": [2, 1]}
            ),
            "ptm_sites": pd.DataFrame(
                {
                    "type": ["Modified residue", "Modified residue", "Lipidation"],
                    "position": [104, 186, 186],
                    "end": [104, 186, 186],
                }
            ),
            "domains": pd.DataFrame(
                {"type": ["Region"], "name": ["Hypervariable region"], "start": [166], "end": [185]}
            ),
        },
        {"sequence_length": 189},
    )
    specs = build_ptm(result)
    assert [spec.id for spec in specs] == ["ptm-types", "ptm-sites"]
    assert len(specs[1].option["series"]) == 2
    assert specs[1].option["series"][0]["markArea"]["data"] == [[{"xAxis": 166}, {"xAxis": 185}]]
    assert specs[1].option["xAxis"]["max"] == 191


def test_disease_builders():
    result = _result(
        "disease",
        {
            "diseases": pd.DataFrame(
                {"disease": ["Noonan syndrome", "NSCLC"], "score": [0.83, 0.8]}
            ),
            "datasources": pd.DataFrame(
                {"datasource": ["Genetic association", "Literature"], "diseases": [2, 2]}
            ),
        },
    )
    specs = build_disease(result)
    assert [spec.id for spec in specs] == ["disease-top", "disease-sources"]


def test_tractability_heatmap():
    result = _result(
        "tractability",
        {
            "tractability": pd.DataFrame(
                {
                    "modality": ["Small molecule", "Small molecule", "Antibody"],
                    "bucket": ["Approved Drug", "Structure with Ligand", "Advanced Clinical"],
                    "available": [True, True, True],
                }
            ),
            "drug_stages": pd.DataFrame({"stage": ["Approved", "Phase 2"], "count": [1, 1]}),
        },
    )
    specs = build_tractability(result)
    heatmap = specs[0]
    assert heatmap.id == "tractability-heat"
    assert len(heatmap.option["series"][0]["data"]) == 6  # 2 modalities x 3 buckets
    assert specs[1].id == "tractability-stages"


def test_safety_builders():
    result = _result(
        "safety",
        {
            "mouse_phenotypes": pd.DataFrame(
                {"phenotype_class": ["cardiovascular system phenotype"], "models": [22]}
            ),
            "expression_breadth": pd.DataFrame(
                {"tissue": ["Lung", "Liver"], "median": [12.0, 2.0]}
            ),
        },
    )
    specs = build_safety(result)
    assert [spec.id for spec in specs] == ["safety-mouse", "safety-breadth"]


def test_cancer_hallmarks_stacked():
    result = _result(
        "cancer",
        {
            "hallmarks": pd.DataFrame(
                {
                    "label": ["proliferative signalling", "invasion and metastasis"],
                    "promotes": [2, 1],
                    "suppresses": [0, 1],
                    "total": [2, 2],
                }
            )
        },
    )
    specs = build_cancer(result)
    assert specs[0].id == "cancer-hallmarks"
    assert [series["name"] for series in specs[0].option["series"]] == ["promotes", "suppresses"]
    assert specs[0].option["yAxis"]["data"] == ["proliferative signalling", "invasion and metastasis"]


def test_comparative_identity():
    result = _result(
        "comparative",
        {
            "homologues": pd.DataFrame(
                {
                    "species": ["Chimpanzee", "Mouse"],
                    "type": ["ortholog", "ortholog"],
                    "identity": [99.5, 88.1],
                }
            )
        },
    )
    specs = build_comparative(result)
    assert specs[0].id == "comparative-identity"
    assert specs[0].option["series"][0]["data"] == [99.5, 88.1]
    assert specs[0].option["xAxis"]["axisLabel"]["formatter"] == "{value}%"
