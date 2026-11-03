import json

from target_profile.analysis.ptm import analyze_ptm
from target_profile.config import Settings
from target_profile.models import GeneContext


def _feature(ftype, start, end, description):
    return {
        "type": ftype,
        "location": {
            "start": {"value": start, "modifier": "EXACT"},
            "end": {"value": end, "modifier": "EXACT"},
        },
        "description": description,
    }


def _settings(tmp_path):
    global_dir = tmp_path / "data" / "cache" / "_global"
    global_dir.mkdir(parents=True)
    (global_dir / "uniprot_P01116.json").write_text(
        json.dumps(
            {
                "sequence": {"length": 189},
                "features": [
                    _feature("Modified residue", 104, 104, "N6-acetyllysine"),
                    _feature("Modified residue", 186, 186, "Cysteine methyl ester"),
                    _feature("Lipidation", 186, 186, "S-farnesyl cysteine"),
                    _feature("Region", 166, 185, "Hypervariable region"),
                    _feature("Binding site", 10, 18, "GTP"),
                ],
            }
        )
    )
    return Settings(lake_root=tmp_path / "lake", data_root=tmp_path / "data", out_root=tmp_path / "out")


def test_ptm_facts(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703", uniprot_id="P01116")
    result = analyze_ptm(ctx, _settings(tmp_path), offline=True)
    assert result.status == "ok"
    assert result.facts["sequence_length"] == 189
    assert result.facts["n_ptm_sites"] == 3
    assert result.facts["top_ptm_type"] == "Modified residue"
    assert result.facts["n_domains"] == 1
    assert result.facts["domain_summary"] == "Hypervariable region (166-185)"
    assert len(result.tables["ptm_sites"]) == 3


def test_ptm_without_uniprot_degrades(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703")
    result = analyze_ptm(ctx, _settings(tmp_path), offline=True)
    assert result.status == "no_data"
