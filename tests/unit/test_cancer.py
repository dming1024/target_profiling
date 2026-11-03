import json

import pandas as pd

from target_profile.analysis.cancer import analyze_cancer
from target_profile.config import Settings
from target_profile.models import GeneContext, ModuleResult

ENSG = "ENSG00000133703"


def _settings(tmp_path, hallmarks, essential=True):
    ensg = tmp_path / "data" / "cache" / ENSG
    ensg.mkdir(parents=True)
    (ensg / "opentargets_cancer.json").write_text(
        json.dumps(
            {
                "data": {
                    "target": {
                        "id": ENSG,
                        "hallmarks": {
                            "attributes": [{"name": "role in cancer"}],
                            "cancerHallmarks": hallmarks,
                        },
                    }
                }
            }
        )
    )
    (ensg / "opentargets_safety.json").write_text(
        json.dumps(
            {"data": {"target": {"id": ENSG, "isEssential": essential, "homologues": []}}}
        )
    )
    return Settings(lake_root=tmp_path / "lake", data_root=tmp_path / "data", out_root=tmp_path / "out")


def _hallmarks():
    return [
        {"label": "proliferative signalling", "impact": "promotes"},
        {"label": "proliferative signalling", "impact": "promotes"},
        {"label": "invasion and metastasis", "impact": "suppresses"},
    ]


def test_cancer_facts_and_table(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id=ENSG)
    prior = {"mutation": ModuleResult(name="mutation", facts={"overall_freq_pct": 6.96})}
    result = analyze_cancer(ctx, _settings(tmp_path, _hallmarks()), offline=True, prior=prior)
    assert result.status == "ok"
    assert result.facts["n_cancer_hallmarks"] == 2
    assert result.facts["top_hallmark"] == "proliferative signalling"
    assert result.facts["essential"] == "Yes"
    assert result.facts["pan_cancer_freq_pct"] == 6.96
    assert result.facts["driver_status"] == "驱动证据阳性"
    assert any("规则推导" in caveat for caveat in result.caveats)
    frame = result.tables["hallmarks"]
    assert frame.iloc[0]["promotes"] == 1
    assert frame.iloc[0]["suppresses"] == 0
    assert frame.iloc[1]["suppresses"] == 1


def test_cancer_driver_negative_when_below_threshold_and_no_hallmarks(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id=ENSG)
    prior = {"mutation": ModuleResult(name="mutation", facts={"overall_freq_pct": 1.2})}
    result = analyze_cancer(ctx, _settings(tmp_path, []), offline=True, prior=prior)
    assert result.facts["driver_status"] == "证据不足"


def test_cancer_marks_positive_from_hallmarks_when_freq_missing(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id=ENSG)
    result = analyze_cancer(ctx, _settings(tmp_path, _hallmarks()), offline=True, prior={})
    assert result.facts["pan_cancer_freq_pct"] is None
    assert result.facts["driver_status"] == "驱动证据阳性"
