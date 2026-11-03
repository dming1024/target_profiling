import pandas as pd

from target_profile.analysis.mutation import analyze_mutation
from target_profile.config import Settings
from target_profile.models import GeneContext


class FakeFetcher:
    def request_json(self, *args, **kwargs):
        raise AssertionError("offline path must not fetch")


def _settings(tmp_path):
    cache = tmp_path / "data" / "cache" / "KRAS"
    cache.mkdir(parents=True)
    (cache / "cbioportal_studies.json").write_text(
        '[{"studyId": "tcga_pan_can_atlas_2018_luad", "name": "Lung Adenocarcinoma (TCGA, PanCancer Atlas)", "allSampleCount": 100},'
        ' {"studyId": "tcga_pan_can_atlas_2018_paad", "name": "Pancreatic Adenocarcinoma (TCGA, PanCancer Atlas)", "allSampleCount": 40}]'
    )
    for study, sample_list, mutations in [
        (
            "tcga_pan_can_atlas_2018_luad",
            "luad_all",
            [
                {"sampleId": "S1", "proteinChange": "G12C", "mutationType": "Missense_Mutation"},
                {"sampleId": "S2", "proteinChange": "G12C", "mutationType": "Missense_Mutation"},
            ],
        ),
        (
            "tcga_pan_can_atlas_2018_paad",
            "paad_all",
            [{"sampleId": "S3", "proteinChange": "G12D", "mutationType": "Missense_Mutation"}],
        ),
    ]:
        (cache / f"cbioportal_{study}_samplelists.json").write_text(
            f'[{{"sampleListId": "{sample_list}", "category": "all_cases_in_study"}}]'
        )
        import json

        (cache / f"cbioportal_{study}_mutations.json").write_text(json.dumps(mutations))
    return Settings(lake_root=tmp_path / "lake", data_root=tmp_path / "data", out_root=tmp_path / "out")


def test_mutation_facts(tmp_path):
    ctx = GeneContext(symbol="KRAS", ensembl_id="ENSG00000133703", entrez_id="3845")
    result = analyze_mutation(ctx, _settings(tmp_path), offline=True)
    assert result.status == "ok"
    assert result.facts["n_samples"] == 140
    assert result.facts["n_mutated_samples"] == 3
    assert result.facts["overall_freq_pct"] == 2.14
    assert result.facts["top_cancer"] == "Pancreatic Adenocarcinoma"
    assert result.facts["top_protein_change"] == "G12C"
