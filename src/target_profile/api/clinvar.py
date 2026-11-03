# src/target_profile/api/clinvar.py
from typing import Any

from target_profile.api.cache import CachedFetcher

CLINVAR_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PATHOGENIC_TERM = (
    '{symbol}[gene] AND ("pathogenic"[germline_classification] '
    'OR "likely pathogenic"[germline_classification])'
)


def _count(payload: dict) -> int:
    return int(payload.get("esearchresult", {}).get("count") or 0)


def fetch_clinvar(
    symbol: str,
    fetcher: CachedFetcher,
    retmax: int = 100,
    refresh: bool = False,
) -> dict[str, Any]:
    total_payload = fetcher.request_json(
        "clinvar_search",
        "GET",
        f"{CLINVAR_BASE}/esearch.fcgi",
        gene=symbol,
        params={
            "db": "clinvar",
            "term": f"{symbol}[gene]",
            "retmode": "json",
            "retmax": 0,
            "tool": "target_profile",
        },
        refresh=refresh,
    )
    pathogenic_payload = fetcher.request_json(
        "clinvar_search_pathogenic",
        "GET",
        f"{CLINVAR_BASE}/esearch.fcgi",
        gene=symbol,
        params={
            "db": "clinvar",
            "term": PATHOGENIC_TERM.format(symbol=symbol),
            "retmode": "json",
            "retmax": retmax,
            "tool": "target_profile",
        },
        refresh=refresh,
    )
    ids = [
        uid
        for uid in pathogenic_payload.get("esearchresult", {}).get("idlist", [])
        if uid
    ]
    records: list[dict[str, str]] = []
    if ids:
        summary = fetcher.request_json(
            "clinvar_summary_pathogenic",
            "GET",
            f"{CLINVAR_BASE}/esummary.fcgi",
            gene=symbol,
            params={
                "db": "clinvar",
                "id": ",".join(ids),
                "retmode": "json",
                "tool": "target_profile",
            },
            refresh=refresh,
        )
        result = summary.get("result", {})
        for uid in ids:
            record = result.get(uid) or {}
            classification = record.get("germline_classification") or {}
            records.append(
                {
                    "uid": uid,
                    "title": str(record.get("title") or ""),
                    "classification": str(classification.get("description") or ""),
                    "review_status": str(classification.get("review_status") or ""),
                }
            )
    return {
        "total": _count(total_payload),
        "pathogenic_submissions": _count(pathogenic_payload),
        "records": records,
    }
