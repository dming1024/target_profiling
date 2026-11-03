import pandas as pd

from target_profile.api.cache import CachedFetcher

CBIO = "https://www.cbioportal.org/api"


def _study_label(name: str) -> str:
    return name.split(" (TCGA")[0]


def fetch_pancan_mutations(
    symbol: str, entrez_id: str, fetcher: CachedFetcher, refresh: bool = False
) -> tuple[pd.DataFrame, pd.DataFrame]:
    studies_payload = fetcher.request_json(
        "cbioportal_studies",
        "GET",
        f"{CBIO}/studies",
        gene=symbol,
        params={"projection": "SUMMARY", "pageSize": 100000},
        refresh=refresh,
    )
    pan = {s["studyId"]: s for s in studies_payload if "tcga_pan_can_atlas" in s["studyId"]}

    mutation_rows: list[dict] = []
    study_rows: list[dict] = []
    for study_id in sorted(pan):
        study = pan[study_id]
        sample_lists = fetcher.request_json(
            f"cbioportal_{study_id}_samplelists",
            "GET",
            f"{CBIO}/studies/{study_id}/sample-lists",
            gene=symbol,
            refresh=refresh,
        )
        sample_list_id = next(
            (
                item["sampleListId"]
                for item in sample_lists
                if item.get("category") == "all_cases_in_study"
                or item["sampleListId"].endswith("_all")
            ),
            sample_lists[0]["sampleListId"] if sample_lists else None,
        )
        if sample_list_id is None:
            continue
        mutations = fetcher.request_json(
            f"cbioportal_{study_id}_mutations",
            "POST",
            f"{CBIO}/molecular-profiles/{study_id}_mutations/mutations/fetch",
            gene=symbol,
            json_body={"entrezGeneIds": [int(entrez_id)], "sampleListId": sample_list_id},
            refresh=refresh,
        )
        cancer = _study_label(study["name"])
        mutated = {m["sampleId"] for m in mutations}
        study_rows.append(
            {
                "studyId": study_id,
                "cancer": cancer,
                "n_samples": int(study.get("allSampleCount") or 0),
                "n_mutated_samples": len(mutated),
                "n_mutations": len(mutations),
            }
        )
        for mutation in mutations:
            mutation_rows.append(
                {
                    "cancer": cancer,
                    "sampleId": mutation["sampleId"],
                    "proteinChange": mutation.get("proteinChange"),
                    "mutationType": mutation.get("mutationType"),
                }
            )

    studies_df = pd.DataFrame(
        study_rows, columns=["studyId", "cancer", "n_samples", "n_mutated_samples", "n_mutations"]
    )
    mutations_df = pd.DataFrame(
        mutation_rows, columns=["cancer", "sampleId", "proteinChange", "mutationType"]
    )
    return mutations_df, studies_df
