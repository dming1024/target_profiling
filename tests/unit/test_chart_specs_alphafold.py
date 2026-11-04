import json

import pandas as pd

from target_profile.figures.chart_specs import build_basic
from target_profile.models import ModuleResult


def _result():
    return ModuleResult(
        name="basic",
        facts={
            "alphafold_mean_plddt": 75.1,
            "alphafold_entry_id": "AF-P04637-F1",
            "alphafold_model_version": "v6",
        },
        tables={
            "alphafold_plddt": pd.DataFrame(
                {
                    "residue": [1, 2, 3],
                    "plddt": [90.0, 60.0, 30.0],
                    "category": ["A", "C", "D"],
                }
            ),
            "alphafold_categories": pd.DataFrame(
                {
                    "category": [
                        "Very high (≥90)",
                        "Confident (70–90)",
                        "Low (50–70)",
                        "Very low (<50)",
                    ],
                    "residues": [1, 0, 1, 1],
                    "pct": [52.7, 7.1, 10.4, 29.8],
                }
            ),
        },
    )


def test_build_basic_creates_both_charts():
    charts = build_basic(_result())
    assert [chart.id for chart in charts] == [
        "alphafold-residue",
        "alphafold-confidence",
    ]
    for chart in charts:
        json.dumps(chart.option, allow_nan=False)


def test_residue_chart_has_confidence_bands():
    chart = build_basic(_result())[0]
    series = chart.option["series"][0]
    assert series["data"] == [[1, 90.0], [2, 60.0], [3, 30.0]]
    assert len(series["markArea"]["data"]) == 4
    assert chart.option["yAxis"]["max"] == 100


def test_confidence_chart_uses_category_colors():
    chart = build_basic(_result())[1]
    data = chart.option["series"][0]["data"]
    assert data[0]["name"] == "Very high (≥90)"
    assert data[0]["itemStyle"]["color"] == "#55d6be"


def test_build_basic_returns_empty_without_alphafold_data():
    assert build_basic(ModuleResult(name="basic")) == []
