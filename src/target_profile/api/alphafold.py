from typing import Any

from target_profile.api.cache import CachedFetcher

AF_URL = "https://alphafold.ebi.ac.uk/api/prediction/{acc}"


def alphafold_prediction(
    acc: str | None, fetcher: CachedFetcher, refresh: bool = False
) -> dict[str, Any] | None:
    if not acc:
        return None
    rows = fetcher.request_json(
        f"alphafold_{acc}",
        "GET",
        AF_URL.format(acc=acc),
        gene="_global",
        refresh=refresh,
    )
    return rows[0] if rows else None


def alphafold_confidence(
    acc: str | None,
    prediction: dict[str, Any] | None,
    fetcher: CachedFetcher,
    refresh: bool = False,
) -> dict[str, Any] | None:
    """Fetch the per-residue pLDDT document referenced by the prediction entry."""
    if not acc or not prediction:
        return None
    url = prediction.get("plddtDocUrl")
    if not url:
        return None
    return fetcher.request_json(
        f"alphafold_plddt_{acc}",
        "GET",
        url,
        gene="_global",
        refresh=refresh,
    )
