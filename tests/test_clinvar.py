# tests/test_clinvar.py
import json

from target_profile.api.cache import CachedFetcher
from target_profile.api.clinvar import fetch_clinvar


def test_fetch_clinvar_reads_cache(tmp_path):
    gene_dir = tmp_path / "KRAS"
    gene_dir.mkdir(parents=True)
    (gene_dir / "clinvar_search.json").write_text(
        json.dumps({"esearchresult": {"count": "628", "idlist": []}})
    )
    (gene_dir / "clinvar_search_pathogenic.json").write_text(
        json.dumps({"esearchresult": {"count": "216", "idlist": ["1", "2"]}})
    )
    (gene_dir / "clinvar_summary_pathogenic.json").write_text(
        json.dumps(
            {
                "result": {
                    "uids": ["1", "2"],
                    "1": {
                        "title": "NM_004985.5(KRAS):c.34G>T (p.Gly12Cys)",
                        "germline_classification": {
                            "description": "Pathogenic",
                            "review_status": "reviewed by expert panel",
                        },
                    },
                    "2": {
                        "title": "NM_004985.5(KRAS):c.173C>T (p.Thr58Ile)",
                        "germline_classification": {
                            "description": "Uncertain significance",
                            "review_status": "criteria provided, single submitter",
                        },
                    },
                }
            }
        )
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    data = fetch_clinvar("KRAS", fetcher)
    assert data["total"] == 628
    assert data["pathogenic_submissions"] == 216
    assert data["records"][0]["classification"] == "Pathogenic"
    assert data["records"][1]["uid"] == "2"


def test_fetch_clinvar_without_pathogenic_ids_skips_summary(tmp_path):
    gene_dir = tmp_path / "ZZZ"
    gene_dir.mkdir(parents=True)
    (gene_dir / "clinvar_search.json").write_text(
        json.dumps({"esearchresult": {"count": "0"}})
    )
    (gene_dir / "clinvar_search_pathogenic.json").write_text(
        json.dumps({"esearchresult": {"count": "0", "idlist": []}})
    )
    fetcher = CachedFetcher(tmp_path, offline=True)
    data = fetch_clinvar("ZZZ", fetcher)
    assert data == {"total": 0, "pathogenic_submissions": 0, "records": []}
