import json

import pandas as pd
from typer.testing import CliRunner

from target_profile.cli import app


def _home(tmp_path):
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
            "gene_id": ["ENSG00000133703"],
            "gene_name": ["KRAS"],
            "chr": ["12"],
            "gene_start": [25205246],
            "gene_end": [25250936],
            "gene_type": ["protein_coding"],
        }
    ).to_parquet(parquet / "gene_info.parquet", index=False)
    pd.DataFrame(
        {"Gene": ["KRAS", "TP53"], "Tissue": ["Lung", "Lung"], "Expression": [10.0, 5.0]}
    ).to_parquet(parquet / "gtex.parquet", index=False)
    pd.DataFrame({"ModelID": ["ACH-1"], "KRAS (3845)": [-1.0]}).to_parquet(
        parquet / "depmap_gene_effect.parquet", index=False
    )
    pd.DataFrame({"ModelID": ["ACH-1"], "KRAS (3845)": [5.0]}).to_parquet(
        parquet / "depmap_expression.parquet", index=False
    )
    pd.DataFrame(
        {
            "ModelID": ["ACH-1"],
            "CellLineName": ["A"],
            "OncotreeLineage": ["Lung"],
            "OncotreePrimaryDisease": ["LUAD"],
        }
    ).to_parquet(parquet / "depmap_model.parquet", index=False)
    pd.DataFrame({"Gene": ["KRAS"], "RNA tissue specificity": ["all"]}).to_parquet(
        parquet / "hpa.parquet", index=False
    )
    cache = home / "data" / "cache" / "KRAS"
    cache.mkdir(parents=True)
    (cache / "cbioportal_studies.json").write_text(
        '[{"studyId": "tcga_pan_can_atlas_2018_luad", "name": "Lung Adenocarcinoma (TCGA, PanCancer Atlas)", "allSampleCount": 100}]'
    )
    (cache / "cbioportal_tcga_pan_can_atlas_2018_luad_samplelists.json").write_text(
        '[{"sampleListId": "luad_all", "category": "all_cases_in_study"}]'
    )
    (cache / "cbioportal_tcga_pan_can_atlas_2018_luad_mutations.json").write_text(
        '[{"sampleId": "S1", "proteinChange": "G12C", "mutationType": "Missense_Mutation"}]'
    )
    return home


def test_run_offline_produces_artifacts(tmp_path, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setenv("TARGET_PROFILE_HOME", str(home))
    result = CliRunner().invoke(
        app, ["run", "KRAS", "--offline", "--no-llm", "--format", "html"]
    )
    assert result.exit_code == 0, result.output
    out_dirs = list((home / "out").glob("KRAS_*"))
    assert out_dirs
    assert (out_dirs[0] / "report.html").exists()
    assert (out_dirs[0] / "facts.json").exists()
    facts = json.loads((out_dirs[0] / "facts.json").read_text())
    assert facts["gene"]["symbol"] == "KRAS"


def test_unknown_gene_exit_code(tmp_path, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setenv("TARGET_PROFILE_HOME", str(home))
    result = CliRunner().invoke(app, ["run", "NOTAGENE", "--offline", "--no-llm"])
    assert result.exit_code == 2


def test_run_offline_declares_new_sections(tmp_path, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setenv("TARGET_PROFILE_HOME", str(home))
    result = CliRunner().invoke(app, ["run", "KRAS", "--offline", "--no-llm"])
    assert result.exit_code == 0, result.output
    out_dir = next((home / "out").glob("KRAS_*"))
    facts = json.loads((out_dir / "facts.json").read_text())
    assert set(facts["modules"]) == {
        "basic",
        "disease",
        "expression",
        "mutation",
        "dependency",
        "cancer",
        "pathway",
        "ptm",
        "tractability",
        "safety",
        "comparative",
        "summary",
    }
    html = (out_dir / "report.html").read_text(encoding="utf-8")
    assert 'id="chart-data"' in html
    assert "echarts" in html.lower()
    assert (out_dir / "report.pdf").exists() is False  # default format is html


def test_pdf_uses_speedread_template_and_cleans_up(tmp_path, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setenv("TARGET_PROFILE_HOME", str(home))
    captured = {}

    def fake_pdf(html_path, pdf_path):
        captured["path"] = html_path
        assert html_path.name == "_print.html"
        pdf_path.write_bytes(b"%PDF-1.4\n")
        return True

    monkeypatch.setattr("target_profile.cli.html_to_pdf", fake_pdf)
    result = CliRunner().invoke(app, ["run", "KRAS", "--offline", "--no-llm", "--format", "pdf"])
    assert result.exit_code == 0, result.output
    assert captured["path"].name == "_print.html"
    assert not captured["path"].exists()


def test_pdf_failure_retains_html_and_exits_4(tmp_path, monkeypatch):
    home = _home(tmp_path)
    monkeypatch.setenv("TARGET_PROFILE_HOME", str(home))
    captured = {}

    def fake_pdf(html_path, pdf_path):
        captured["path"] = html_path
        assert html_path.name == "_print.html"
        return False

    monkeypatch.setattr("target_profile.cli.html_to_pdf", fake_pdf)
    result = CliRunner().invoke(app, ["run", "KRAS", "--offline", "--no-llm", "--format", "pdf"])
    assert result.exit_code == 4
    assert "PDF export failed; HTML retained" in result.output
    assert captured["path"].name == "_print.html"
    assert not captured["path"].exists()
    out_dir = captured["path"].parent
    assert (out_dir / "report.html").exists()
