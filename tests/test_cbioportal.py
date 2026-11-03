import pandas as pd

from target_profile.api.cache import CachedFetcher
from target_profile.api.cbioportal import fetch_pancan_mutations


class FakeClient:
    def __init__(self):
        self.calls = []

    def request(self, method, url, params=None, json=None):
        self.calls.append((method, url, json))
        if url.endswith("/studies"):
            return FakeResponse(
                [
                    {
                        "studyId": "tcga_pan_can_atlas_2018_luad",
                        "name": "Lung Adenocarcinoma (TCGA, PanCancer Atlas)",
                        "allSampleCount": 100,
                    },
                    {
                        "studyId": "tcga_pan_can_atlas_2018_paad",
                        "name": "Pancreatic Adenocarcinoma (TCGA, PanCancer Atlas)",
                        "allSampleCount": 50,
                    },
                ]
            )
        if url.endswith("/sample-lists"):
            return FakeResponse([{"sampleListId": "luad_all", "category": "all_cases_in_study"}])
        if url.endswith("/mutations/fetch"):
            return FakeResponse(
                [
                    {
                        "sampleId": "S1",
                        "proteinChange": "G12C",
                        "mutationType": "Missense_Mutation",
                    }
                ]
            )
        return FakeResponse({})


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_fetch_returns_mutation_rows_and_study_counts(tmp_path):
    fetcher = CachedFetcher(tmp_path, offline=False, client=FakeClient())
    mutations, studies = fetch_pancan_mutations("KRAS", "3845", fetcher)
    assert len(studies) == 2
    assert studies["n_samples"].sum() == 150
    assert len(mutations) == 2
    assert set(mutations.columns) >= {"cancer", "sampleId", "proteinChange", "mutationType"}
