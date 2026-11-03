from typing import Any

from target_profile.api.cache import CachedFetcher

STRING_URL = "https://string-db.org/api/json/interaction_partners"


def interaction_partners(
    symbol: str,
    fetcher: CachedFetcher,
    limit: int = 100,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    payload = fetcher.request_json(
        "string_partners",
        "GET",
        STRING_URL,
        gene=symbol,
        params={
            "identifiers": symbol,
            "species": 9606,
            "limit": limit,
            "caller_identity": "target_profile",
        },
        refresh=refresh,
    )
    return payload or []
